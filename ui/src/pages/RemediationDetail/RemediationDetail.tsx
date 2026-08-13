/**
 * RemediationDetail page — detailed view for a single finding with AI
 * remediation guidance (WO-082).
 *
 * Route: /findings/:findingId
 *
 * Lifecycle sections:
 *   1. PageHeader         — breadcrumb, title, severity/dimension/status badges
 *   2. ResolvedBanner     — shown when finding.status === 'resolved'
 *   3. ViolationExplanationCard — AI explanation + business impact
 *   4. AIRemediationCard  — confidence meter + steps + code blocks + disclaimer
 *   5. ScoreComparisonCard — before/after health score + action buttons
 *   6. ExceptionRequestSection — collapsible form (WOREF-083)
 */

import {
  Alert,
  Anchor,
  Badge,
  Breadcrumbs,
  Button,
  Container,
  Divider,
  Group,
  Skeleton,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core';
import { type JSX, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { useFinding, useFindingRemediation } from '@/hooks/api/useFinding';
import { useReEvaluate } from '@/hooks/api/useReEvaluate';
import { useRequestException } from '@/hooks/api/useRemediation';
import { type ReEvaluationResult } from '@/types/api';
import { showToast } from '@/components/shared/AlertsAndToasts';
import { AIRemediationCard } from './components/AIRemediationCard';
import { ScoreComparisonCard } from './components/ScoreComparisonCard';
import { ViolationExplanationCard } from './components/ViolationExplanationCard';

// ---------------------------------------------------------------------------
// Severity badge helper
// ---------------------------------------------------------------------------

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'yellow',
  low: 'blue',
  info: 'gray',
};

function SeverityBadge({ severity }: { severity: string }): JSX.Element {
  return (
    <Badge
      color={SEVERITY_COLOR[severity] ?? 'gray'}
      data-testid="severity-badge"
    >
      {severity}
    </Badge>
  );
}

const STATUS_COLOR: Record<string, string> = {
  open: 'red',
  in_progress: 'yellow',
  resolved: 'teal',
  excepted: 'gray',
};

function StatusBadge({ status }: { status: string }): JSX.Element {
  return (
    <Badge
      color={STATUS_COLOR[status] ?? 'gray'}
      variant="outline"
      data-testid="status-badge"
    >
      {status.replace('_', ' ')}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// Page loading skeleton
// ---------------------------------------------------------------------------

function RemediationDetailSkeleton(): JSX.Element {
  return (
    <Stack gap="lg" data-testid="remediation-detail-skeleton">
      <Skeleton height={24} width="40%" />
      <Skeleton height={32} width="60%" />
      <Group gap="sm">
        <Skeleton height={24} width={80} />
        <Skeleton height={24} width={100} />
        <Skeleton height={24} width={80} />
      </Group>
      <Skeleton height={160} radius="md" />
      <Skeleton height={300} radius="md" />
      <Skeleton height={160} radius="md" />
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Exception request form (inline, WOREF-083 stub)
// ---------------------------------------------------------------------------

interface ExceptionFormProps {
  findingId: string;
  onClose: () => void;
}

function ExceptionRequestForm({
  findingId,
  onClose,
}: ExceptionFormProps): JSX.Element {
  const [justification, setJustification] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const exceptionMutation = useRequestException(findingId);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!justification.trim()) {
      showToast({
        type: 'warning',
        message: 'Please provide a justification for the exception request.',
      });
      return;
    }
    exceptionMutation.mutate(
      {
        justification: justification.trim(),
        expires_at: expiresAt || undefined,
      },
      {
        onSuccess: () => {
          showToast({
            type: 'success',
            title: 'Exception requested',
            message:
              'Your exception request has been submitted for review.',
          });
          onClose();
        },
        onError: (err) => {
          showToast({
            type: 'error',
            title: 'Request failed',
            message:
              err instanceof Error
                ? err.message
                : 'Failed to submit exception request.',
          });
        },
      },
    );
  };

  return (
    <Stack
      gap="md"
      component="form"
      onSubmit={handleSubmit}
      data-testid="exception-request-form"
    >
      <Title order={5}>Request Exception</Title>
      <Text size="sm" c="dimmed">
        Provide a justification for why this finding should be excepted. The
        request will be routed to a Security Reviewer or Platform Admin for
        approval.
      </Text>

      <Textarea
        label="Justification"
        description="Explain why this exception is necessary and acceptable."
        placeholder="e.g. This finding is a false positive because…"
        required
        minRows={3}
        value={justification}
        onChange={(e) => setJustification(e.currentTarget.value)}
        data-testid="exception-justification-input"
      />

      <TextInput
        label="Expiry date (optional)"
        description="ISO 8601 date after which the exception lapses."
        placeholder="e.g. 2026-12-31"
        type="date"
        value={expiresAt}
        onChange={(e) => setExpiresAt(e.currentTarget.value)}
        data-testid="exception-expiry-input"
      />

      <Group gap="sm">
        <Button
          type="submit"
          loading={exceptionMutation.isPending}
          data-testid="exception-submit-btn"
        >
          Submit Request
        </Button>
        <Button
          variant="subtle"
          onClick={onClose}
          disabled={exceptionMutation.isPending}
          data-testid="exception-cancel-btn"
        >
          Cancel
        </Button>
      </Group>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export function RemediationDetail(): JSX.Element {
  const { findingId } = useParams<{ findingId: string }>();
  const navigate = useNavigate();

  // Local state
  const [showExceptionForm, setShowExceptionForm] = useState(false);
  const [lastReEvalResult, setLastReEvalResult] =
    useState<ReEvaluationResult | null>(null);

  // Data fetching
  const findingQuery = useFinding(findingId ?? '');
  const recommendationQuery = useFindingRemediation(findingId ?? '');
  const reEvaluateMutation = useReEvaluate(findingId ?? '');

  // Derived state
  const finding = findingQuery.data;
  const recommendation = recommendationQuery.data;
  const isLoading = findingQuery.isLoading;
  const findingError = findingQuery.error;
  const is404 =
    findingError &&
    typeof findingError === 'object' &&
    'status' in findingError &&
    (findingError as { status: number }).status === 404;
  const isResolved = finding?.status === 'resolved';

  const recommendationIs404 =
    recommendationQuery.error &&
    typeof recommendationQuery.error === 'object' &&
    'status' in recommendationQuery.error &&
    (recommendationQuery.error as { status: number }).status === 404;

  // Re-evaluate handler
  const handleReEvaluate = () => {
    reEvaluateMutation.mutate(undefined, {
      onSuccess: (result) => {
        setLastReEvalResult(result);
        showToast({
          type: 'success',
          title: 'Re-evaluation complete',
          message: `Health score updated: ${
            result.before_health_score !== null
              ? `${Math.round(result.before_health_score)} → `
              : ''
          }${Math.round(result.after_health_score)}`,
        });
      },
      onError: (err) => {
        showToast({
          type: 'error',
          title: 'Re-evaluation failed',
          message:
            err instanceof Error
              ? err.message
              : 'Re-evaluation could not be completed.',
        });
      },
    });
  };

  // ---- Loading state -------------------------------------------------------
  if (isLoading) {
    return (
      <Container size="xl">
        <RemediationDetailSkeleton />
      </Container>
    );
  }

  // ---- Not found state -----------------------------------------------------
  if (is404 || (!isLoading && !finding && findingError)) {
    return (
      <Container size="xl">
        <Stack gap="md" align="center" py="xl" data-testid="finding-not-found">
          <Text size="xl">🔍</Text>
          <Title order={3}>Finding Not Found</Title>
          <Text c="dimmed" ta="center" maw={480}>
            The finding you&apos;re looking for does not exist or you do not
            have permission to view it.
          </Text>
          <Button
            variant="outline"
            onClick={() => void navigate('/findings')}
            data-testid="back-to-findings-btn"
          >
            Back to Findings
          </Button>
        </Stack>
      </Container>
    );
  }

  // ---- Error state ---------------------------------------------------------
  if (!isLoading && findingError && !is404) {
    return (
      <Container size="xl">
        <Alert
          color="red"
          title="Failed to load finding"
          data-testid="finding-error"
        >
          <Stack gap="xs">
            <Text size="sm">
              {findingError instanceof Error
                ? findingError.message
                : 'An unexpected error occurred.'}
            </Text>
            <Button
              variant="outline"
              color="red"
              size="xs"
              onClick={() => void findingQuery.refetch()}
              data-testid="retry-btn"
              style={{ alignSelf: 'flex-start' }}
            >
              Retry
            </Button>
          </Stack>
        </Alert>
      </Container>
    );
  }

  if (!finding) return <Container size="xl"><RemediationDetailSkeleton /></Container>;

  // ---- Normal render -------------------------------------------------------
  const serviceName = finding.service_id
    ? `Service ${finding.service_id.slice(0, 8)}`
    : 'Unknown Service';

  return (
    <Container size="xl">
      <Stack gap="lg">
        {/* Breadcrumb navigation */}
        <Breadcrumbs
          aria-label="Breadcrumb navigation"
          data-testid="breadcrumb"
        >
          <Anchor component={Link} to="/services" size="sm">
            Services
          </Anchor>
          <Anchor
            component={Link}
            to={`/services?serviceId=${finding.service_id}`}
            size="sm"
            data-testid="breadcrumb-service"
          >
            {serviceName}
          </Anchor>
          <Anchor component={Link} to="/findings" size="sm">
            Findings
          </Anchor>
          <Text size="sm" aria-current="page" data-testid="breadcrumb-current">
            {finding.title}
          </Text>
        </Breadcrumbs>

        {/* Page header */}
        <div data-testid="page-header">
          <Title order={2} mb="xs" data-testid="finding-title">
            {finding.title}
          </Title>
          <Group gap="sm" wrap="wrap">
            <SeverityBadge severity={finding.severity} />
            <Badge
              color="violet"
              variant="outline"
              data-testid="dimension-badge"
            >
              {finding.dimension.replace('_', ' ')}
            </Badge>
            <StatusBadge status={finding.status} />
          </Group>
        </div>

        {/* Resolved banner */}
        {isResolved && (
          <Alert
            color="teal"
            title="Finding resolved"
            data-testid="resolved-banner"
          >
            This finding was resolved on{' '}
            {finding.resolved_at
              ? new Date(finding.resolved_at).toLocaleDateString()
              : 'an unknown date'}
            . Re-evaluation and exception requests are not available for
            resolved findings.
          </Alert>
        )}

        {/* Violation explanation */}
        <ViolationExplanationCard
          explanation={finding.ai_explanation ?? finding.description}
          businessImpact={recommendation?.business_impact ?? null}
          isLoading={recommendationQuery.isLoading}
          data-testid="violation-explanation-card"
        />

        {/* AI recommendation */}
        <AIRemediationCard
          recommendation={recommendation ?? null}
          isLoading={recommendationQuery.isLoading}
          isNotFound={Boolean(recommendationIs404)}
          onRetry={() => void recommendationQuery.refetch()}
          data-testid="ai-remediation-card"
        />

        {/* Score comparison + action buttons */}
        <ScoreComparisonCard
          reEvalResult={lastReEvalResult}
          isReEvaluating={reEvaluateMutation.isPending}
          isResolved={isResolved}
          onReEvaluate={handleReEvaluate}
          onRequestException={() => setShowExceptionForm(true)}
          data-testid="score-comparison-card"
        />

        {/* Exception request form (WOREF-083) — inline collapsible */}
        {showExceptionForm && !isResolved && (
          <>
            <Divider />
            <ExceptionRequestForm
              findingId={finding.id}
              onClose={() => setShowExceptionForm(false)}
            />
          </>
        )}
      </Stack>
    </Container>
  );
}
