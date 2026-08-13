/**
 * ReleaseDecisionReviewPage — Release Decision Review interface (WO-075).
 *
 * Route: /releases/:id
 *
 * State machine:
 *   loading         — fetching assessment data
 *   error           — fetch failed (full-page error with retry)
 *   processing      — assessment status is 'pending' or 'in_progress' (polling)
 *   pending-decision— assessment is 'completed', no decision_record exists
 *   decided         — assessment has a decision_record (read-only)
 *
 * Permissions:
 *   All roles can view (guarded by 'service.view').
 *   Approve button shown only to users with 'release.approve'.
 *   Block button shown only to users with 'release.block'.
 *   Users with neither see a read-only message.
 */

import {
  Alert,
  Box,
  Button,
  Card,
  Center,
  Container,
  Divider,
  Group,
  Loader,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { type JSX, useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';

import { DemoIndicatorProvider } from '@/contexts/DemoIndicatorContext';
import { MockDataBanner } from '@/components/common/MockDataBanner';
import { AssessmentMetadata } from '@/components/releases/AssessmentMetadata';
import { ApproveModal } from '@/components/releases/ApproveModal';
import { BlockModal } from '@/components/releases/BlockModal';
import { FindingsTable } from '@/components/releases/FindingsTable';
import { ReleaseDecisionCard } from '@/components/releases/ReleaseDecisionCard';
import { DecisionBanner } from '@/components/shared/DecisionBanner';
import { ScoreRing } from '@/components/shared/ScoreRing';
import { useReleaseDecisionView, useSubmitDecision } from '@/hooks/api/useReleases';
import { useAuthStore } from '@/stores/auth-store';
import { type DecisionOutcome } from '@/types';
import { type ReleaseAssessmentFinding } from '@/types/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Derive DecisionOutcome from the backend decision string for DecisionBanner. */
function toDecisionOutcome(decision: string): DecisionOutcome {
  switch (decision.toUpperCase()) {
    case 'APPROVE':
      return 'approve';
    case 'CONDITIONAL_APPROVE':
      return 'conditional_approve';
    case 'BLOCK':
      return 'block';
    default:
      return 'pending';
  }
}

/** Count findings by severity across the severity groups. */
function countBySeverity(
  byS: Record<string, { count: number; items: ReleaseAssessmentFinding[] }>,
) {
  return {
    critical: byS['critical']?.count ?? 0,
    high:     byS['high']?.count ?? 0,
    medium:   byS['medium']?.count ?? 0,
    low:      byS['low']?.count ?? 0,
  };
}

/** Flatten severity groups into a flat array of findings. */
function flattenFindings(
  byS: Record<string, { count: number; items: ReleaseAssessmentFinding[] }>,
): ReleaseAssessmentFinding[] {
  return Object.values(byS).flatMap((g) => g.items);
}

// ---------------------------------------------------------------------------
// Processing state component
// ---------------------------------------------------------------------------

function ProcessingState({ onRetry }: { onRetry: () => void }): JSX.Element {
  return (
    <Center style={{ minHeight: 300 }} data-testid="processing-state">
      <Stack align="center" gap="md">
        <Loader size="lg" />
        <Title order={4}>Assessment in Progress</Title>
        <Text c="dimmed" ta="center">
          The release assessment pipeline is running. This may take a few moments.
        </Text>
        <Button variant="subtle" size="sm" onClick={onRetry}>
          Refresh
        </Button>
      </Stack>
    </Center>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export function ReleaseDecisionReviewPage(): JSX.Element {
  const { id = '' } = useParams<{ id: string }>();
  const permissions = useAuthStore((s) => s.user?.permissions ?? []);

  // Data fetching
  const { data, isLoading, isError, error, refetch } = useReleaseDecisionView(id, {
    refetchInterval: (query) => {
      const d = query.state.data;
      if (!d) return false;
      const status = d.assessment.status;
      // Poll while processing
      if (status === 'pending' || status === 'in_progress') return 3000;
      return false;
    },
  });

  const submitDecision = useSubmitDecision(id);

  // Modal state
  const [approveModal, setApproveModal] = useState<{
    open: boolean;
    rationale: string;
    comment: string;
  }>({ open: false, rationale: '', comment: '' });

  const [blockModal, setBlockModal] = useState<{
    open: boolean;
    rationale: string;
    comment: string;
  }>({ open: false, rationale: '', comment: '' });

  // Handlers
  const handleApprove = useCallback((rationale: string, comment: string) => {
    setApproveModal({ open: true, rationale, comment });
  }, []);

  const handleBlock = useCallback((rationale: string, comment: string) => {
    setBlockModal({ open: true, rationale, comment });
  }, []);

  const handleConfirmApprove = useCallback(async () => {
    try {
      await submitDecision.mutateAsync({
        decision: 'APPROVE',
        rationale: approveModal.rationale,
        comment: approveModal.comment || undefined,
      });
      setApproveModal({ open: false, rationale: '', comment: '' });
      notifications.show({
        title: 'Release Approved',
        message: 'The release approval has been recorded in the audit log.',
        color: 'green',
        autoClose: 5000,
      });
    } catch (err: unknown) {
      setApproveModal((prev) => ({ ...prev, open: false }));
      const status = (err as { status?: number }).status;
      if (status === 403) {
        notifications.show({
          title: 'Permission Denied',
          message: 'Your permissions have changed — you no longer have authority to make this decision.',
          color: 'red',
          autoClose: false,
        });
      } else if (status === 409) {
        notifications.show({
          title: 'Already Decided',
          message: 'This release has already been decided. Refreshing…',
          color: 'orange',
          autoClose: 3000,
        });
        void refetch();
      } else {
        const detail = (err as { detail?: string }).detail;
        notifications.show({
          title: 'Decision Failed',
          message: detail ?? 'An unexpected error occurred. Please try again.',
          color: 'red',
          autoClose: false,
        });
      }
    }
  }, [approveModal, submitDecision, refetch]);

  const handleConfirmBlock = useCallback(async () => {
    try {
      await submitDecision.mutateAsync({
        decision: 'BLOCK',
        rationale: blockModal.rationale,
        comment: blockModal.comment || undefined,
      });
      setBlockModal({ open: false, rationale: '', comment: '' });
      notifications.show({
        title: 'Release Blocked',
        message: 'The release block has been recorded in the audit log.',
        color: 'red',
        autoClose: 5000,
      });
    } catch (err: unknown) {
      setBlockModal((prev) => ({ ...prev, open: false }));
      const status = (err as { status?: number }).status;
      if (status === 403) {
        notifications.show({
          title: 'Permission Denied',
          message: 'Your permissions have changed — you no longer have authority to make this decision.',
          color: 'red',
          autoClose: false,
        });
      } else if (status === 409) {
        notifications.show({
          title: 'Already Decided',
          message: 'This release has already been decided. Refreshing…',
          color: 'orange',
          autoClose: 3000,
        });
        void refetch();
      } else {
        const detail = (err as { detail?: string }).detail;
        notifications.show({
          title: 'Decision Failed',
          message: detail ?? 'An unexpected error occurred. Please try again.',
          color: 'red',
          autoClose: false,
        });
      }
    }
  }, [blockModal, submitDecision, refetch]);

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------

  if (isLoading) {
    return (
      <Container size="lg" py="xl" data-testid="page-loading">
        <Center style={{ minHeight: 300 }}>
          <Stack align="center" gap="md">
            <Loader size="lg" />
            <Text c="dimmed">Loading assessment…</Text>
          </Stack>
        </Center>
      </Container>
    );
  }

  // ---------------------------------------------------------------------------
  // Error state
  // ---------------------------------------------------------------------------

  if (isError || !data) {
    const errMsg = (error as { detail?: string })?.detail ?? 'Failed to load assessment.';
    return (
      <Container size="lg" py="xl" data-testid="page-error">
        <Alert color="danger" title="Failed to load assessment" variant="light">
          {errMsg}
        </Alert>
        <Button mt="md" variant="outline" onClick={() => void refetch()}>
          Retry
        </Button>
      </Container>
    );
  }

  // ---------------------------------------------------------------------------
  // Processing state (pending or in_progress)
  // ---------------------------------------------------------------------------

  const { assessment, risk_score, findings_summary, escalation, decision_record } = data;

  if (assessment.status === 'pending' || assessment.status === 'in_progress') {
    return (
      <Container size="lg" py="xl">
        <AssessmentMetadata
          id={assessment.id}
          serviceId={assessment.service_id}
          commitSha={assessment.commit_sha}
          prReference={assessment.pr_reference}
          status={assessment.status}
          createdAt={assessment.created_at}
          completedAt={assessment.completed_at}
        />
        <Box mt="xl">
          <ProcessingState onRetry={() => void refetch()} />
        </Box>
      </Container>
    );
  }

  // ---------------------------------------------------------------------------
  // Flatten findings for the table
  // ---------------------------------------------------------------------------

  const allFindings = flattenFindings(findings_summary.by_severity);
  const findingCounts = countBySeverity(findings_summary.by_severity);
  const riskScoreValue = risk_score?.overall ?? null;

  // ---------------------------------------------------------------------------
  // Decided state (read-only)
  // ---------------------------------------------------------------------------

  if (decision_record !== null) {
    const outcome = toDecisionOutcome(decision_record.decision);
    return (
      <Container size="lg" py="xl" data-testid="page-decided">
        {/* Escalation banner */}
        {escalation.is_escalated && (
          <Alert
            color="red"
            variant="filled"
            title="Security Escalation"
            mb="lg"
            data-testid="escalation-banner"
          >
            This assessment has been escalated due to critical security findings.
            Security Reviewer approval is required.
          </Alert>
        )}

        {/* Decision outcome banner */}
        <DecisionBanner
          decision={outcome}
          mb="lg"
          data-testid="decision-banner"
        />

        {/* Assessment metadata */}
        <AssessmentMetadata
          id={assessment.id}
          serviceId={assessment.service_id}
          commitSha={assessment.commit_sha}
          prReference={assessment.pr_reference}
          status={assessment.status}
          createdAt={assessment.created_at}
          completedAt={assessment.completed_at}
        />

        {/* Decision details (read-only) */}
        <Card withBorder radius="md" p="md" mt="md" data-testid="decision-details-card">
          <Stack gap="sm">
            <Title order={4}>Decision Details</Title>
            <Group gap="sm">
              <Text size="sm" c="dimmed" fw={500} style={{ minWidth: 120 }}>Decided by:</Text>
              <Text size="sm">{decision_record.decided_by_role ?? '—'}</Text>
            </Group>
            <Group gap="sm">
              <Text size="sm" c="dimmed" fw={500} style={{ minWidth: 120 }}>Decided at:</Text>
              <Text size="sm">
                {new Date(decision_record.created_at).toLocaleString(undefined, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                })}
              </Text>
            </Group>
            <Box>
              <Text size="sm" c="dimmed" fw={500} mb={4}>Rationale:</Text>
              <Text size="sm" data-testid="decision-rationale">
                {decision_record.rationale ?? '—'}
              </Text>
            </Box>
            {decision_record.comment && (
              <Box>
                <Text size="sm" c="dimmed" fw={500} mb={4}>Additional Comment:</Text>
                <Text size="sm" data-testid="decision-comment">
                  {decision_record.comment}
                </Text>
              </Box>
            )}
          </Stack>
        </Card>

        {/* Risk Score */}
        {riskScoreValue !== null && (
          <Box mt="md">
            <Group gap="sm" align="center">
              <Text fw={500}>Release Risk Score</Text>
              <ScoreRing
                score={riskScoreValue}
                size={64}
                label="Risk Score"
                color={
                  riskScoreValue <= 30 ? '#16a34a'
                  : riskScoreValue <= 60 ? '#d97706'
                  : '#dc2626'
                }
              />
            </Group>
          </Box>
        )}

        {/* Findings */}
        {allFindings.length > 0 && (
          <Box mt="md">
            <Title order={4} mb="sm">Findings</Title>
            <FindingsTable findings={allFindings} />
          </Box>
        )}
      </Container>
    );
  }

  // ---------------------------------------------------------------------------
  // Pending-decision state (actionable)
  // ---------------------------------------------------------------------------

  const isDemo = assessment.is_demo ?? false;

  return (
    <DemoIndicatorProvider isDemo={isDemo}>
    <Container size="lg" py="xl" data-testid="page-pending-decision">
      {/* Demo data banner */}
      {isDemo && <MockDataBanner />}

      {/* Escalation banner */}
      {escalation.is_escalated && (
        <Alert
          color="red"
          variant="filled"
          title="Security Escalation"
          mb="lg"
          data-testid="escalation-banner"
        >
          This assessment has been escalated due to critical security findings.
          Security Reviewer approval is required.
        </Alert>
      )}

      <Stack gap="md">
        {/* Assessment metadata */}
        <AssessmentMetadata
          id={assessment.id}
          serviceId={assessment.service_id}
          commitSha={assessment.commit_sha}
          prReference={assessment.pr_reference}
          status={assessment.status}
          createdAt={assessment.created_at}
          completedAt={assessment.completed_at}
        />

        {/* Risk Score */}
        <Card withBorder radius="md" p="md" data-testid="risk-score-card">
          <Group gap="md" align="center">
            <Stack gap={2}>
              <Title order={4}>Release Risk Score</Title>
              <Text size="sm" c="dimmed">
                Lower scores indicate safer releases (0–100).
              </Text>
            </Stack>
            {riskScoreValue !== null ? (
              <ScoreRing
                score={riskScoreValue}
                size={80}
                label="Risk Score"
                color={
                  riskScoreValue <= 30 ? '#16a34a'
                  : riskScoreValue <= 60 ? '#d97706'
                  : '#dc2626'
                }
              />
            ) : (
              <Text size="sm" c="dimmed">Score not available</Text>
            )}
          </Group>
        </Card>

        {/* Findings section */}
        <Card withBorder radius="md" p="md" data-testid="findings-section">
          <Stack gap="sm">
            <Group justify="space-between" align="center">
              <Title order={4}>Findings ({findings_summary.total})</Title>
            </Group>
            <FindingsTable findings={allFindings} />
          </Stack>
        </Card>

        {/* Decision form */}
        <ReleaseDecisionCard
          permissions={permissions}
          isSubmitting={submitDecision.isPending}
          onApprove={handleApprove}
          onBlock={handleBlock}
        />
      </Stack>

      {/* Approve confirmation modal */}
      <ApproveModal
        opened={approveModal.open}
        onClose={() => setApproveModal({ open: false, rationale: '', comment: '' })}
        onConfirm={() => void handleConfirmApprove()}
        confirmLoading={submitDecision.isPending}
        riskScore={riskScoreValue}
        findingCounts={findingCounts}
        rationale={approveModal.rationale}
      />

      {/* Block confirmation modal */}
      <BlockModal
        opened={blockModal.open}
        onClose={() => setBlockModal({ open: false, rationale: '', comment: '' })}
        onConfirm={() => void handleConfirmBlock()}
        confirmLoading={submitDecision.isPending}
        riskScore={riskScoreValue}
        findingCounts={findingCounts}
        rationale={blockModal.rationale}
      />
    </Container>
    </DemoIndicatorProvider>
  );
}
