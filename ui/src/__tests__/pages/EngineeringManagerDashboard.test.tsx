/**
 * Integration tests for EngineeringManagerDashboard (WO-078).
 *
 * Verifies full dashboard render: KPI cards, health distribution, trend charts,
 * resolution charts, services table, empty state, loading state, and error state.
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
import { EngineeringManagerDashboard } from '@/pages/EngineeringManager';
import { server } from '@/test/mocks/server';
import {
  SERVICES_WITH_METRICS_RESPONSE,
  EMPTY_SERVICES_RESPONSE,
  ASSESSMENT_TRENDS_RESPONSE,
  EMPTY_TRENDS_RESPONSE,
} from '@/test/fixtures/managerDashboardData';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function setupDefaultHandlers() {
  server.use(
    http.get('/api/v1/services/with-metrics', () =>
      HttpResponse.json(SERVICES_WITH_METRICS_RESPONSE),
    ),
    http.get('/api/v1/assessments/trends', () =>
      HttpResponse.json(ASSESSMENT_TRENDS_RESPONSE),
    ),
  );
}

// ---------------------------------------------------------------------------
// Page structure
// ---------------------------------------------------------------------------

describe('EngineeringManagerDashboard — page structure', () => {
  it('renders the page title', async () => {
    setupDefaultHandlers();
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('manager-dashboard-title')).toBeInTheDocument();
    });
    expect(screen.getByText('Engineering Manager Dashboard')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Healthy data loaded
// ---------------------------------------------------------------------------

describe('EngineeringManagerDashboard — full data render', () => {
  it('renders all 4 KPI cards', async () => {
    setupDefaultHandlers();
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Avg Health Score')).toBeInTheDocument();
      expect(screen.getByText('Services ≥ 70')).toBeInTheDocument();
      expect(screen.getByText('Critical Findings')).toBeInTheDocument();
      expect(screen.getByText('Avg Time to Remediate')).toBeInTheDocument();
    });
  });

  it('renders the health distribution card', async () => {
    setupDefaultHandlers();
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Health Score Distribution')).toBeInTheDocument();
    });
  });

  it('renders the trend chart card', async () => {
    setupDefaultHandlers();
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Health Score Trend — Last 6 Months')).toBeInTheDocument();
    });
  });

  it('renders the resolution rate chart card', async () => {
    setupDefaultHandlers();
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(
        screen.getByText('Finding Resolution Rate — Last 6 Months'),
      ).toBeInTheDocument();
    });
  });

  it('renders the services table card with service data', async () => {
    setupDefaultHandlers();
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Services Overview')).toBeInTheDocument();
      expect(screen.getByText('payment-service')).toBeInTheDocument();
    });
  });

  it('renders the team filter select in the services table', async () => {
    setupDefaultHandlers();
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('team-filter-select')).toBeInTheDocument();
    });
  });

  it('renders the export CSV button', async () => {
    setupDefaultHandlers();
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('export-csv-btn')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe('EngineeringManagerDashboard — empty state', () => {
  it('shows empty services table when no services returned', async () => {
    server.use(
      http.get('/api/v1/services/with-metrics', () =>
        HttpResponse.json(EMPTY_SERVICES_RESPONSE),
      ),
      http.get('/api/v1/assessments/trends', () =>
        HttpResponse.json(EMPTY_TRENDS_RESPONSE),
      ),
    );
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByText('No services found.')).toBeInTheDocument();
    });
  });

  it('shows empty trend chart when no trends returned', async () => {
    server.use(
      http.get('/api/v1/services/with-metrics', () =>
        HttpResponse.json(EMPTY_SERVICES_RESPONSE),
      ),
      http.get('/api/v1/assessments/trends', () =>
        HttpResponse.json(EMPTY_TRENDS_RESPONSE),
      ),
    );
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByText('No trend data available.')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe('EngineeringManagerDashboard — loading state', () => {
  it('renders skeleton components while data is loading', () => {
    server.use(
      http.get('/api/v1/services/with-metrics', () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(HttpResponse.json(SERVICES_WITH_METRICS_RESPONSE)), 300),
        ),
      ),
      http.get('/api/v1/assessments/trends', () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(HttpResponse.json(ASSESSMENT_TRENDS_RESPONSE)), 300),
        ),
      ),
    );
    render(<EngineeringManagerDashboard />);
    expect(screen.getByTestId('manager-dashboard-skeleton')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

describe('EngineeringManagerDashboard — error state', () => {
  it('renders error alert when services endpoint returns 500', async () => {
    server.use(
      http.get('/api/v1/services/with-metrics', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
      http.get('/api/v1/assessments/trends', () =>
        HttpResponse.json(ASSESSMENT_TRENDS_RESPONSE),
      ),
    );
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('manager-dashboard-error')).toBeInTheDocument();
    });
  });

  it('renders a Retry button in the error state', async () => {
    server.use(
      http.get('/api/v1/services/with-metrics', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
      http.get('/api/v1/assessments/trends', () =>
        HttpResponse.json(ASSESSMENT_TRENDS_RESPONSE),
      ),
    );
    render(<EngineeringManagerDashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('manager-retry-btn')).toBeInTheDocument();
    });
  });
});
