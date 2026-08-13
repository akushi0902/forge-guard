/**
 * Integration tests for PlatformHealthPage (WO-081).
 *
 * Covers: status grid rendering, service health rows, chart card, log entries,
 * overall status badge, last-refresh timestamp, auto-refresh timer behavior,
 * and degraded/down scenarios.
 */

import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { PlatformHealthPage } from '@/pages/PlatformHealthPage';
import { server } from '@/test/mocks/server';
import {
  PLATFORM_HEALTH_FIXTURE,
  PLATFORM_HEALTH_DEGRADED_FIXTURE,
  PLATFORM_HEALTH_DOWN_FIXTURE,
  PLATFORM_LOGS_FIXTURE,
  SYSTEM_HEALTH_FIXTURE,
  READINESS_FIXTURE,
} from '@/test/mocks/handlers/health';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  vi.useRealTimers();
});
afterAll(() => server.close());

describe('PlatformHealthPage — healthy state', () => {
  it('renders the page heading', () => {
    render(<PlatformHealthPage />);
    expect(screen.getByText('Platform Health')).toBeInTheDocument();
    expect(screen.getByText(/Auto-refreshes every 10 seconds/)).toBeInTheDocument();
  });

  it('renders all four StatusGrid cards after data loads', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('status-card-api-success-rate')).toBeInTheDocument();
      expect(screen.getByTestId('status-card-assessment-completion')).toBeInTheDocument();
      expect(screen.getByTestId('status-card-db-pool-utilization')).toBeInTheDocument();
      expect(screen.getByTestId('status-card-audit-log-success')).toBeInTheDocument();
    });
  });

  it('shows correct API success rate value', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('status-card-api-success-rate')).toHaveTextContent('99.5');
    });
  });

  it('renders all five service health check rows', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByText('Backend API')).toBeInTheDocument();
      expect(screen.getByText('Database')).toBeInTheDocument();
      expect(screen.getByText('Frontend')).toBeInTheDocument();
      expect(screen.getByText('LLM Provider')).toBeInTheDocument();
      expect(screen.getByText('CI/CD Pipeline')).toBeInTheDocument();
    });
  });

  it('shows "Healthy" overall status badge when all metrics are green', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('overall-status-badge')).toHaveTextContent('Healthy');
    });
  });

  it('shows last-refresh timestamp after initial data load', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('last-refresh-time')).toBeInTheDocument();
    });
  });

  it('renders the ResponseTimeChartCard container', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('response-time-chart-card')).toBeInTheDocument();
    });
  });

  it('renders RecentLogsCard with log entries', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByText('Recent Operational Logs')).toBeInTheDocument();
      expect(screen.getByTestId('log-entry-log-001')).toBeInTheDocument();
    });
  });

  it('renders up to 6 log entries', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      for (const entry of PLATFORM_LOGS_FIXTURE.entries.slice(0, 6)) {
        expect(screen.getByTestId(`log-entry-${entry.id}`)).toBeInTheDocument();
      }
    });
  });

  it('does not show stale data banner when healthy', async () => {
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.queryByTestId('stale-data-banner')).not.toBeInTheDocument();
    });
  });
});

describe('PlatformHealthPage — degraded state', () => {
  it('shows "Degraded" badge when LLM circuit breaker is half-open', async () => {
    server.use(
      http.get('/api/v1/platform/health', () =>
        HttpResponse.json(PLATFORM_HEALTH_DEGRADED_FIXTURE),
      ),
    );
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('overall-status-badge')).toHaveTextContent('Degraded');
    });
  });

  it('shows degraded badge for LLM Provider service row', async () => {
    server.use(
      http.get('/api/v1/platform/health', () =>
        HttpResponse.json(PLATFORM_HEALTH_DEGRADED_FIXTURE),
      ),
    );
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('service-status-llm-provider')).toHaveTextContent('Degraded');
    });
  });

  it('shows red StatusCard when DB pool utilization is critical', async () => {
    server.use(
      http.get('/api/v1/platform/health', () =>
        HttpResponse.json(PLATFORM_HEALTH_DOWN_FIXTURE),
      ),
    );
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('overall-status-badge')).toHaveTextContent('Critical');
    });
  });
});

describe('PlatformHealthPage — auto-refresh', () => {
  it('re-fetches health data after the 10-second interval', async () => {
    vi.useFakeTimers();
    let callCount = 0;
    server.use(
      http.get('/api/v1/platform/health', () => {
        callCount++;
        return HttpResponse.json(PLATFORM_HEALTH_FIXTURE);
      }),
    );
    render(<PlatformHealthPage />);

    // Initial fetch
    await act(async () => { await Promise.resolve(); });
    const after_initial = callCount;
    expect(after_initial).toBeGreaterThan(0);

    // Advance past the 10-second polling interval
    await act(async () => { vi.advanceTimersByTime(10_100); });

    expect(callCount).toBeGreaterThan(after_initial);
  });
});

describe('PlatformHealthPage — TanStack Query hook integration', () => {
  it('fetches from /health endpoint', async () => {
    let healthCalled = false;
    server.use(
      http.get('/health', () => {
        healthCalled = true;
        return HttpResponse.json(SYSTEM_HEALTH_FIXTURE);
      }),
    );
    render(<PlatformHealthPage />);
    await waitFor(() => { expect(healthCalled).toBe(true); });
  });

  it('fetches from /ready endpoint', async () => {
    let readyCalled = false;
    server.use(
      http.get('/ready', () => {
        readyCalled = true;
        return HttpResponse.json(READINESS_FIXTURE);
      }),
    );
    render(<PlatformHealthPage />);
    await waitFor(() => { expect(readyCalled).toBe(true); });
  });

  it('fetches from /api/v1/platform/health endpoint', async () => {
    let platformCalled = false;
    server.use(
      http.get('/api/v1/platform/health', () => {
        platformCalled = true;
        return HttpResponse.json(PLATFORM_HEALTH_FIXTURE);
      }),
    );
    render(<PlatformHealthPage />);
    await waitFor(() => { expect(platformCalled).toBe(true); });
  });

  it('renders Backend API as down when /health returns 500', async () => {
    server.use(
      http.get('/health', () =>
        HttpResponse.json({ detail: 'Service unavailable' }, { status: 500 }),
      ),
    );
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('service-status-backend-api')).toHaveTextContent('Down');
    });
  });

  it('renders Database as down when /ready returns 500', async () => {
    server.use(
      http.get('/ready', () =>
        HttpResponse.json({ detail: 'DB unreachable' }, { status: 500 }),
      ),
    );
    render(<PlatformHealthPage />);
    await waitFor(() => {
      expect(screen.getByTestId('service-status-database')).toHaveTextContent('Down');
    });
  });
});
