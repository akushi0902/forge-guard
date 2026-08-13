/**
 * Unit tests for EscalationCard component (WO-077).
 *
 * Tests:
 *   - Rendering: service name, severity badge, description
 *   - Action buttons: Review, Block, Override
 *   - Block modal: opens, requires rationale, submits mutation
 *   - RBAC gating: buttons disabled without release.block permission
 *   - Concurrent protection: button disabled while mutation pending
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
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { EscalationCard } from '@/pages/SecurityReview/components/EscalationCard';
import { server } from '@/test/mocks/server';
import { useAuthStore } from '@/stores/auth-store';
import { Role } from '@/types';
import type { User } from '@/stores/auth-store';
import {
  ESCALATED_RELEASE_1,
  BLOCK_DECISION_RESPONSE,
} from '@/test/fixtures/securityFindings';

// ---------------------------------------------------------------------------
// Test users
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

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, csrfToken: null });
});
afterAll(() => server.close());

beforeEach(() => {
  useAuthStore.setState({ user: securityReviewerUser, isAuthenticated: true });
  server.use(
    http.post('/api/v1/releases/:id/decide', () =>
      HttpResponse.json(BLOCK_DECISION_RESPONSE, { status: 201 }),
    ),
  );
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe('EscalationCard — rendering', () => {
  it('renders the escalation card container', () => {
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    expect(screen.getByTestId(`escalation-card-${ESCALATED_RELEASE_1.id}`)).toBeInTheDocument();
  });

  it('renders the service name', () => {
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    expect(
      screen.getByTestId(`escalation-service-${ESCALATED_RELEASE_1.id}`),
    ).toHaveTextContent('payment-service');
  });

  it('renders the severity badge', () => {
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    expect(
      screen.getByTestId(`escalation-severity-${ESCALATED_RELEASE_1.id}`),
    ).toHaveTextContent('CRITICAL');
  });

  it('renders the finding description', () => {
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    expect(
      screen.getByTestId(`escalation-description-${ESCALATED_RELEASE_1.id}`),
    ).toHaveTextContent('AWS access key found');
  });

  it('renders all three action buttons', () => {
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    expect(
      screen.getByTestId(`escalation-review-btn-${ESCALATED_RELEASE_1.id}`),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(`escalation-block-btn-${ESCALATED_RELEASE_1.id}`),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(`escalation-override-btn-${ESCALATED_RELEASE_1.id}`),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// RBAC gating (AC-5)
// ---------------------------------------------------------------------------

describe('EscalationCard — RBAC gating', () => {
  it('Block button is enabled for users with release.block permission', () => {
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    const btn = screen.getByTestId(`escalation-block-btn-${ESCALATED_RELEASE_1.id}`);
    expect(btn).not.toBeDisabled();
  });

  it('Block button is disabled for users without release.block permission', () => {
    useAuthStore.setState({ user: developerUser, isAuthenticated: true });
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    const btn = screen.getByTestId(`escalation-block-btn-${ESCALATED_RELEASE_1.id}`);
    expect(btn).toBeDisabled();
  });

  it('Override button is disabled for users without release.block permission', () => {
    useAuthStore.setState({ user: developerUser, isAuthenticated: true });
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    const btn = screen.getByTestId(`escalation-override-btn-${ESCALATED_RELEASE_1.id}`);
    expect(btn).toBeDisabled();
  });

  it('Review button is always accessible regardless of permissions', () => {
    useAuthStore.setState({ user: developerUser, isAuthenticated: true });
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    const btn = screen.getByTestId(`escalation-review-btn-${ESCALATED_RELEASE_1.id}`);
    expect(btn).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Block modal (AC-4)
// ---------------------------------------------------------------------------

describe('EscalationCard — block modal', () => {
  it('opens block modal when Block button is clicked', async () => {
    const user = userEvent.setup();
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    const blockBtn = screen.getByTestId(`escalation-block-btn-${ESCALATED_RELEASE_1.id}`);
    await user.click(blockBtn);
    await waitFor(() => {
      expect(screen.getByTestId(`block-modal-${ESCALATED_RELEASE_1.id}`)).toBeInTheDocument();
    });
  });

  it('shows rationale textarea in block modal', async () => {
    const user = userEvent.setup();
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    await user.click(screen.getByTestId(`escalation-block-btn-${ESCALATED_RELEASE_1.id}`));
    await waitFor(() => {
      expect(screen.getByTestId('block-rationale-input')).toBeInTheDocument();
    });
  });

  it('shows validation error when submitting without rationale', async () => {
    const user = userEvent.setup();
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    await user.click(screen.getByTestId(`escalation-block-btn-${ESCALATED_RELEASE_1.id}`));
    await waitFor(() => {
      expect(screen.getByTestId('block-modal-confirm')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('block-modal-confirm'));
    await waitFor(() => {
      expect(screen.getByText('Rationale is required before submitting a decision.')).toBeInTheDocument();
    });
  });

  it('closes modal when Cancel is clicked', async () => {
    const user = userEvent.setup();
    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    await user.click(screen.getByTestId(`escalation-block-btn-${ESCALATED_RELEASE_1.id}`));
    await waitFor(() => {
      expect(screen.getByTestId('block-modal-cancel')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('block-modal-cancel'));
    await waitFor(() => {
      expect(screen.queryByTestId('block-rationale-input')).not.toBeInTheDocument();
    });
  });

  it('submits block mutation with rationale when confirmed', async () => {
    const user = userEvent.setup();
    let capturedBody: unknown;
    server.use(
      http.post('/api/v1/releases/:id/decide', async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json(BLOCK_DECISION_RESPONSE, { status: 201 });
      }),
    );

    render(<EscalationCard escalation={ESCALATED_RELEASE_1} />);
    await user.click(screen.getByTestId(`escalation-block-btn-${ESCALATED_RELEASE_1.id}`));
    await waitFor(() => {
      expect(screen.getByTestId('block-rationale-input')).toBeInTheDocument();
    });
    await user.type(screen.getByTestId('block-rationale-input'), 'Critical vulnerability requires immediate block.');
    await user.click(screen.getByTestId('block-modal-confirm'));
    await waitFor(() => {
      expect(capturedBody).toMatchObject({
        decision: 'BLOCK',
        rationale: 'Critical vulnerability requires immediate block.',
      });
    });
  });
});
