/**
 * Unit tests for AssessmentProgress (WO-074).
 *
 * Covers: spinner rendering, elapsed time counter, timeout warning,
 * cancel link, navigation on completion, and error/retry message.
 */

import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { AssessmentProgress } from '@/components/releases/AssessmentProgress';
import { server } from '@/test/mocks/server';
import { RELEASE_FIXTURE, PENDING_RELEASE_FIXTURE } from '@/test/mocks/handlers/releases';

// Mock useNavigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  mockNavigate.mockClear();
  vi.useRealTimers();
});
afterAll(() => server.close());

describe('AssessmentProgress rendering', () => {
  it('renders spinner and "Assessment in progress" heading', async () => {
    server.use(
      http.get('/api/v1/releases/:id', () => HttpResponse.json(PENDING_RELEASE_FIXTURE)),
    );
    render(<AssessmentProgress assessmentId="rel-pending" />);
    expect(screen.getByText(/assessment in progress/i)).toBeInTheDocument();
  });

  it('renders elapsed time counter', async () => {
    server.use(
      http.get('/api/v1/releases/:id', () => HttpResponse.json(PENDING_RELEASE_FIXTURE)),
    );
    render(<AssessmentProgress assessmentId="rel-pending" />);
    expect(screen.getByTestId('elapsed-time')).toBeInTheDocument();
  });

  it('renders cancel link when onCancel is provided', async () => {
    server.use(
      http.get('/api/v1/releases/:id', () => HttpResponse.json(PENDING_RELEASE_FIXTURE)),
    );
    const onCancel = vi.fn();
    render(<AssessmentProgress assessmentId="rel-pending" onCancel={onCancel} />);
    expect(screen.getByText(/cancel/i)).toBeInTheDocument();
  });

  it('calls onCancel when cancel is clicked', async () => {
    server.use(
      http.get('/api/v1/releases/:id', () => HttpResponse.json(PENDING_RELEASE_FIXTURE)),
    );
    const onCancel = vi.fn();
    render(<AssessmentProgress assessmentId="rel-pending" onCancel={onCancel} />);
    await userEvent.click(screen.getByText(/cancel/i));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});

describe('AssessmentProgress elapsed time', () => {
  it('increments elapsed time every second', async () => {
    vi.useFakeTimers();
    server.use(
      http.get('/api/v1/releases/:id', () => HttpResponse.json(PENDING_RELEASE_FIXTURE)),
    );
    render(<AssessmentProgress assessmentId="rel-pending" />);

    // Initially shows 0s
    expect(screen.getByTestId('elapsed-time')).toHaveTextContent('Elapsed: 0s');

    // Advance 3 seconds
    vi.advanceTimersByTime(3000);
    await waitFor(() => {
      expect(screen.getByTestId('elapsed-time')).toHaveTextContent('Elapsed: 3s');
    });
  });

  it('shows timeout warning after 300 seconds', async () => {
    vi.useFakeTimers();
    server.use(
      http.get('/api/v1/releases/:id', () => HttpResponse.json(PENDING_RELEASE_FIXTURE)),
    );
    render(<AssessmentProgress assessmentId="rel-pending" />);

    // Timeout warning should not be visible initially
    expect(screen.queryByTestId('timeout-warning')).not.toBeInTheDocument();

    // Advance past 300 seconds
    vi.advanceTimersByTime(301_000);
    await waitFor(() => {
      expect(screen.getByTestId('timeout-warning')).toBeInTheDocument();
      expect(
        screen.getByText(/taking longer than expected/i),
      ).toBeInTheDocument();
    });
  });
});

describe('AssessmentProgress navigation', () => {
  it('navigates to /releases/{id} when assessment status becomes completed', async () => {
    // Override handler to return completed status
    server.use(
      http.get('/api/v1/releases/:id', () => HttpResponse.json(RELEASE_FIXTURE)),
    );
    render(<AssessmentProgress assessmentId={RELEASE_FIXTURE.id} />);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(`/releases/${RELEASE_FIXTURE.id}`);
    });
  });
});

describe('AssessmentProgress error handling', () => {
  it('shows retrying message when polling returns an error', async () => {
    server.use(
      http.get('/api/v1/releases/:id', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    );
    render(<AssessmentProgress assessmentId="rel-pending" />);

    await waitFor(() => {
      expect(screen.getByText(/unable to check assessment status/i)).toBeInTheDocument();
    });
  });

  it('shows fatal error alert after 3 consecutive poll failures', async () => {
    vi.useFakeTimers();
    server.use(
      http.get('/api/v1/releases/:id', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    );
    render(<AssessmentProgress assessmentId="rel-pending" />);

    // First fetch fails immediately on mount (no timer needed).
    // Advance past 2 more polling cycles (5s each) to reach 3 total failures.
    await act(async () => { vi.advanceTimersByTime(10_100); });

    expect(
      screen.queryByText(/assessment status unavailable — try refreshing/i),
    ).toBeInTheDocument();
  });
});
