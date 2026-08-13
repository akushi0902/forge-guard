/**
 * Component tests for PolicyConfiguration page (WO-079).
 *
 * Covers: tab navigation, rules table rendering, filter bar,
 * CreateRuleModal form validation, dimension weight validation,
 * threshold card rendering, empty state, and RBAC guard.
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
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { PolicyConfiguration } from '@/pages/PolicyConfiguration';
import { server } from '@/test/mocks/server';
import {
  POLICY_RULES_RESPONSE_FIXTURE,
  DIMENSION_WEIGHTS_FIXTURE,
  SCORE_THRESHOLDS_FIXTURE,
} from '@/test/fixtures/policyData';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Helper: render the page with platform_admin permissions in auth store
function renderPage() {
  // Inject a mock user with policy.manage permission via auth store
  // The RoleGuard reads from useAuthStore — we override via Zustand in test
  const { useAuthStore } = require('@/stores/auth-store');
  useAuthStore.setState({
    user: {
      id: 'usr-001',
      email: 'admin@example.com',
      name: 'Platform Admin',
      role: 'platform_admin',
      permissions: ['policy.manage', 'service.view'],
    },
    isAuthenticated: true,
    isLoading: false,
    csrfToken: null,
  });
  return render(<PolicyConfiguration />);
}

describe('PolicyConfiguration — tab navigation', () => {
  it('renders three tabs: Policy Rules, Dimensions, Score Thresholds', () => {
    renderPage();
    expect(screen.getByTestId('tab-rules')).toBeInTheDocument();
    expect(screen.getByTestId('tab-dimensions')).toBeInTheDocument();
    expect(screen.getByTestId('tab-thresholds')).toBeInTheDocument();
  });

  it('shows Policy Rules tab by default', () => {
    renderPage();
    expect(screen.getByTestId('policy-rules-panel')).toBeInTheDocument();
  });

  it('switches to Dimensions tab on click', async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-dimensions'));
    await waitFor(() =>
      expect(screen.getByTestId('dimensions-panel')).toBeInTheDocument(),
    );
  });

  it('switches to Score Thresholds tab on click', async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-thresholds'));
    await waitFor(() =>
      expect(screen.getByTestId('score-thresholds-panel')).toBeInTheDocument(),
    );
  });
});

describe('PolicyConfiguration — RBAC guard', () => {
  it('renders ForbiddenPage for user without policy.manage', () => {
    const { useAuthStore } = require('@/stores/auth-store');
    useAuthStore.setState({
      user: {
        id: 'usr-002',
        email: 'dev@example.com',
        name: 'Developer',
        role: 'developer',
        permissions: ['service.view'],
      },
      isAuthenticated: true,
      isLoading: false,
      csrfToken: null,
    });
    render(<PolicyConfiguration />);
    expect(screen.queryByTestId('policy-tabs')).not.toBeInTheDocument();
  });
});

describe('PolicyConfiguration — Policy Rules tab', () => {
  it('renders the filter bar', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId('filter-bar')).toBeInTheDocument(),
    );
  });

  it('renders policy rules from API', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId('rules-table')).toBeInTheDocument(),
    );
    // At least one rule from fixture
    expect(
      screen.getByText('No critical SQL injection vulnerabilities'),
    ).toBeInTheDocument();
  });

  it('shows empty state when no rules exist', async () => {
    server.use(
      http.get('/api/v1/policies', () =>
        HttpResponse.json({ items: [], cursor: null, total: 0 }),
      ),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId('empty-state')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('create-first-rule-btn')).toBeInTheDocument();
  });

  it('opens CreateRuleModal when Create Rule is clicked', async () => {
    renderPage();
    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByTestId('create-rule-btn')).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId('create-rule-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('create-rule-modal')).toBeInTheDocument(),
    );
  });
});

describe('CreateRuleModal — form validation', () => {
  async function openModal() {
    renderPage();
    const user = userEvent.setup();
    await waitFor(() =>
      expect(screen.getByTestId('create-rule-btn')).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId('create-rule-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('create-rule-form')).toBeInTheDocument(),
    );
    return user;
  }

  it('shows validation errors on empty submit', async () => {
    const user = await openModal();
    await user.click(screen.getByTestId('submit-btn'));
    await waitFor(() => {
      expect(screen.getByText(/Name must be at least 3 characters/)).toBeInTheDocument();
    });
  });

  it('shows error when name is too short', async () => {
    const user = await openModal();
    await user.type(screen.getByTestId('field-name'), 'AB');
    await user.click(screen.getByTestId('submit-btn'));
    await waitFor(() =>
      expect(screen.getByText(/Name must be at least 3 characters/)).toBeInTheDocument(),
    );
  });

  it('shows 409 conflict error on duplicate name', async () => {
    server.use(
      http.post('/api/v1/policies', () =>
        HttpResponse.json(
          { detail: 'A policy rule with this name already exists.', error_code: 'DUPLICATE_NAME' },
          { status: 409 },
        ),
      ),
    );
    const user = await openModal();
    await user.type(screen.getByTestId('field-name'), 'Duplicate Rule Name');
    await user.click(screen.getByTestId('submit-btn'));
    await waitFor(() =>
      expect(screen.getByText(/A rule with this name already exists/)).toBeInTheDocument(),
    );
  });
});

describe('DimensionsPanel', () => {
  it('renders five dimension rows', async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-dimensions'));
    await waitFor(() =>
      expect(screen.getByTestId('dimensions-panel')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('dimension-row-security')).toBeInTheDocument();
    expect(screen.getByTestId('dimension-row-test_coverage')).toBeInTheDocument();
    expect(screen.getByTestId('dimension-row-code_quality')).toBeInTheDocument();
    expect(screen.getByTestId('dimension-row-documentation')).toBeInTheDocument();
    expect(screen.getByTestId('dimension-row-operations_readiness')).toBeInTheDocument();
  });

  it('shows weight total from fixture (sums to 100)', async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-dimensions'));
    await waitFor(() =>
      expect(screen.getByTestId('weights-total')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('weights-total')).toHaveTextContent('100%');
  });

  it('disables save button when total != 100', async () => {
    // Return weights that don't sum to 100
    server.use(
      http.get('/api/v1/policies/dimensions', () =>
        HttpResponse.json([
          { dimension: 'security', weight: 50 },
          { dimension: 'test_coverage', weight: 10 },
          { dimension: 'code_quality', weight: 10 },
          { dimension: 'documentation', weight: 10 },
          { dimension: 'operations_readiness', weight: 10 },
        ]),
      ),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-dimensions'));
    await waitFor(() =>
      expect(screen.getByTestId('save-weights-btn')).toBeDisabled(),
    );
    expect(screen.getByTestId('weights-validation-alert')).toBeInTheDocument();
  });
});

describe('ScoreThresholdsPanel', () => {
  it('renders three threshold cards', async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-thresholds'));
    await waitFor(() => {
      expect(screen.getByTestId('approve-threshold-card')).toBeInTheDocument();
      expect(screen.getByTestId('conditional-threshold-card')).toBeInTheDocument();
      expect(screen.getByTestId('block-explanation-card')).toBeInTheDocument();
    });
  });

  it('save button is enabled when thresholds are valid', async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByTestId('tab-thresholds'));
    await waitFor(() =>
      expect(screen.getByTestId('save-thresholds-btn')).not.toBeDisabled(),
    );
  });
});
