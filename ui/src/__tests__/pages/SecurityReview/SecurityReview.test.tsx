/**
 * Integration tests for SecurityReview page (WO-077).
 *
 * Verifies full page rendering: escalation alert, KPI cards, pending escalations,
 * findings table, empty state, loading state, and error state.
 * Uses MSW to mock API endpoints.
 */

import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { SecurityReview } from '@/pages/SecurityReview';
import { server } from '@/test/mocks/server';
import { useAuthStore } from '@/stores/auth-store';
import { Role } from '@/types';
import type { User } from '@/stores/auth-store';
import {
  SECURITY_FINDINGS_PAGINATED,
  EMPTY_SECURITY_FINDINGS_PAGINATED,
  ESCALATIONS_PAGINATED,
  EMPTY_ESCALATIONS_PAGINATED,
  PENDING_EXCEPTIONS_PAGINATED,
  EMPTY_EXCEPTIONS_PAGINATED,
} from '@/test/fixtures/securityFindings';

// ---------------------------------------------------------------------------
// Test user fixtures
// ---------------------------------------------------------------------------

const securityReviewerUser: User = {
  id: 'usr-sec-001',
  email: 'security@forgeguard.io',
  name: 'Security Reviewer',
  role: Role.SecurityReviewer,
  permissions: ['release.block', 'exception.approve', 'security:review', 'finding:read'],
};

const developerUser: User = {
  id: 'usr-dev-001',
  email: 'dev@forgeguard.io',
  name: 'Developer',
  role: Role.Developer,
  permissions: ['service:read', 'finding:read'],
};

// ---------------------------------------------------------------------------
// MSW setup
// ---------------------------------------------------------------------------

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, csrfToken: null });
});
afterAll(() => server.close());

function setupDefaultHandlers(): void {
  server.use(
    http.get('/api/v1/findings', () => HttpResponse.json(SECURITY_FINDINGS_PAGINATED)),
    http.get('/api/v1/releases', () => HttpResponse.json(ESCALATIONS_PAGINATED)),
    http.get('/api/v1/exceptions', () => HttpResponse.json(PENDING_EXCEPTIONS_PAGINATED)),
  );
}

function setupEmptyHandlers(): void {
  server.use(
    http.get('/api/v1/findings', () => HttpResponse.json(EMPTY_SECURITY_FINDINGS_PAGINATED)),
    http.get('/api/v1/releases', () => HttpResponse.json(EMPTY_ESCALATIONS_PAGINATED)),
    http.get('/api/v1/exceptions', () => HttpResponse.json(EMPTY_EXCEPTIONS_PAGINATED)),
  );
}

beforeEach(() => {
  useAuthStore.setState({ user: securityReviewerUser, isAuthenticated: true });
});

// ---------------------------------------------------------------------------
// Page structure
// ---------------------------------------------------------------------------

describe('SecurityReview — page structure', () => {
  it('renders the page title', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('security-review-title')).toBeInTheDocument();
    });
    expect(screen.getByText('Security Review')).toBeInTheDocument();
  });

  it('renders all four KPI cards after data loads', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('kpi-critical-count')).toBeInTheDocument();
    });
    expect(screen.getByTestId('kpi-high-count')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-blocked-releases')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-pending-exceptions')).toBeInTheDocument();
  });

  it('renders KPI card labels', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByText('Critical Findings')).toBeInTheDocument();
      expect(screen.getByText('High Findings')).toBeInTheDocument();
      expect(screen.getByText('Blocked Releases')).toBeInTheDocument();
      expect(screen.getByText('Pending Exceptions')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// AC-1: Critical escalation alert
// ---------------------------------------------------------------------------

describe('SecurityReview — AC-1 critical escalation alert', () => {
  it('shows critical escalation alert when critical findings exist', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('critical-escalation-alert')).toBeInTheDocument();
    });
  });

  it('hides critical escalation alert when no critical findings exist', async () => {
    server.use(
      http.get('/api/v1/findings', () =>
        HttpResponse.json({
          items: [
            {
              id: 'fnd-high-only',
              service_id: 'svc-001',
              service_name: 'payment-service',
              dimension: 'security',
              severity: 'high',
              title: 'High severity only',
              description: 'No critical findings.',
              status: 'open',
              created_at: '2026-08-12T10:00:00Z',
            },
          ],
          cursor: null,
          total_count: 1,
        }),
      ),
      http.get('/api/v1/releases', () => HttpResponse.json(EMPTY_ESCALATIONS_PAGINATED)),
      http.get('/api/v1/exceptions', () => HttpResponse.json(EMPTY_EXCEPTIONS_PAGINATED)),
    );
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.queryByTestId('critical-escalation-alert')).not.toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// AC-3: Pending escalations section
// ---------------------------------------------------------------------------

describe('SecurityReview — AC-3 pending escalations', () => {
  it('renders the pending escalations section title', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('pending-escalations-title')).toBeInTheDocument();
    });
  });

  it('renders escalation cards for each escalated release', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('escalation-card-rel-esc-001')).toBeInTheDocument();
      expect(screen.getByTestId('escalation-card-rel-esc-002')).toBeInTheDocument();
    });
  });

  it('shows service name on escalation cards', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('escalation-service-rel-esc-001')).toHaveTextContent(
        'payment-service',
      );
    });
  });

  it('shows severity badge on escalation cards', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('escalation-severity-rel-esc-001')).toBeInTheDocument();
    });
  });

  it('shows action buttons on escalation cards', async () => {
    setupDefaultHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('escalation-review-btn-rel-esc-001')).toBeInTheDocument();
      expect(screen.getByTestId('escalation-block-btn-rel-esc-001')).toBeInTheDocument();
      expect(screen.getByTestId('escalation-override-btn-rel-esc-001')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// AC-6: Empty state
// ---------------------------------------------------------------------------

describe('SecurityReview — AC-6 empty state', () => {
  it('shows empty state when no findings returned', async () => {
    setupEmptyHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('security-empty-state')).toBeInTheDocument();
    });
  });

  it('empty state contains guidance text', async () => {
    setupEmptyHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByText('No security findings detected')).toBeInTheDocument();
    });
  });

  it('shows empty escalations state when no escalations', async () => {
    setupEmptyHandlers();
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('escalations-empty')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe('SecurityReview — loading state', () => {
  it('renders skeleton while data is loading', () => {
    server.use(
      http.get('/api/v1/findings', () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(HttpResponse.json(SECURITY_FINDINGS_PAGINATED)), 300),
        ),
      ),
      http.get('/api/v1/releases', () => HttpResponse.json(ESCALATIONS_PAGINATED)),
      http.get('/api/v1/exceptions', () => HttpResponse.json(PENDING_EXCEPTIONS_PAGINATED)),
    );
    render(<SecurityReview />);
    expect(screen.getByTestId('security-review-skeleton')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Error state
// ---------------------------------------------------------------------------

describe('SecurityReview — error state', () => {
  it('renders error alert when findings endpoint returns 500', async () => {
    server.use(
      http.get('/api/v1/findings', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
      http.get('/api/v1/releases', () => HttpResponse.json(ESCALATIONS_PAGINATED)),
      http.get('/api/v1/exceptions', () => HttpResponse.json(PENDING_EXCEPTIONS_PAGINATED)),
    );
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('security-review-error')).toBeInTheDocument();
    });
  });

  it('renders a Retry button in the error state', async () => {
    server.use(
      http.get('/api/v1/findings', () =>
        HttpResponse.json({ detail: 'Internal error' }, { status: 500 }),
      ),
      http.get('/api/v1/releases', () => HttpResponse.json(ESCALATIONS_PAGINATED)),
      http.get('/api/v1/exceptions', () => HttpResponse.json(PENDING_EXCEPTIONS_PAGINATED)),
    );
    render(<SecurityReview />);
    await waitFor(() => {
      expect(screen.getByTestId('security-retry-btn')).toBeInTheDocument();
    });
  });
});
