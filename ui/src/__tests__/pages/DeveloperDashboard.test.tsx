/**
 * Integration tests for DeveloperDashboard (WO-072).
 *
 * Verifies the full dashboard render: stat cards, dimension bars, findings
 * table, empty state, loading state, and error state using MSW fixtures.
 */

import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
} from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { DeveloperDashboard } from '@/pages/DeveloperDashboard';
import { server } from '@/test/mocks/server';
import { SERVICE_FIXTURE, SERVICE_LIST_FIXTURE } from '@/test/mocks/handlers/services';
import { HEALTHY_SCORE_FIXTURE } from '@/test/fixtures/scores';
import { MIXED_FINDINGS_PAGINATED, EMPTY_FINDINGS_PAGINATED } from '@/test/fixtures/findings';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

/** Render DeveloperDashboard with a pre-selected serviceId in the URL. */
function renderWithService(serviceId = SERVICE_FIXTURE.id) {
  return render(<DeveloperDashboard />, {
    routerProps: {
      initialEntries: [`/?serviceId=${serviceId}`],
    },
  });
}

/** Render with the default healthy score and mixed findings handlers. */
function setupHealthyHandlers() {
  server.use(
    http.get('/api/v1/services', () => HttpResponse.json(SERVICE_LIST_FIXTURE)),
    http.get('/api/v1/services/:id', () => HttpResponse.json(SERVICE_FIXTURE)),
    http.get('/api/v1/services/:id/scores', () =>
      HttpResponse.json(HEALTHY_SCORE_FIXTURE),
    ),
    http.get('/api/v1/services/:id/findings', () =>
      HttpResponse.json(MIXED_FINDINGS_PAGINATED),
    ),
  );
}

// ---------------------------------------------------------------------------
// Page structure
// ---------------------------------------------------------------------------

describe('DeveloperDashboard — page structure', () => {
  it('renders the Developer Dashboard heading', () => {
    render(<DeveloperDashboard />);
    expect(screen.getByText('Developer Dashboard')).toBeInTheDocument();
  });

  it('renders the service selector', () => {
    render(<DeveloperDashboard />);
    expect(screen.getByTestId('service-selector')).toBeInTheDocument();
  });

  it('shows a prompt when no service is selected', () => {
    render(<DeveloperDashboard />);
    expect(screen.getByTestId('no-service-prompt')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Full dashboard — healthy service
// ---------------------------------------------------------------------------

describe('DeveloperDashboard — healthy service with data', () => {
  it('renders all 4 stat card titles after data loads', async () => {
    setupHealthyHandlers();
    renderWithService();
    await waitFor(() => {
      expect(screen.getByText('Health Score')).toBeInTheDocument();
      expect(screen.getByText('Open Findings')).toBeInTheDocument();
      expect(screen.getByText('Critical / High')).toBeInTheDocument();
      expect(screen.getByText('Last Evaluation')).toBeInTheDocument();
    });
  });

  it('displays the correct health score value', async () => {
    setupHealthyHandlers();
    renderWithService();
    await waitFor(() => {
      // Overall score from HEALTHY_SCORE_FIXTURE is 85
      expect(screen.getByText('85')).toBeInTheDocument();
    });
  });

  it('renders 5 dimension bars in the HealthScoreCard', async () => {
    setupHealthyHandlers();
    renderWithService();
    await waitFor(() => {
      expect(screen.getByText('Code Quality')).toBeInTheDocument();
      expect(screen.getByText('Test Coverage')).toBeInTheDocument();
      expect(screen.getByText('Security')).toBeInTheDocument();
      expect(screen.getByText('Documentation')).toBeInTheDocument();
      expect(screen.getByText('Operations Readiness')).toBeInTheDocument();
    });
  });

  it('renders the ScoreRing SVG with the overall score', async () => {
    setupHealthyHandlers();
    renderWithService();
    await waitFor(() => {
      const svg = document.querySelector('svg[role="img"]');
      expect(svg).toBeInTheDocument();
      expect(svg?.getAttribute('aria-label')).toContain('85');
    });
  });

  it('renders the findings table with correct rows', async () => {
    setupHealthyHandlers();
    renderWithService();
    await waitFor(() => {
      expect(screen.getByText('Hardcoded credentials detected')).toBeInTheDocument();
      expect(screen.getByText('Test coverage below 80% threshold')).toBeInTheDocument();
    });
  });

  it('shows severity filter tabs', async () => {
    setupHealthyHandlers();
    renderWithService();
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Critical' })).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe('DeveloperDashboard — empty state (no evaluations)', () => {
  it('shows the EmptyStateCard when scores endpoint returns null data', async () => {
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json(SERVICE_LIST_FIXTURE)),
      http.get('/api/v1/services/:id', () => HttpResponse.json(SERVICE_FIXTURE)),
      http.get('/api/v1/services/:id/scores', () =>
        HttpResponse.json(null, { status: 200 }),
      ),
      http.get('/api/v1/services/:id/findings', () =>
        HttpResponse.json(EMPTY_FINDINGS_PAGINATED),
      ),
    );
    renderWithService();
    await waitFor(() => {
      expect(screen.getByText('No evaluations yet')).toBeInTheDocument();
    });
  });

  it('shows the 3-step onboarding instructions', async () => {
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json(SERVICE_LIST_FIXTURE)),
      http.get('/api/v1/services/:id', () => HttpResponse.json(SERVICE_FIXTURE)),
      http.get('/api/v1/services/:id/scores', () =>
        HttpResponse.json(null, { status: 200 }),
      ),
      http.get('/api/v1/services/:id/findings', () =>
        HttpResponse.json(EMPTY_FINDINGS_PAGINATED),
      ),
    );
    renderWithService();
    await waitFor(() => {
      expect(screen.getByText('Register your service')).toBeInTheDocument();
      expect(screen.getByText('Configure policies')).toBeInTheDocument();
      expect(screen.getByText('Trigger your first evaluation')).toBeInTheDocument();
    });
  });

  it('renders the Run First Assessment CTA button', async () => {
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json(SERVICE_LIST_FIXTURE)),
      http.get('/api/v1/services/:id', () => HttpResponse.json(SERVICE_FIXTURE)),
      http.get('/api/v1/services/:id/scores', () =>
        HttpResponse.json(null, { status: 200 }),
      ),
      http.get('/api/v1/services/:id/findings', () =>
        HttpResponse.json(EMPTY_FINDINGS_PAGINATED),
      ),
    );
    renderWithService();
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /run first assessment/i }),
      ).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe('DeveloperDashboard — loading state', () => {
  it('renders skeleton components while data is fetching', async () => {
    server.use(
      http.get('/api/v1/services', () =>
        new Promise((resolve) =>
          setTimeout(
            () => resolve(HttpResponse.json(SERVICE_LIST_FIXTURE)),
            200,
          ),
        ),
      ),
      http.get('/api/v1/services/:id/scores', () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(HttpResponse.json(HEALTHY_SCORE_FIXTURE)), 200),
        ),
      ),
      http.get('/api/v1/services/:id/findings', () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(HttpResponse.json(MIXED_FINDINGS_PAGINATED)), 200),
        ),
      ),
    );
    renderWithService();
    // Skeleton should be visible before data arrives
    expect(screen.getByTestId('dashboard-skeleton')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

describe('DeveloperDashboard — error state', () => {
  it('renders an error alert when the scores endpoint returns 500', async () => {
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json(SERVICE_LIST_FIXTURE)),
      http.get('/api/v1/services/:id', () => HttpResponse.json(SERVICE_FIXTURE)),
      http.get('/api/v1/services/:id/scores', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
      http.get('/api/v1/services/:id/findings', () =>
        HttpResponse.json(MIXED_FINDINGS_PAGINATED),
      ),
    );
    renderWithService();
    await waitFor(() => {
      expect(screen.getByTestId('dashboard-error')).toBeInTheDocument();
    });
  });

  it('renders a Retry button in the error state', async () => {
    server.use(
      http.get('/api/v1/services', () => HttpResponse.json(SERVICE_LIST_FIXTURE)),
      http.get('/api/v1/services/:id', () => HttpResponse.json(SERVICE_FIXTURE)),
      http.get('/api/v1/services/:id/scores', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
      http.get('/api/v1/services/:id/findings', () =>
        HttpResponse.json(MIXED_FINDINGS_PAGINATED),
      ),
    );
    renderWithService();
    await waitFor(() => {
      expect(screen.getByTestId('retry-btn')).toBeInTheDocument();
    });
  });
});
