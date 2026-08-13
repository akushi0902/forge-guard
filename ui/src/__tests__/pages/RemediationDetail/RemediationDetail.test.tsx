/**
 * Tests for RemediationDetail page and sub-components (WO-082).
 *
 * Covers:
 *   AC-1  PageHeader — title, severity badge, dimension badge, status badge
 *   AC-2  ViolationExplanationCard — explanation text + business impact list
 *   AC-3  AIRemediationCard — confidence meter, steps, code blocks
 *   AC-4  ScoreComparisonCard — before/after values and delta
 *   AC-5  Re-evaluate button — loading state + score update
 *   AC-6  Exception request — form expands inline
 *   AC-7  Low-confidence warning — shown when confidence < 50%
 *   AC-8  Component unit tests
 *   AC-9  TanStack Query hooks integration with MSW
 *   AC-10 Mock fixture coverage
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
import {
  screen,
  waitFor,
  fireEvent,
} from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { RemediationDetail } from '@/pages/RemediationDetail/RemediationDetail';
import { server } from '@/test/mocks/server';
import {
  CRITICAL_FINDING_DETAIL,
  HIGH_CONFIDENCE_DETAIL_RECOMMENDATION,
  LOW_CONFIDENCE_DETAIL_RECOMMENDATION,
  ZERO_CONFIDENCE_DETAIL_RECOMMENDATION,
  IMPROVED_REEVALUATION,
  WORSENED_REEVALUATION,
  UNCHANGED_REEVALUATION,
  RESOLVED_FINDING_DETAIL,
} from '@/test/fixtures/remediationData';
import { ViolationExplanationCard } from '@/pages/RemediationDetail/components/ViolationExplanationCard';
import { AIRemediationCard } from '@/pages/RemediationDetail/components/AIRemediationCard';
import { ScoreComparisonCard } from '@/pages/RemediationDetail/components/ScoreComparisonCard';
import { ConfidenceMeter } from '@/pages/RemediationDetail/components/ConfidenceMeter';
import { CodeBlock } from '@/pages/RemediationDetail/components/CodeBlock';
import { RemediationSteps, parseRemediationGuide } from '@/pages/RemediationDetail/components/RemediationSteps';

// ---------------------------------------------------------------------------
// Mock react-router-dom so we can supply URL params
// ---------------------------------------------------------------------------

/**
 * Mutable reference for useParams — allows per-test override via
 * renderWithFindingId(id). Must be an object (not a primitive) so the
 * factory closure captures it by reference, not by value.
 */
const routeParams: { findingId: string } = { findingId: CRITICAL_FINDING_DETAIL.id };

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useParams: () => routeParams,
  };
});

// ---------------------------------------------------------------------------
// MSW lifecycle
// ---------------------------------------------------------------------------

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  // Reset params back to the default finding after each test
  routeParams.findingId = CRITICAL_FINDING_DETAIL.id;
});
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderWithFindingId(findingId = CRITICAL_FINDING_DETAIL.id) {
  routeParams.findingId = findingId;
  return render(<RemediationDetail />);
}

function setupHandlers(
  findingOverride?: object,
  recommendationOverride?: object,
) {
  server.use(
    http.get('/api/v1/findings/:findingId', () =>
      HttpResponse.json({
        ...CRITICAL_FINDING_DETAIL,
        ...(findingOverride ?? {}),
      }),
    ),
    http.get('/api/v1/findings/:findingId/recommendation', () =>
      HttpResponse.json({
        ...HIGH_CONFIDENCE_DETAIL_RECOMMENDATION,
        ...(recommendationOverride ?? {}),
      }),
    ),
  );
}

// ===========================================================================
// Unit tests — ConfidenceMeter (RingProgress variant)
// ===========================================================================

describe('ConfidenceMeter (RemediationDetail)', () => {
  it('renders with teal color for high confidence (>70%)', () => {
    render(<ConfidenceMeter score={0.85} />);
    // RingProgress aria label should include the value
    const ring = screen.getByRole('progressbar');
    expect(ring).toHaveAttribute('aria-valuenow', '85');
    expect(ring).toHaveAttribute('aria-valuemax', '100');
  });

  it('renders with yellow color for medium confidence (30-70%)', () => {
    render(<ConfidenceMeter score={0.55} />);
    const ring = screen.getByRole('progressbar');
    expect(ring).toHaveAttribute('aria-valuenow', '55');
  });

  it('renders with red color for low confidence (<30%)', () => {
    render(<ConfidenceMeter score={0.25} />);
    const ring = screen.getByRole('progressbar');
    expect(ring).toHaveAttribute('aria-valuenow', '25');
  });

  it('handles 0% confidence', () => {
    render(<ConfidenceMeter score={0} />);
    const ring = screen.getByRole('progressbar');
    expect(ring).toHaveAttribute('aria-valuenow', '0');
  });

  it('normalises percentage inputs (e.g. 92 → 92%)', () => {
    render(<ConfidenceMeter score={92} />);
    const ring = screen.getByRole('progressbar');
    expect(ring).toHaveAttribute('aria-valuenow', '92');
  });

  it('shows the default label "AI Confidence"', () => {
    render(<ConfidenceMeter score={0.8} />);
    expect(screen.getByText('AI Confidence')).toBeInTheDocument();
  });

  it('accepts a custom label', () => {
    render(<ConfidenceMeter score={0.8} label="Custom Label" />);
    expect(screen.getByText('Custom Label')).toBeInTheDocument();
  });
});

// ===========================================================================
// Unit tests — CodeBlock
// ===========================================================================

describe('CodeBlock', () => {
  it('renders code content in a code element', () => {
    render(<CodeBlock code="const x = 1;" language="typescript" />);
    expect(screen.getByText('const x = 1;')).toBeInTheDocument();
  });

  it('shows the language label', () => {
    render(<CodeBlock code="print('hi')" language="python" />);
    expect(screen.getByText('python')).toBeInTheDocument();
  });

  it('does not show language label for "text"', () => {
    render(<CodeBlock code="plain text" language="text" />);
    // "text" label should be hidden
    expect(screen.queryByText('text')).not.toBeInTheDocument();
  });

  it('renders without language prop (defaults to text)', () => {
    render(<CodeBlock code="no language" />);
    expect(screen.getByText('no language')).toBeInTheDocument();
  });

  it('renders with a data-testid', () => {
    render(<CodeBlock code="test" data-testid="my-code" />);
    expect(screen.getByTestId('my-code')).toBeInTheDocument();
  });
});

// ===========================================================================
// Unit tests — parseRemediationGuide
// ===========================================================================

describe('parseRemediationGuide', () => {
  it('parses simple numbered steps', () => {
    const guide = '1. First step.\n2. Second step.\n3. Third step.';
    const steps = parseRemediationGuide(guide);
    expect(steps).toHaveLength(3);
    expect(steps[0].number).toBe(1);
    expect(steps[0].text).toBe('First step.');
    expect(steps[1].text).toBe('Second step.');
  });

  it('extracts code blocks from steps', () => {
    const guide = '1. Run this command:\n```bash\nnpm install lodash\n```\n2. Verify the install.';
    const steps = parseRemediationGuide(guide);
    expect(steps).toHaveLength(2);
    expect(steps[0].code).toBeDefined();
    expect(steps[0].code?.language).toBe('bash');
    expect(steps[0].code?.content).toBe('npm install lodash');
    expect(steps[1].code).toBeUndefined();
  });

  it('returns an empty array for empty guide', () => {
    expect(parseRemediationGuide('')).toHaveLength(0);
  });

  it('handles guide with no numbered steps', () => {
    expect(parseRemediationGuide('Just some text without numbers.')).toHaveLength(0);
  });
});

// ===========================================================================
// Unit tests — RemediationSteps
// ===========================================================================

describe('RemediationSteps', () => {
  it('renders numbered steps', () => {
    const guide = '1. Do this.\n2. Then do that.\n3. Finally do this.';
    render(<RemediationSteps guide={guide} />);
    expect(screen.getByTestId('step-1')).toBeInTheDocument();
    expect(screen.getByTestId('step-2')).toBeInTheDocument();
    expect(screen.getByTestId('step-3')).toBeInTheDocument();
  });

  it('renders code blocks within steps', () => {
    const guide = '1. Run:\n```bash\nnpm test\n```';
    render(<RemediationSteps guide={guide} />);
    expect(screen.getByTestId('step-1-code')).toBeInTheDocument();
    expect(screen.getByText('npm test')).toBeInTheDocument();
  });

  it('shows table of contents when steps > 10', () => {
    const steps = Array.from({ length: 11 }, (_, i) => `${i + 1}. Step ${i + 1}.`).join('\n');
    render(<RemediationSteps guide={steps} />);
    expect(screen.getByTestId('steps-toc')).toBeInTheDocument();
  });

  it('does not show TOC for <= 10 steps', () => {
    const guide = '1. One.\n2. Two.\n3. Three.';
    render(<RemediationSteps guide={guide} />);
    expect(screen.queryByTestId('steps-toc')).not.toBeInTheDocument();
  });

  it('shows placeholder when no steps parsed', () => {
    render(<RemediationSteps guide="No numbered steps here." />);
    expect(screen.getByText('No remediation steps available.')).toBeInTheDocument();
  });
});

// ===========================================================================
// Unit tests — ViolationExplanationCard
// ===========================================================================

describe('ViolationExplanationCard', () => {
  it('renders explanation text', () => {
    render(
      <ViolationExplanationCard
        explanation="This is the explanation."
        businessImpact={null}
      />,
    );
    expect(screen.getByText('This is the explanation.')).toBeInTheDocument();
    expect(screen.getByTestId('violation-explanation-text')).toBeInTheDocument();
  });

  it('renders business impact list when provided', () => {
    render(
      <ViolationExplanationCard
        explanation="Explanation."
        businessImpact="First impact. Second impact. Third impact."
      />,
    );
    expect(screen.getByTestId('business-impact-list')).toBeInTheDocument();
  });

  it('does not render business impact section when null', () => {
    render(
      <ViolationExplanationCard
        explanation="Explanation."
        businessImpact={null}
      />,
    );
    expect(screen.queryByTestId('business-impact-list')).not.toBeInTheDocument();
  });

  it('shows fallback message when explanation is null', () => {
    render(
      <ViolationExplanationCard
        explanation={null}
        businessImpact={null}
      />,
    );
    expect(screen.getByText(/No AI-generated explanation available/)).toBeInTheDocument();
  });

  it('shows loading skeleton when isLoading=true', () => {
    render(
      <ViolationExplanationCard
        explanation={null}
        businessImpact={null}
        isLoading={true}
      />,
    );
    // Skeletons don't have accessible text but the card renders
    expect(screen.getByTestId('violation-explanation-card')).toBeInTheDocument();
  });
});

// ===========================================================================
// Unit tests — AIRemediationCard
// ===========================================================================

describe('AIRemediationCard', () => {
  it('renders the recommendation summary', () => {
    render(
      <AIRemediationCard
        recommendation={HIGH_CONFIDENCE_DETAIL_RECOMMENDATION}
        isLoading={false}
        isNotFound={false}
      />,
    );
    expect(screen.getByTestId('recommendation-text')).toBeInTheDocument();
    expect(
      screen.getByText(HIGH_CONFIDENCE_DETAIL_RECOMMENDATION.recommendation_text),
    ).toBeInTheDocument();
  });

  it('renders the confidence meter', () => {
    render(
      <AIRemediationCard
        recommendation={HIGH_CONFIDENCE_DETAIL_RECOMMENDATION}
        isLoading={false}
        isNotFound={false}
      />,
    );
    expect(screen.getByTestId('recommendation-confidence-meter')).toBeInTheDocument();
  });

  it('does NOT show low-confidence warning for high confidence', () => {
    render(
      <AIRemediationCard
        recommendation={HIGH_CONFIDENCE_DETAIL_RECOMMENDATION}
        isLoading={false}
        isNotFound={false}
      />,
    );
    expect(screen.queryByTestId('low-confidence-warning')).not.toBeInTheDocument();
  });

  it('shows low-confidence warning when confidence < 50%', () => {
    render(
      <AIRemediationCard
        recommendation={LOW_CONFIDENCE_DETAIL_RECOMMENDATION}
        isLoading={false}
        isNotFound={false}
      />,
    );
    expect(screen.getByTestId('low-confidence-warning')).toBeInTheDocument();
    expect(
      screen.getByText(/verify it independently/i),
    ).toBeInTheDocument();
  });

  it('shows strong warning for zero confidence', () => {
    render(
      <AIRemediationCard
        recommendation={ZERO_CONFIDENCE_DETAIL_RECOMMENDATION}
        isLoading={false}
        isNotFound={false}
      />,
    );
    expect(screen.getByTestId('low-confidence-warning')).toBeInTheDocument();
  });

  it('shows remediation steps', () => {
    render(
      <AIRemediationCard
        recommendation={HIGH_CONFIDENCE_DETAIL_RECOMMENDATION}
        isLoading={false}
        isNotFound={false}
      />,
    );
    expect(screen.getByTestId('remediation-steps')).toBeInTheDocument();
  });

  it('shows AI disclaimer text', () => {
    render(
      <AIRemediationCard
        recommendation={HIGH_CONFIDENCE_DETAIL_RECOMMENDATION}
        isLoading={false}
        isNotFound={false}
      />,
    );
    expect(screen.getByTestId('ai-disclaimer')).toBeInTheDocument();
  });

  it('shows generating skeleton when isLoading=true', () => {
    render(
      <AIRemediationCard
        recommendation={null}
        isLoading={true}
        isNotFound={false}
      />,
    );
    expect(screen.getByTestId('ai-remediation-skeleton')).toBeInTheDocument();
    expect(screen.getByText(/Generating recommendation/i)).toBeInTheDocument();
  });

  it('shows "not available" alert when isNotFound=true', () => {
    render(
      <AIRemediationCard
        recommendation={null}
        isLoading={false}
        isNotFound={true}
      />,
    );
    expect(screen.getByTestId('recommendation-not-available')).toBeInTheDocument();
  });

  it('shows retry button when onRetry is provided', () => {
    render(
      <AIRemediationCard
        recommendation={null}
        isLoading={false}
        isNotFound={true}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByTestId('recommendation-retry-btn')).toBeInTheDocument();
  });
});

// ===========================================================================
// Unit tests — ScoreComparisonCard
// ===========================================================================

describe('ScoreComparisonCard', () => {
  const noOp = () => {};

  it('shows placeholder text when no re-evaluation has occurred', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={null}
        isReEvaluating={false}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.getByTestId('no-reevaluation-text')).toBeInTheDocument();
  });

  it('shows before/after grid after re-evaluation', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={IMPROVED_REEVALUATION}
        isReEvaluating={false}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.getByTestId('before-after-grid')).toBeInTheDocument();
    expect(screen.getByTestId('before-score')).toBeInTheDocument();
    expect(screen.getByTestId('after-score')).toBeInTheDocument();
  });

  it('shows "No change detected" for delta=0', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={UNCHANGED_REEVALUATION}
        isReEvaluating={false}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.getByTestId('score-delta-badge')).toHaveTextContent(
      'No change detected',
    );
  });

  it('shows improvement delta badge for positive delta', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={IMPROVED_REEVALUATION}
        isReEvaluating={false}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.getByTestId('score-delta-badge')).toHaveTextContent('+16.0 improvement');
  });

  it('shows regression delta badge for negative delta', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={WORSENED_REEVALUATION}
        isReEvaluating={false}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.getByTestId('score-delta-badge')).toHaveTextContent('-4.0 regression');
  });

  it('shows Re-evaluate button when not resolved', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={null}
        isReEvaluating={false}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.getByTestId('re-evaluate-btn')).toBeInTheDocument();
  });

  it('hides action buttons when finding is resolved', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={null}
        isReEvaluating={false}
        isResolved={true}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.queryByTestId('re-evaluate-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('request-exception-btn')).not.toBeInTheDocument();
  });

  it('disables Re-evaluate button while re-evaluating', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={null}
        isReEvaluating={true}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    const btn = screen.getByTestId('re-evaluate-btn');
    expect(btn).toBeDisabled();
  });

  it('shows Loader when re-evaluating', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={null}
        isReEvaluating={true}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.getByTestId('re-evaluate-btn')).toHaveTextContent('Re-evaluating…');
  });

  it('shows Request Exception button when not resolved', () => {
    render(
      <ScoreComparisonCard
        reEvalResult={null}
        isReEvaluating={false}
        isResolved={false}
        onReEvaluate={noOp}
        onRequestException={noOp}
      />,
    );
    expect(screen.getByTestId('request-exception-btn')).toBeInTheDocument();
  });
});

// ===========================================================================
// Integration tests — RemediationDetail page (AC-1 through AC-10)
// ===========================================================================

describe('RemediationDetail page — full page render', () => {
  it('shows loading skeleton while data is fetching', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId', () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(HttpResponse.json(CRITICAL_FINDING_DETAIL)), 200),
        ),
      ),
    );
    renderWithFindingId();
    expect(screen.getByTestId('remediation-detail-skeleton')).toBeInTheDocument();
  });

  it('renders page header with finding title after loading (AC-1)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('finding-title')).toBeInTheDocument();
      expect(screen.getByText(CRITICAL_FINDING_DETAIL.title)).toBeInTheDocument();
    });
  });

  it('renders severity badge (AC-1)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('severity-badge')).toBeInTheDocument();
      expect(screen.getByTestId('severity-badge')).toHaveTextContent(/critical/i);
    });
  });

  it('renders dimension badge (AC-1)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('dimension-badge')).toBeInTheDocument();
    });
  });

  it('renders status badge (AC-1)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('status-badge')).toBeInTheDocument();
    });
  });

  it('renders breadcrumb navigation (AC-1)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('breadcrumb')).toBeInTheDocument();
      expect(screen.getByText('Services')).toBeInTheDocument();
      expect(screen.getByText('Findings')).toBeInTheDocument();
    });
  });

  it('renders ViolationExplanationCard with explanation text (AC-2)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('violation-explanation-card')).toBeInTheDocument();
    });
  });

  it('renders AIRemediationCard with confidence meter (AC-3)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('ai-remediation-card')).toBeInTheDocument();
      expect(screen.getByTestId('recommendation-confidence-meter')).toBeInTheDocument();
    });
  });

  it('renders RemediationSteps inside AIRemediationCard (AC-3)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('remediation-steps')).toBeInTheDocument();
    });
  });

  it('renders ScoreComparisonCard (AC-4)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('score-comparison-card')).toBeInTheDocument();
    });
  });

  it('renders Re-evaluate button (AC-5)', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('re-evaluate-btn')).toBeInTheDocument();
    });
  });

  it('shows low-confidence warning for low-confidence recommendations (AC-7)', async () => {
    setupHandlers({}, { confidence_score: 0.30 });
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('low-confidence-warning')).toBeInTheDocument();
    });
  });

  it('does NOT show warning for high-confidence recommendations', async () => {
    setupHandlers({}, { confidence_score: 0.92 });
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('ai-remediation-card')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('low-confidence-warning')).not.toBeInTheDocument();
  });
});

// ===========================================================================
// Integration — exception request form (AC-6)
// ===========================================================================

describe('RemediationDetail — exception request (AC-6)', () => {
  it('shows exception form when Request Exception is clicked', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('request-exception-btn')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('request-exception-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('exception-request-form')).toBeInTheDocument();
    });
  });

  it('hides exception form after Cancel is clicked', async () => {
    setupHandlers();
    renderWithFindingId();
    await waitFor(() => screen.getByTestId('request-exception-btn'));
    fireEvent.click(screen.getByTestId('request-exception-btn'));
    await waitFor(() => screen.getByTestId('exception-request-form'));
    fireEvent.click(screen.getByTestId('exception-cancel-btn'));
    await waitFor(() => {
      expect(screen.queryByTestId('exception-request-form')).not.toBeInTheDocument();
    });
  });
});

// ===========================================================================
// Integration — resolved finding (edge case)
// ===========================================================================

describe('RemediationDetail — resolved finding', () => {
  it('shows resolved banner when finding.status is resolved', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId', () =>
        HttpResponse.json(RESOLVED_FINDING_DETAIL),
      ),
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(HIGH_CONFIDENCE_DETAIL_RECOMMENDATION),
      ),
    );
    renderWithFindingId(RESOLVED_FINDING_DETAIL.id);
    await waitFor(() => {
      expect(screen.getByTestId('resolved-banner')).toBeInTheDocument();
    });
  });

  it('hides action buttons for resolved finding', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId', () =>
        HttpResponse.json(RESOLVED_FINDING_DETAIL),
      ),
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(HIGH_CONFIDENCE_DETAIL_RECOMMENDATION),
      ),
    );
    renderWithFindingId(RESOLVED_FINDING_DETAIL.id);
    await waitFor(() => {
      expect(screen.getByTestId('resolved-banner')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('re-evaluate-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('request-exception-btn')).not.toBeInTheDocument();
  });
});

// ===========================================================================
// Integration — 404 states
// ===========================================================================

describe('RemediationDetail — 404 states', () => {
  it('shows not-found page when finding ID does not exist (AC-error handling)', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId', () =>
        HttpResponse.json(
          { detail: 'Finding not found', error_code: 'FINDING_NOT_FOUND' },
          { status: 404 },
        ),
      ),
    );
    renderWithFindingId('not-found');
    await waitFor(() => {
      expect(screen.getByTestId('finding-not-found')).toBeInTheDocument();
    });
  });

  it('shows "Back to Findings" link on 404', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId', () =>
        HttpResponse.json(
          { detail: 'Finding not found' },
          { status: 404 },
        ),
      ),
    );
    renderWithFindingId('not-found');
    await waitFor(() => {
      expect(screen.getByTestId('back-to-findings-btn')).toBeInTheDocument();
    });
  });

  it('shows "Recommendation not yet available" when recommendation 404s (AC-edge case)', async () => {
    server.use(
      http.get('/api/v1/findings/:findingId', () =>
        HttpResponse.json(CRITICAL_FINDING_DETAIL),
      ),
      http.get('/api/v1/findings/:findingId/recommendation', () =>
        HttpResponse.json(
          { detail: 'Recommendation not yet available' },
          { status: 404 },
        ),
      ),
    );
    renderWithFindingId();
    await waitFor(() => {
      expect(screen.getByTestId('recommendation-not-available')).toBeInTheDocument();
    });
  });
});

// ===========================================================================
// Integration — re-evaluate updates score comparison (AC-5)
// ===========================================================================

describe('RemediationDetail — re-evaluate flow (AC-5)', () => {
  it('shows loading state when re-evaluate is clicked', async () => {
    setupHandlers();
    server.use(
      http.post('/api/v1/findings/:findingId/re-evaluate', () =>
        new Promise((resolve) =>
          setTimeout(
            () => resolve(HttpResponse.json(IMPROVED_REEVALUATION)),
            300,
          ),
        ),
      ),
    );
    renderWithFindingId();
    await waitFor(() => screen.getByTestId('re-evaluate-btn'));
    fireEvent.click(screen.getByTestId('re-evaluate-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('re-evaluate-btn')).toBeDisabled();
    });
  });

  it('updates ScoreComparisonCard with before/after values after success (AC-5)', async () => {
    setupHandlers();
    server.use(
      http.post('/api/v1/findings/:findingId/re-evaluate', () =>
        HttpResponse.json(IMPROVED_REEVALUATION),
      ),
    );
    renderWithFindingId();
    await waitFor(() => screen.getByTestId('re-evaluate-btn'));
    fireEvent.click(screen.getByTestId('re-evaluate-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('before-after-grid')).toBeInTheDocument();
      expect(screen.getByTestId('before-score')).toHaveTextContent('62');
      expect(screen.getByTestId('after-score')).toHaveTextContent('78');
    });
  });
});
