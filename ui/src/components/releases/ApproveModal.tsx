/**
 * ApproveModal — confirmation dialog for releasing a build.
 *
 * Shows the Risk Score, finding count summary, and rationale preview before
 * the user confirms the APPROVE decision.
 *
 * Part of WO-075 Release Decision Review.
 */

import { Alert, Badge, Button, Group, Modal, Stack, Text } from '@mantine/core';
import { type JSX } from 'react';

export interface ApproveModalProps {
  /** Whether the modal is open. */
  opened: boolean;
  /** Called when the modal should close (Cancel button or backdrop click). */
  onClose: () => void;
  /** Called when the user confirms the approval. */
  onConfirm: () => void;
  /** Whether the confirm button should show a loading spinner. */
  confirmLoading?: boolean;
  /** Risk score (0-100). Lower is safer. */
  riskScore: number | null;
  /** Finding counts by severity for the summary. */
  findingCounts: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  /** Rationale text entered by the reviewer. */
  rationale: string;
}

/**
 * Confirmation modal for release approval.
 *
 * @example
 * <ApproveModal
 *   opened={showApprove}
 *   onClose={() => setShowApprove(false)}
 *   onConfirm={handleApprove}
 *   riskScore={25}
 *   findingCounts={{ critical: 0, high: 1, medium: 2, low: 3 }}
 *   rationale="All critical checks pass."
 * />
 */
export function ApproveModal({
  opened,
  onClose,
  onConfirm,
  confirmLoading = false,
  riskScore,
  findingCounts,
  rationale,
}: ApproveModalProps): JSX.Element {
  const riskColor =
    riskScore === null ? 'gray'
    : riskScore <= 30 ? 'green'
    : riskScore <= 60 ? 'orange'
    : 'red';

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Confirm Release Approval"
      size="md"
      data-testid="approve-modal"
    >
      <Stack gap="md">
        <Alert color="green" variant="light" title="You are approving this release">
          This action is irreversible. The decision will be permanently recorded in the audit log.
        </Alert>

        {/* Risk Score summary */}
        <Group gap="sm" align="center">
          <Text size="sm" fw={500}>Risk Score:</Text>
          <Badge color={riskColor} size="lg" variant="light" data-testid="approve-modal-risk-score">
            {riskScore !== null ? riskScore : '—'}
          </Badge>
        </Group>

        {/* Finding count summary */}
        <Stack gap={4}>
          <Text size="sm" fw={500}>Findings Summary:</Text>
          <Group gap="xs">
            {findingCounts.critical > 0 && (
              <Badge color="red" size="sm" variant="light">{findingCounts.critical} Critical</Badge>
            )}
            {findingCounts.high > 0 && (
              <Badge color="orange" size="sm" variant="light">{findingCounts.high} High</Badge>
            )}
            {findingCounts.medium > 0 && (
              <Badge color="yellow" size="sm" variant="light">{findingCounts.medium} Medium</Badge>
            )}
            {findingCounts.low > 0 && (
              <Badge color="blue" size="sm" variant="light">{findingCounts.low} Low</Badge>
            )}
            {findingCounts.critical === 0 &&
              findingCounts.high === 0 &&
              findingCounts.medium === 0 &&
              findingCounts.low === 0 && (
              <Text size="sm" c="dimmed">No findings</Text>
            )}
          </Group>
        </Stack>

        {/* Rationale preview */}
        <Stack gap={4}>
          <Text size="sm" fw={500}>Your Rationale:</Text>
          <Text
            size="sm"
            style={{
              padding: '8px',
              background: 'var(--mantine-color-gray-0)',
              borderRadius: 4,
              fontStyle: 'italic',
            }}
            data-testid="approve-modal-rationale"
          >
            &ldquo;{rationale}&rdquo;
          </Text>
        </Stack>

        <Group justify="flex-end" mt="sm">
          <Button variant="subtle" color="gray" onClick={onClose} data-testid="approve-modal-cancel">
            Cancel
          </Button>
          <Button
            color="green"
            onClick={onConfirm}
            loading={confirmLoading}
            data-testid="approve-modal-confirm"
          >
            Confirm Approval
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
