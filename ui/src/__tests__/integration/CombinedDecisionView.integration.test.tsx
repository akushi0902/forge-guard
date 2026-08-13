/**
 * Integration tests for the Combined Release Decision view (WO-076).
 *
 * Tests verify that the full ReleaseDecisionReviewPage renders all new
 * components correctly for each decision type using MSW.
 *
 * Scenarios:
 *   1. CONDITIONAL_APPROVE — scores row, decision banner (amber), conditions card
 *   2. APPROVE             — scores row, decision banner (green), no conditions card
 *   3. BLOCK               — scores row, decision banner (red), no conditions card
 *   4. Pending decision    — ScoresRow with 'Pending Review', no ConditionsCard
 */

import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { ReleaseDecisionReviewPage } from '@/pages/ReleaseDecisionReviewPage';
import { server } from '@/test/mocks/server';
import {
  CONDITIONAL_APPROVE_DECISION_VIEW,
  APPROVED_DECISION_VIEW,
  BLOCKED_DECISION_VIEW,
  PENDING_DECISION_VIEW,
} from '@/test/fixtures/releases';
import { useAuthStore } from '@/stores/auth-store';

// ---------------------------------------------------------------------------
// Mock react-router-dom
// ---------------------------------------------------------------------------

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: 'rel-001' }),
  };
});

// ---------------------------------------------------------------------------
// MSW lifecycle
// ---------------------------------------------------------------------------

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  vi.restoreAllMocks();
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    csrfToken: null,
  });
});
afterAll(() => server.close());

function setUser(permissions: string[]): void {
  useAuthStore.setState({
    user: {
      id: 'usr-001',
      email: 'user@example.com',
      name: 'Test User',
      role: 'tech_lead' as any,
      permissions,
    },
    isAuthenticated: true,
    isLoading: false,
    csrfToken: 'test-csrf',
  });
}

// ---------------------------------------------------------------------------
// CONDITIONAL_APPROVE scenario
// ---------------------------------------------------------------------------

describe('CombinedDecisionView — CONDITIONAL_APPROVE', () => {
  it('renders ScoresRow with correct scores', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(CONDITIONAL_APPROVE_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('scores-row')).toBeInTheDocument();
    });

    // Health score 60 → warning
    expect(screen.getByTestId('score-box-health-score')).toHaveAttribute('data-color', 'warning');
    // Risk score 45 → warning
    expect(screen.getByTestId('score-box-risk-score')).toHaveAttribute('data-color', 'warning');
    // Decision → warning
    expect(screen.getByTestId('score-box-combined-decision')).toHaveAttribute('data-color', 'warning');
  });

  it('renders DecisionBanner showing conditional approval', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(CONDITIONAL_APPROVE_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('decision-banner')).toBeInTheDocument();
    });
    expect(screen.getByText(/Conditionally Approved/i)).toBeInTheDocument();
  });

  it('renders ConditionsCard with conditions list', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(CONDITIONAL_APPROVE_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('conditions-card')).toBeInTheDocument();
    });
    expect(screen.getByText('Increase test coverage to >= 80% within 5 business days.')).toBeInTheDocument();
    expect(screen.getByText('Resolve high-severity dependency vulnerability CVE-2021-23337.')).toBeInTheDocument();
  });

  it('renders RiskFactorsCard with 4 factors', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(CONDITIONAL_APPROVE_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('risk-factors-card')).toBeInTheDocument();
    });
    expect(screen.getByTestId('risk-factor-code-complexity')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-test-coverage')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-dependency-changes')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-security-implications')).toBeInTheDocument();
  });

  it('renders ThresholdInfoSection', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(CONDITIONAL_APPROVE_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('threshold-info-section')).toBeInTheDocument();
    });
  });
});

// ---------------------------------------------------------------------------
// APPROVE scenario
// ---------------------------------------------------------------------------

describe('CombinedDecisionView — APPROVE', () => {
  it('renders green decision banner', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(APPROVED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('decision-banner')).toBeInTheDocument();
    });
    expect(screen.getByText(/Approved — Ready to Release/i)).toBeInTheDocument();
  });

  it('shows health 85 as success', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(APPROVED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('score-box-health-score')).toHaveAttribute('data-color', 'success');
    });
  });

  it('does NOT render ConditionsCard for APPROVE decision', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(APPROVED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('decision-banner')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('conditions-card')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BLOCK scenario
// ---------------------------------------------------------------------------

describe('CombinedDecisionView — BLOCK', () => {
  it('renders red decision banner', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(BLOCKED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('decision-banner')).toBeInTheDocument();
    });
    expect(screen.getByText(/Blocked — Do Not Release/i)).toBeInTheDocument();
  });

  it('shows health 40 and risk 75 as danger', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(BLOCKED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('score-box-health-score')).toHaveAttribute('data-color', 'danger');
    });
    expect(screen.getByTestId('score-box-risk-score')).toHaveAttribute('data-color', 'danger');
    expect(screen.getByTestId('score-box-combined-decision')).toHaveAttribute('data-color', 'danger');
  });

  it('does NOT render ConditionsCard for BLOCK decision', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(BLOCKED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('decision-banner')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('conditions-card')).not.toBeInTheDocument();
  });

  it('renders RiskFactorsCard with BLOCK-level severity indicators', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(BLOCKED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('risk-factors-card')).toBeInTheDocument();
    });
    // Security implications badge should show 'critical'
    const siBadge = screen.getByTestId('risk-factor-security-implications-badge');
    expect(siBadge).toHaveTextContent('critical');
  });
});

// ---------------------------------------------------------------------------
// Pending decision scenario (no decision_record yet)
// ---------------------------------------------------------------------------

describe('CombinedDecisionView — pending decision state', () => {
  it('renders ScoresRow in the pending-decision page', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('page-pending-decision')).toBeInTheDocument();
    });
    expect(screen.getByTestId('scores-row')).toBeInTheDocument();
  });

  it('does NOT render ConditionsCard in pending state (no decision)', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('page-pending-decision')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('conditions-card')).not.toBeInTheDocument();
  });

  it('renders ThresholdInfoSection in pending state', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('threshold-info-section')).toBeInTheDocument();
    });
  });

  it('renders RiskFactorsCard in pending state', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('risk-factors-card')).toBeInTheDocument();
    });
  });
});
