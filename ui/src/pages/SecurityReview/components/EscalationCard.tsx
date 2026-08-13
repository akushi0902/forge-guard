/**
 * EscalationCard — card for a single escalated release assessment.
 *
 * Displays service name, severity badge, finding description and three action
 * buttons: Review (navigate to detail), Block (opens confirmation modal with
 * mandatory rationale), and Override (confirm without hard block).
 *
 * Action buttons are disabled with a tooltip when the user lacks the required
 * permission (release.block for Block/Override).
 */

import {
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Stack,
  Text,
  Textarea,
  Tooltip,
} from '@mantine/core';
import { type JSX, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { notifications } from '@mantine/notifications';

import { useAuthStore } from '@/stores/auth-store';
import { useBlockRelease } from '@/hooks/api/useReleaseDecision';
import { type EscalatedRelease } from '@/hooks/api/useSecurityFindings';

// ---------------------------------------------------------------------------
// Severity colour mapping
// ---------------------------------------------------------------------------

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'red',
  high: 'orange',
  medium: 'yellow',
  low: 'blue',
};

function severityColor(severity: string): string {
  return SEVERITY_COLORS[severity.toLowerCase()] ?? 'gray';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface EscalationCardProps {
  escalation: EscalatedRelease;
}

/**
 * @example
 * <EscalationCard escalation={escalatedRelease} />
 */
export function EscalationCard({ escalation }: EscalationCardProps): JSX.Element {
  const navigate = useNavigate();
  const permissions = useAuthStore((s) => s.user?.permissions ?? []);
  const canBlock = permissions.includes('release.block');

  const [blockModalOpen, setBlockModalOpen] = useState(false);
  const [overrideModalOpen, setOverrideModalOpen] = useState(false);
  const [rationale, setRationale] = useState('');
  const [rationaleError, setRationaleError] = useState('');

  const blockMutation = useBlockRelease();

  function openBlockModal(): void {
    setRationale('');
    setRationaleError('');
    setBlockModalOpen(true);
  }

  function openOverrideModal(): void {
    setRationale('');
    setRationaleError('');
    setOverrideModalOpen(true);
  }

  function closeModals(): void {
    setBlockModalOpen(false);
    setOverrideModalOpen(false);
    setRationale('');
    setRationaleError('');
  }

  function validateRationale(): boolean {
    if (!rationale.trim()) {
      setRationaleError('Rationale is required before submitting a decision.');
      return false;
    }
    setRationaleError('');
    return true;
  }

  async function handleBlock(): Promise<void> {
    if (!validateRationale()) return;
    try {
      await blockMutation.mutateAsync({
        releaseId: escalation.id,
        body: { decision: 'BLOCK', rationale: rationale.trim() },
      });
      closeModals();
      notifications.show({
        title: 'Release Blocked',
        message: `${escalation.service_name} release has been blocked.`,
        color: 'red',
        autoClose: 5000,
      });
    } catch {
      // Error notification handled by the global query client onError hook.
    }
  }

  async function handleOverride(): Promise<void> {
    if (!validateRationale()) return;
    try {
      await blockMutation.mutateAsync({
        releaseId: escalation.id,
        body: { decision: 'OVERRIDE', rationale: rationale.trim() },
      });
      closeModals();
      notifications.show({
        title: 'Block Overridden',
        message: `${escalation.service_name} security escalation has been overridden.`,
        color: 'green',
        autoClose: 5000,
      });
    } catch {
      // Error notification handled by the global query client onError hook.
    }
  }

  const isSubmitting = blockMutation.isPending;

  return (
    <>
      <Card
        withBorder
        radius="md"
        padding="md"
        data-testid={`escalation-card-${escalation.id}`}
      >
        <Stack gap="sm">
          {/* Header: service name + severity */}
          <Group justify="space-between" align="center">
            <Text fw={600} size="md" data-testid={`escalation-service-${escalation.id}`}>
              {escalation.service_name}
            </Text>
            <Badge
              color={severityColor(escalation.severity)}
              variant="filled"
              size="md"
              data-testid={`escalation-severity-${escalation.id}`}
            >
              {escalation.severity.toUpperCase()}
            </Badge>
          </Group>

          {/* Finding title */}
          <Text fw={500} size="sm" c="dimmed">
            {escalation.finding_title}
          </Text>

          {/* Finding description — truncated with title for full text */}
          <Text
            size="sm"
            lineClamp={3}
            title={escalation.finding_description}
            data-testid={`escalation-description-${escalation.id}`}
          >
            {escalation.finding_description}
          </Text>

          {/* Metadata */}
          <Text size="xs" c="dimmed">
            Commit:{' '}
            <Text component="span" ff="monospace" size="xs">
              {escalation.commit_sha.slice(0, 8)}
            </Text>
            {escalation.risk_score != null && ` · Risk Score: ${escalation.risk_score}`}
          </Text>

          {/* Action buttons */}
          <Group gap="xs" mt="xs">
            <Button
              size="xs"
              variant="outline"
              onClick={() => void navigate(`/releases/${escalation.id}`)}
              data-testid={`escalation-review-btn-${escalation.id}`}
              aria-label={`Review ${escalation.service_name} escalation`}
            >
              Review
            </Button>

            <Tooltip
              label={canBlock ? undefined : 'You need the release.block permission to block a release.'}
              disabled={canBlock}
              withArrow
            >
              <Button
                size="xs"
                color="red"
                disabled={!canBlock || isSubmitting}
                onClick={openBlockModal}
                data-testid={`escalation-block-btn-${escalation.id}`}
                aria-label={`Block ${escalation.service_name} release`}
                aria-disabled={!canBlock}
              >
                Block
              </Button>
            </Tooltip>

            <Tooltip
              label={canBlock ? undefined : 'You need the release.block permission to override a security escalation.'}
              disabled={canBlock}
              withArrow
            >
              <Button
                size="xs"
                color="orange"
                variant="outline"
                disabled={!canBlock || isSubmitting}
                onClick={openOverrideModal}
                data-testid={`escalation-override-btn-${escalation.id}`}
                aria-label={`Override ${escalation.service_name} security escalation`}
                aria-disabled={!canBlock}
              >
                Override
              </Button>
            </Tooltip>
          </Group>
        </Stack>
      </Card>

      {/* Block confirmation modal */}
      <Modal
        opened={blockModalOpen}
        onClose={closeModals}
        title="Confirm Release Block"
        size="md"
        data-testid={`block-modal-${escalation.id}`}
      >
        <Stack gap="md">
          <Text size="sm" c="red" fw={500}>
            ⚠ You are permanently blocking this release. This action is recorded in the audit log.
          </Text>
          <Text size="sm">
            Service: <strong>{escalation.service_name}</strong> · Commit:{' '}
            <Text component="span" ff="monospace" size="sm">
              {escalation.commit_sha.slice(0, 8)}
            </Text>
          </Text>
          <Textarea
            label="Rationale (required)"
            description="Explain why this release is being blocked."
            placeholder="Describe the security risk and why blocking is necessary…"
            value={rationale}
            onChange={(e) => {
              setRationale(e.currentTarget.value);
              if (rationaleError) setRationaleError('');
            }}
            minRows={3}
            error={rationaleError}
            required
            data-testid="block-rationale-input"
            aria-label="Block rationale"
            aria-required="true"
          />
          <Group justify="flex-end" mt="sm">
            <Button
              variant="subtle"
              color="gray"
              onClick={closeModals}
              data-testid="block-modal-cancel"
            >
              Cancel
            </Button>
            <Button
              color="red"
              onClick={() => void handleBlock()}
              loading={isSubmitting}
              data-testid="block-modal-confirm"
            >
              Confirm Block
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* Override confirmation modal */}
      <Modal
        opened={overrideModalOpen}
        onClose={closeModals}
        title="Override Security Escalation"
        size="md"
        data-testid={`override-modal-${escalation.id}`}
      >
        <Stack gap="md">
          <Text size="sm" c="orange" fw={500}>
            You are overriding a security escalation. This action is recorded in the audit log.
          </Text>
          <Textarea
            label="Rationale (required)"
            description="Explain why this security escalation is being overridden."
            placeholder="Describe the compensating controls or accepted risk…"
            value={rationale}
            onChange={(e) => {
              setRationale(e.currentTarget.value);
              if (rationaleError) setRationaleError('');
            }}
            minRows={3}
            error={rationaleError}
            required
            data-testid="override-rationale-input"
            aria-label="Override rationale"
            aria-required="true"
          />
          <Group justify="flex-end" mt="sm">
            <Button
              variant="subtle"
              color="gray"
              onClick={closeModals}
              data-testid="override-modal-cancel"
            >
              Cancel
            </Button>
            <Button
              color="orange"
              onClick={() => void handleOverride()}
              loading={isSubmitting}
              data-testid="override-modal-confirm"
            >
              Confirm Override
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
