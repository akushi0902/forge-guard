import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '@/test-utils';
import { server } from '@/test/mocks/server';
import { FindingsCard } from '@/components/dashboard/FindingsCard';
import { MIXED_FINDINGS_PAGINATED, EMPTY_FINDINGS_PAGINATED } from '@/test/fixtures/findings';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('FindingsCard', () => {
  it('renders the Findings heading', () => {
    render(<FindingsCard serviceId="svc-001" />);
    expect(screen.getByText('Findings')).toBeInTheDocument();
  });

  it('renders severity filter tabs', () => {
    render(<FindingsCard serviceId="svc-001" />);
    expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Critical' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'High' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Medium' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Low' })).toBeInTheDocument();
  });

  it('renders findings rows after data loads', async () => {
    server.use(
      http.get('/api/v1/services/:serviceId/findings', () =>
        HttpResponse.json(MIXED_FINDINGS_PAGINATED),
      ),
    );
    render(<FindingsCard serviceId="svc-001" />);
    await waitFor(() => {
      expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
    });
  });

  it('shows the empty compliance message when there are no findings', async () => {
    server.use(
      http.get('/api/v1/services/:serviceId/findings', () =>
        HttpResponse.json(EMPTY_FINDINGS_PAGINATED),
      ),
    );
    render(<FindingsCard serviceId="svc-001" />);
    await waitFor(() => {
      expect(
        screen.getByText("No findings — your service is fully compliant"),
      ).toBeInTheDocument();
    });
  });

  it('shows columns: Title, Severity, Dimension, Status, Detected', async () => {
    server.use(
      http.get('/api/v1/services/:serviceId/findings', () =>
        HttpResponse.json(MIXED_FINDINGS_PAGINATED),
      ),
    );
    render(<FindingsCard serviceId="svc-001" />);
    await waitFor(() => {
      expect(screen.getByText('Title')).toBeInTheDocument();
      expect(screen.getByText('Severity')).toBeInTheDocument();
      expect(screen.getByText('Dimension')).toBeInTheDocument();
      expect(screen.getByText('Status')).toBeInTheDocument();
      expect(screen.getByText('Detected')).toBeInTheDocument();
    });
  });

  it('shows an error alert when the findings query fails', async () => {
    server.use(
      http.get('/api/v1/services/:serviceId/findings', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
    );
    render(<FindingsCard serviceId="svc-001" />);
    await waitFor(() => {
      expect(
        screen.getByRole('alert'),
      ).toBeInTheDocument();
    });
  });
});
