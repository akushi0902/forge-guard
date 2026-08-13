import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '@/test-utils';
import { server } from '@/test/mocks/server';
import { FindingsTable } from '@/components/findings/FindingsTable';
import {
  MIXED_FINDINGS_PAGINATED,
  EMPTY_FINDINGS_PAGINATED,
  CRITICAL_FINDINGS_PAGINATED,
  PAGE_1_FINDINGS_PAGINATED,
  PAGE_2_FINDINGS_PAGINATED,
} from '@/test/fixtures/findings';
import { HIGH_CONFIDENCE_RECOMMENDATION } from '@/test/fixtures/recommendations';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('FindingsTable', () => {
  describe('rendering', () => {
    it('renders column headers: Title, Severity, Dimension, Status, Created', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(screen.getByText('Title')).toBeInTheDocument();
        expect(screen.getByText('Severity')).toBeInTheDocument();
        expect(screen.getByText('Dimension')).toBeInTheDocument();
        expect(screen.getByText('Status')).toBeInTheDocument();
        expect(screen.getByText('Created')).toBeInTheDocument();
      });
    });

    it('renders correct number of rows from mock data', async () => {
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

    it('renders severity badges', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(screen.getByText('Critical')).toBeInTheDocument();
        expect(screen.getByText('High')).toBeInTheDocument();
        expect(screen.getByText('Medium')).toBeInTheDocument();
        expect(screen.getByText('Low')).toBeInTheDocument();
      });
    });

    it('shows empty state when no findings', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(EMPTY_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(
          screen.getByText('No findings — your service is fully compliant'),
        ).toBeInTheDocument();
      });
    });

    it('shows filter-specific empty message when severity filter yields no results', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(EMPTY_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" initialSeverityFilter="critical" />);
      await waitFor(() => {
        expect(
          screen.getByText('No findings match this filter'),
        ).toBeInTheDocument();
      });
    });

    it('hides Dimension column when showDimensionColumn=false', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" showDimensionColumn={false} />);
      await waitFor(() => {
        expect(screen.queryByText('Dimension')).not.toBeInTheDocument();
      });
    });

    it('limits rows in dashboard mode (maxRows)', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" maxRows={2} showPagination={false} />);
      await waitFor(() => {
        expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
        expect(screen.getByText('Test coverage below 80% threshold')).toBeInTheDocument();
        expect(
          screen.queryByText('Outdated dependency with known vulnerability'),
        ).not.toBeInTheDocument();
      });
    });

    it('shows error alert when findings query fails', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(
          screen.getByText('Unable to fetch findings. Please try again.'),
        ).toBeInTheDocument();
      });
    });
  });

  describe('severity filter', () => {
    it('renders the SeverityFilterBar', () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      expect(screen.getByTestId('severity-filter-bar')).toBeInTheDocument();
    });

    it('sets initialSeverityFilter on mount', () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(CRITICAL_FINDINGS_PAGINATED),
        ),
      );
      render(
        <FindingsTable serviceId="svc-001" initialSeverityFilter="critical" />,
      );
      expect(
        screen.getByTestId('severity-filter-critical'),
      ).toHaveAttribute('aria-pressed', 'true');
    });

    it('clicking a filter button updates active state', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await userEvent.click(screen.getByTestId('severity-filter-high'));
      expect(
        screen.getByTestId('severity-filter-high'),
      ).toHaveAttribute('aria-pressed', 'true');
      expect(
        screen.getByTestId('severity-filter-all'),
      ).toHaveAttribute('aria-pressed', 'false');
    });
  });

  describe('column sorting', () => {
    it('sorts rows on Title column header click', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(screen.getByText('Title')).toBeInTheDocument();
      });
      // Click sort on Title column
      await userEvent.click(screen.getByRole('button', { name: 'Title' }));
      // Column header should now have aria-sort="ascending"
      const table = screen.getByRole('table');
      const headers = within(table).getAllByRole('columnheader');
      const titleHeader = headers.find((h) => h.textContent?.includes('Title'));
      expect(titleHeader).toHaveAttribute('aria-sort', 'ascending');
    });

    it('toggles sort direction to descending on second click', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(screen.getByText('Severity')).toBeInTheDocument();
      });
      const severityBtn = screen.getByRole('button', { name: 'Severity' });
      await userEvent.click(severityBtn);
      await userEvent.click(severityBtn);
      const table = screen.getByRole('table');
      const headers = within(table).getAllByRole('columnheader');
      const severityHeader = headers.find((h) => h.textContent?.includes('Severity'));
      expect(severityHeader).toHaveAttribute('aria-sort', 'descending');
    });

    it('sorts created_at column', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(screen.getByText('Created')).toBeInTheDocument();
      });
      await userEvent.click(screen.getByRole('button', { name: 'Created' }));
      const table = screen.getByRole('table');
      const headers = within(table).getAllByRole('columnheader');
      const createdHeader = headers.find((h) => h.textContent?.includes('Created'));
      expect(createdHeader).toHaveAttribute('aria-sort', 'ascending');
    });
  });

  describe('pagination', () => {
    it('renders Previous and Next buttons', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /previous page/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole('button', { name: /next page/i }),
        ).toBeInTheDocument();
      });
    });

    it('disables Previous button on first page', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /previous page/i }),
        ).toBeDisabled();
      });
    });

    it('disables Next button when cursor is null (last page)', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED), // cursor: null
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /next page/i }),
        ).toBeDisabled();
      });
    });

    it('enables Next button when cursor is returned', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(PAGE_1_FINDINGS_PAGINATED), // cursor: 'cursor-page-2'
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /next page/i }),
        ).not.toBeDisabled();
      });
    });

    it('navigates to next page on Next button click', async () => {
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
      await userEvent.click(screen.getByRole('button', { name: /next page/i }));
      await waitFor(() => {
        expect(screen.getByText('Outdated base image in Dockerfile')).toBeInTheDocument();
      });
    });

    it('hides pagination when showPagination=false', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" showPagination={false} />);
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /previous page/i })).not.toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /next page/i })).not.toBeInTheDocument();
      });
    });
  });

  describe('expandable rows', () => {
    it('expands a row when clicked, loading AI recommendation', async () => {
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
        http.get('/api/v1/findings/:findingId/recommendation', () =>
          HttpResponse.json(HIGH_CONFIDENCE_RECOMMENDATION),
        ),
      );
      render(<FindingsTable serviceId="svc-001" />);
      await waitFor(() => {
        expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
      });
      // Click the first row's title to expand (DataTable handles row click)
      await userEvent.click(screen.getByText('Hardcoded credentials detected'));
      // Recommendation text should appear
      await waitFor(() => {
        expect(
          screen.getByText(HIGH_CONFIDENCE_RECOMMENDATION.recommendation_text),
        ).toBeInTheDocument();
      });
    });

    it('calls onFindingClick when provided and title is clicked', async () => {
      const onFindingClick = vi.fn();
      server.use(
        http.get('/api/v1/services/:serviceId/findings', () =>
          HttpResponse.json(MIXED_FINDINGS_PAGINATED),
        ),
      );
      render(<FindingsTable serviceId="svc-001" onFindingClick={onFindingClick} />);
      await waitFor(() => {
        expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
      });
      await userEvent.click(screen.getByText('Hardcoded credentials detected'));
      expect(onFindingClick).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'fnd-crit-001' }),
      );
    });
  });
});
