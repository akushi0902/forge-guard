/**
 * Unit + integration tests for ReleaseDecisionReviewPage (WO-075).
 *
 * Unit tests:
 *   - Renders correctly for each state (loading, processing, pending-decision, decided)
 *   - Conditional button rendering per role
 *   - Escalation banner visibility
 *
 * Integration test:
 *   - Full flow: render with MSW pending data → enter rationale → click Approve
 *     → confirm modal → verify mutation called with correct body
 *     → verify page transitions to decided state with DecisionBanner
 */

import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { ReleaseDecisionReviewPage } from '@/pages/ReleaseDecisionReviewPage';
import { server } from '@/test/mocks/server';
import {
  PENDING_DECISION_VIEW,
  APPROVED_DECISION_VIEW,
  BLOCKED_DECISION_VIEW,
  ESCALATED_DECISION_VIEW,
  PROCESSING_DECISION_VIEW,
} from '@/test/fixtures/releases';
import { useAuthStore } from '@/stores/auth-store';

// ---------------------------------------------------------------------------
// Mock react-router-dom so we can supply URL params
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
  // Reset auth store between tests
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    csrfToken: null,
  });
});
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Helper: set auth store user with given permissions
// ---------------------------------------------------------------------------

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
// Unit tests — rendering states
// ---------------------------------------------------------------------------

describe('ReleaseDecisionReviewPage — loading state', () => {
  it('shows loading indicator while fetching', async () => {
    // Keep the request pending
    server.use(
      http.get('/api/v1/releases/:id/decision', () => new Promise(() => {})),
    );
    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);
    expect(screen.getByTestId('page-loading')).toBeInTheDocument();
  });
});

describe('ReleaseDecisionReviewPage — error state', () => {
  it('shows error when fetch fails', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json({ detail: 'Assessment not found' }, { status: 404 }),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('page-error')).toBeInTheDocument();
    });
  });

  it('shows retry button on error', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });
});

describe('ReleaseDecisionReviewPage — processing state', () => {
  it('shows processing state when assessment is pending', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PROCESSING_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('processing-state')).toBeInTheDocument();
    });
  });
});

describe('ReleaseDecisionReviewPage — pending-decision state', () => {
  it('renders assessment metadata', async () => {
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
    expect(screen.getByTestId('assessment-metadata')).toBeInTheDocument();
  });

  it('renders Risk Score card', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('risk-score-card')).toBeInTheDocument();
    });
  });

  it('renders findings table', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('findings-section')).toBeInTheDocument();
    });
  });

  it('shows Approve and Block buttons for Tech Lead (both permissions)', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('approve-btn')).toBeInTheDocument();
      expect(screen.getByTestId('block-btn')).toBeInTheDocument();
    });
  });

  it('shows only Approve button for approve-only permission', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('approve-btn')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('block-btn')).not.toBeInTheDocument();
  });

  it('shows only Block button for block-only permission', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.block']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('block-btn')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('approve-btn')).not.toBeInTheDocument();
  });

  it('shows read-only message for Developer (no decision permissions)', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('decision-card-readonly')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('approve-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('block-btn')).not.toBeInTheDocument();
  });

  it('shows escalation banner for escalated assessments', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(ESCALATED_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('escalation-banner')).toBeInTheDocument();
    });
    expect(screen.getByText(/security escalation/i)).toBeInTheDocument();
  });
});

describe('ReleaseDecisionReviewPage — decided state', () => {
  it('renders DecisionBanner for APPROVED assessment', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(APPROVED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('page-decided')).toBeInTheDocument();
    });
    expect(screen.getByTestId('decision-banner')).toBeInTheDocument();
  });

  it('shows APPROVED banner text', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(APPROVED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByText(/approved — ready to release/i)).toBeInTheDocument();
    });
  });

  it('renders DecisionBanner for BLOCKED assessment', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(BLOCKED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('decision-banner')).toBeInTheDocument();
      expect(screen.getByText(/blocked — do not release/i)).toBeInTheDocument();
    });
  });

  it('shows decision rationale in read-only card', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(APPROVED_DECISION_VIEW),
      ),
    );
    setUser(['service.view']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('decision-rationale')).toBeInTheDocument();
    });
    expect(screen.getByTestId('decision-rationale')).toHaveTextContent(
      APPROVED_DECISION_VIEW.decision_record!.rationale!,
    );
  });

  it('does not show decision form in decided state', async () => {
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(APPROVED_DECISION_VIEW),
      ),
    );
    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);
    await waitFor(() => {
      expect(screen.getByTestId('page-decided')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('decision-card')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Integration test — full approve flow
// ---------------------------------------------------------------------------

describe('ReleaseDecisionReviewPage — integration: approve flow', () => {
  it('enters rationale, opens ApproveModal, confirms, page transitions to decided state', async () => {
    const requestBodies: unknown[] = [];

    // Step 1: return pending view
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
      http.post('/api/v1/releases/:id/decide', async ({ request }) => {
        requestBodies.push(await request.json());
        return HttpResponse.json(
          {
            id: 'dec-new',
            release_assessment_id: 'rel-001',
            health_score_at_decision: 78,
            risk_score_at_decision: 42,
            decision: 'APPROVE',
            decided_by_role: 'tech_lead',
            decided_by: null,
            rationale: 'All critical issues resolved.',
            comment: null,
            was_escalated: false,
            escalation_reasons: [],
            original_recommendation: null,
            created_at: '2026-08-11T11:00:00Z',
          },
          { status: 201 },
        );
      }),
    );

    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);

    // Wait for the page to load
    await waitFor(() => {
      expect(screen.getByTestId('page-pending-decision')).toBeInTheDocument();
    });

    // Type rationale
    const rationaleInput = screen.getByTestId('rationale-textarea');
    await userEvent.type(rationaleInput, 'All critical issues resolved. Safe to release.');

    // Wait for buttons to be enabled
    await waitFor(() => {
      expect(screen.getByTestId('approve-btn')).not.toBeDisabled();
    });

    // Click Approve
    await userEvent.click(screen.getByTestId('approve-btn'));

    // ApproveModal should open
    await waitFor(() => {
      expect(screen.getByTestId('approve-modal')).toBeInTheDocument();
    });

    // Step 2: after confirm, refetch returns decided view
    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(APPROVED_DECISION_VIEW),
      ),
    );

    // Click Confirm
    await userEvent.click(screen.getByTestId('approve-modal-confirm'));

    // Verify mutation was called with correct body
    await waitFor(() => {
      expect(requestBodies.length).toBe(1);
    });
    expect(requestBodies[0]).toMatchObject({
      decision: 'APPROVE',
      rationale: 'All critical issues resolved. Safe to release.',
    });

    // Page should transition to decided state
    await waitFor(() => {
      expect(screen.getByTestId('page-decided')).toBeInTheDocument();
    });
    expect(screen.getByTestId('decision-banner')).toBeInTheDocument();
  });

  it('enters rationale, opens BlockModal, confirms, mutation called with BLOCK', async () => {
    const requestBodies: unknown[] = [];

    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(PENDING_DECISION_VIEW),
      ),
      http.post('/api/v1/releases/:id/decide', async ({ request }) => {
        requestBodies.push(await request.json());
        return HttpResponse.json(
          {
            id: 'dec-new',
            release_assessment_id: 'rel-001',
            health_score_at_decision: 78,
            risk_score_at_decision: 42,
            decision: 'BLOCK',
            decided_by_role: 'tech_lead',
            decided_by: null,
            rationale: 'High risk — blocking for now.',
            comment: null,
            was_escalated: false,
            escalation_reasons: [],
            original_recommendation: null,
            created_at: '2026-08-11T11:00:00Z',
          },
          { status: 201 },
        );
      }),
    );

    setUser(['service.view', 'release.approve', 'release.block']);
    render(<ReleaseDecisionReviewPage />);

    await waitFor(() => {
      expect(screen.getByTestId('page-pending-decision')).toBeInTheDocument();
    });

    await userEvent.type(
      screen.getByTestId('rationale-textarea'),
      'High risk — blocking for now.',
    );
    await waitFor(() => {
      expect(screen.getByTestId('block-btn')).not.toBeDisabled();
    });

    await userEvent.click(screen.getByTestId('block-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('block-modal')).toBeInTheDocument();
    });

    server.use(
      http.get('/api/v1/releases/:id/decision', () =>
        HttpResponse.json(BLOCKED_DECISION_VIEW),
      ),
    );

    await userEvent.click(screen.getByTestId('block-modal-confirm'));

    await waitFor(() => {
      expect(requestBodies.length).toBe(1);
    });
    expect(requestBodies[0]).toMatchObject({
      decision: 'BLOCK',
      rationale: 'High risk — blocking for now.',
    });

    await waitFor(() => {
      expect(screen.getByTestId('page-decided')).toBeInTheDocument();
    });
  });
});
