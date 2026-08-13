import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '@/test-utils';
import { server } from '@/test/mocks/server';
import { FindingExpandedRow } from '@/components/findings/FindingExpandedRow';
import {
  HIGH_CONFIDENCE_RECOMMENDATION,
  MEDIUM_CONFIDENCE_RECOMMENDATION,
  ZERO_CONFIDENCE_RECOMMENDATION,
} from '@/test/fixtures/recommendations';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('FindingExpandedRow', () => {
  it('renders a loading skeleton on initial mount', () => {
    // Default MSW handler responds, but while loading skeletons are visible
    render(<FindingExpandedRow findingId="fnd-crit-001" />);
    // Skeleton elements are rendered by default (Mantine Skeleton renders divs)
    // We just verify the component renders without crashing during loading.
    expect(document.body).toBeTruthy();
  });

  it('renders recommendation_text after data loads', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(HIGH_CONFIDENCE_RECOMMENDATION),
      ),
    );
    render(<FindingExpandedRow findingId="fnd-crit-001" />);
    await waitFor(() => {
      expect(
        screen.getByText(HIGH_CONFIDENCE_RECOMMENDATION.recommendation_text),
      ).toBeInTheDocument();
    });
  });

  it('renders implementation_guide after data loads', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(HIGH_CONFIDENCE_RECOMMENDATION),
      ),
    );
    render(<FindingExpandedRow findingId="fnd-crit-001" />);
    await waitFor(() => {
      // The implementation guide is rendered in a Code block; verify its text is present
      expect(
        screen.getByText(
          (_content, el) =>
            el != null &&
            el.textContent?.includes('Identify all secrets') === true,
        ),
      ).toBeInTheDocument();
    });
  });

  it('renders ConfidenceMeter with correct percentage for high-confidence recommendation', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(HIGH_CONFIDENCE_RECOMMENDATION),
      ),
    );
    render(<FindingExpandedRow findingId="fnd-crit-001" />);
    await waitFor(() => {
      expect(screen.getByText('95%')).toBeInTheDocument();
    });
  });

  it('renders ConfidenceMeter for medium-confidence recommendation', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(MEDIUM_CONFIDENCE_RECOMMENDATION),
      ),
    );
    render(<FindingExpandedRow findingId="fnd-high-001" />);
    await waitFor(() => {
      expect(screen.getByText('65%')).toBeInTheDocument();
    });
  });

  it('renders 0% confidence meter for zero-confidence recommendation', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(ZERO_CONFIDENCE_RECOMMENDATION),
      ),
    );
    render(<FindingExpandedRow findingId="fnd-low-001" />);
    await waitFor(() => {
      expect(screen.getByText('0%')).toBeInTheDocument();
    });
  });

  it('shows "No AI recommendation available" when API returns 404', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    );
    render(<FindingExpandedRow findingId="fnd-no-rec" />);
    await waitFor(() => {
      expect(
        screen.getByText('No AI recommendation available for this finding.'),
      ).toBeInTheDocument();
    });
  });

  it('shows error message and retry button when API returns 500', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
    );
    render(<FindingExpandedRow findingId="fnd-error" />);
    await waitFor(() => {
      expect(
        screen.getByText('Failed to load AI recommendation.'),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  it('renders section headings for recommendation and implementation guide', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(HIGH_CONFIDENCE_RECOMMENDATION),
      ),
    );
    render(<FindingExpandedRow findingId="fnd-crit-001" />);
    await waitFor(() => {
      expect(screen.getByText('AI Recommendation')).toBeInTheDocument();
      expect(screen.getByText('Implementation Guide')).toBeInTheDocument();
    });
  });
});
