/**
 * BlockModal — confirmation dialog for blocking a release.
 *
 * Shows the Risk Score, finding count summary, and rationale preview before
 * the user confirms the BLOCK decision.
 *
 * Part of WO-075 Release Decision Review.
 */

import { Alert, Badge, Button, Group, Modal, Stack, Text } from '@mantine/core';
import { type JSX } from 'react';

export interface BlockModalProps {
  /** Whether the modal is open. */
  opened: boolean;
  /** Called when the modal should close (Cancel button or backdrop click). */
  onClose: () => void;
  /** Called when the user confirms the block. */
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
 * Confirmation modal for release block.
 *
 * @example
 * <BlockModal
 *   opened={showBlock}
 *   onClose={() => setShowBlock(false)}
 *   onConfirm={handleBlock}
 *   riskScore={78}
 *   findingCounts={{ critical: 2, high: 3, medium: 1, low: 0 }}
 *   rationale="Critical security vulnerabilities must be resolved."
 * />
 */
export function BlockModal({
  opened,
  onClose,
  onConfirm,
  confirmLoading = false,
  riskScore,
  findingCounts,
  rationale,
}: BlockModalProps): JSX.Element {
  const riskColor =
    riskScore === null ? 'gray'
    : riskScore <= 30 ? 'green'
    : riskScore <= 60 ? 'orange'
    : 'red';

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Confirm Release Block"
      size="md"
      data-testid="block-modal"
    >
      <Stack gap="md">
        <Alert color="red" variant="light" title="You are blocking this release">
          This action is irreversible. The decision will be permanently recorded in the audit log.
        </Alert>

        {/* Risk Score summary */}
        <Group gap="sm" align="center">
          <Text size="sm" fw={500}>Risk Score:</Text>
          <Badge color={riskColor} size="lg" variant="light" data-testid="block-modal-risk-score">
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
            data-testid="block-modal-rationale"
          >
            &ldquo;{rationale}&rdquo;
          </Text>
        </Stack>

        <Group justify="flex-end" mt="sm">
          <Button variant="subtle" color="gray" onClick={onClose} data-testid="block-modal-cancel">
            Cancel
          </Button>
          <Button
            color="red"
            onClick={onConfirm}
            loading={confirmLoading}
            data-testid="block-modal-confirm"
          >
            Confirm Block
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
