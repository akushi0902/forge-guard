/**
 * Integration tests for FindingsTable with MSW.
 *
 * Covers:
 *  1. Render with paginated findings — all rows visible
 *  2. Severity filter click → new API call with severity param → filtered results
 *  3. Pagination: Next button → API called with cursor param → page 2 renders
 *  4. Expand row → useFindingRecommendation called with findingId → panel renders
 */

import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '@/test-utils';
import { server } from '@/test/mocks/server';
import { FindingsTable } from '@/components/findings/FindingsTable';
import {
  CRITICAL_FINDINGS_PAGINATED,
  MIXED_FINDINGS_PAGINATED,
  PAGE_1_FINDINGS_PAGINATED,
  PAGE_2_FINDINGS_PAGINATED,
} from '@/test/fixtures/findings';
import { HIGH_CONFIDENCE_RECOMMENDATION } from '@/test/fixtures/recommendations';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('FindingsTable integration', () => {
  it('renders paginated findings on mount', async () => {
    server.use(
      http.get('/api/v1/services/:serviceId/findings', () =>
        HttpResponse.json(MIXED_FINDINGS_PAGINATED),
      ),
    );
    render(<FindingsTable serviceId="svc-001" />);
    await waitFor(() => {
      expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
      expect(screen.getByText('Test coverage below 80% threshold')).toBeInTheDocument();
      expect(screen.getByText('Outdated dependency with known vulnerability')).toBeInTheDocument();
      expect(screen.getByText('Missing API documentation')).toBeInTheDocument();
    });
  });

  it('filter-fetch-render cycle: clicking Critical filter triggers API with severity=critical', async () => {
    const calls: string[] = [];

    server.use(
      http.get('/api/v1/services/:serviceId/findings', ({ request }) => {
        const url = new URL(request.url);
        const severity = url.searchParams.get('severity');
        calls.push(severity ?? 'all');
        if (severity === 'critical') {
          return HttpResponse.json(CRITICAL_FINDINGS_PAGINATED);
        }
        return HttpResponse.json(MIXED_FINDINGS_PAGINATED);
      }),
    );

    render(<FindingsTable serviceId="svc-001" />);

    // Wait for initial render
    await waitFor(() => {
      expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
    });

    // Click Critical filter
    await userEvent.click(screen.getByTestId('severity-filter-critical'));

    // Wait for filtered results — only critical finding should be visible
    await waitFor(
      () => {
        // Should have made an API call with severity=critical
        expect(calls).toContain('critical');
        expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  it('pagination navigation: Next → API called with cursor → page 2 renders', async () => {
    const requests: { cursor: string | null }[] = [];

    server.use(
      http.get('/api/v1/services/:serviceId/findings', ({ request }) => {
        const url = new URL(request.url);
        const cursor = url.searchParams.get('cursor');
        requests.push({ cursor });
        if (cursor === 'cursor-page-2') {
          return HttpResponse.json(PAGE_2_FINDINGS_PAGINATED);
        }
        return HttpResponse.json(PAGE_1_FINDINGS_PAGINATED);
      }),
    );

    render(<FindingsTable serviceId="svc-001" />);

    // Page 1 data
    await waitFor(() => {
      expect(screen.getByText('SQL injection risk in query builder')).toBeInTheDocument();
    });

    // Click Next
    const nextBtn = screen.getByRole('button', { name: /next page/i });
    expect(nextBtn).not.toBeDisabled();
    await userEvent.click(nextBtn);

    // Page 2 data
    await waitFor(() => {
      expect(screen.getByText('Outdated base image in Dockerfile')).toBeInTheDocument();
      expect(screen.getByText('No README contributing guide')).toBeInTheDocument();
    });

    // Verify the API was called with the cursor param
    expect(requests.some((r) => r.cursor === 'cursor-page-2')).toBe(true);
  });

  it('expand-fetch-render cycle: expand row → recommendation panel renders', async () => {
    server.use(
      http.get('/api/v1/services/:serviceId/findings', () =>
        HttpResponse.json(MIXED_FINDINGS_PAGINATED),
      ),
      http.get('/api/v1/findings/:findingId/recommendation', ({ params }) => {
        if (params.findingId === 'fnd-crit-001') {
          return HttpResponse.json(HIGH_CONFIDENCE_RECOMMENDATION);
        }
        return HttpResponse.json({ detail: 'Not found' }, { status: 404 });
      }),
    );

    render(<FindingsTable serviceId="svc-001" />);

    // Wait for rows to render
    await waitFor(() => {
      expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
    });

    // Click the first row (DataTable handles row-click to expand)
    await userEvent.click(screen.getByText('Hardcoded credentials detected'));

    // Recommendation panel should render
    await waitFor(() => {
      expect(
        screen.getByText(HIGH_CONFIDENCE_RECOMMENDATION.recommendation_text),
      ).toBeInTheDocument();
    });
  });

  it('Previous button is enabled after navigating to page 2', async () => {
    server.use(
      http.get('/api/v1/services/:serviceId/findings', ({ request }) => {
        const url = new URL(request.url);
        const cursor = url.searchParams.get('cursor');
        if (cursor === 'cursor-page-2') {
          return HttpResponse.json(PAGE_2_FINDINGS_PAGINATED);
        }
        return HttpResponse.json(PAGE_1_FINDINGS_PAGINATED);
      }),
    );

    render(<FindingsTable serviceId="svc-001" />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /previous page/i })).toBeDisabled();
    });

    await userEvent.click(screen.getByRole('button', { name: /next page/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /previous page/i })).not.toBeDisabled();
    });
  });

  it('going back to page 1 from page 2 re-renders page 1 data', async () => {
    server.use(
      http.get('/api/v1/services/:serviceId/findings', ({ request }) => {
        const url = new URL(request.url);
        const cursor = url.searchParams.get('cursor');
        if (cursor === 'cursor-page-2') {
          return HttpResponse.json(PAGE_2_FINDINGS_PAGINATED);
        }
        return HttpResponse.json(PAGE_1_FINDINGS_PAGINATED);
      }),
    );

    render(<FindingsTable serviceId="svc-001" />);

    await waitFor(() => {
      expect(screen.getByText('SQL injection risk in query builder')).toBeInTheDocument();
    });

    // Go to page 2
    await userEvent.click(screen.getByRole('button', { name: /next page/i }));
    await waitFor(() => {
      expect(screen.getByText('Outdated base image in Dockerfile')).toBeInTheDocument();
    });

    // Go back to page 1
    await userEvent.click(screen.getByRole('button', { name: /previous page/i }));
    await waitFor(() => {
      expect(screen.getByText('SQL injection risk in query builder')).toBeInTheDocument();
    });
  });
});
