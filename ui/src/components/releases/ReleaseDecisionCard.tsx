/**
 * ReleaseDecisionCard — decision form card for the Release Decision Review page.
 *
 * Features:
 *   - Rationale Textarea (required, minLength 10, maxLength 2000, with character counter)
 *   - Optional comment Textarea
 *   - Conditionally rendered Approve (green) and Block (red) buttons based on permissions
 *   - Submit buttons disabled until rationale has ≥10 characters or mutation is loading
 *   - Read-only message for users without any decision permission
 *
 * Part of WO-075 Release Decision Review.
 */

import { Alert, Box, Button, Card, Group, Stack, Text, Textarea, Title } from '@mantine/core';
import { useState, type JSX } from 'react';
import { useDemoContext } from '@/hooks/useDemoContext';
import { MockDataBadge } from '@/components/common/MockDataBadge';

const RATIONALE_MIN = 10;
const RATIONALE_MAX = 2000;

export interface ReleaseDecisionCardProps {
  /** User permissions array from the auth store. */
  permissions: string[];
  /** Whether a mutation is in flight (disable buttons). */
  isSubmitting?: boolean;
  /** Called when user clicks Approve (passes rationale and optional comment). */
  onApprove: (rationale: string, comment: string) => void;
  /** Called when user clicks Block (passes rationale and optional comment). */
  onBlock: (rationale: string, comment: string) => void;
}

/**
 * Decision form with rationale textarea and conditional action buttons.
 *
 * @example
 * <ReleaseDecisionCard
 *   permissions={user.permissions}
 *   isSubmitting={mutation.isPending}
 *   onApprove={(rationale, comment) => openApproveModal(rationale, comment)}
 *   onBlock={(rationale, comment) => openBlockModal(rationale, comment)}
 * />
 */
export function ReleaseDecisionCard({
  permissions,
  isSubmitting = false,
  onApprove,
  onBlock,
}: ReleaseDecisionCardProps): JSX.Element {
  const [rationale, setRationale] = useState('');
  const [comment, setComment] = useState('');
  const { isDemo } = useDemoContext();

  const canApprove = permissions.includes('release.approve');
  const canBlock   = permissions.includes('release.block');
  const canDecide  = canApprove || canBlock;

  const rationaleValid = rationale.trim().length >= RATIONALE_MIN;
  const rationaleError =
    rationale.length > 0 && rationale.trim().length < RATIONALE_MIN
      ? `Rationale must be at least ${RATIONALE_MIN} characters.`
      : null;

  if (!canDecide) {
    return (
      <Card withBorder radius="md" p="md" data-testid="decision-card-readonly">
        <Stack gap="sm">
          <Group justify="space-between" align="center">
            <Title order={4}>Release Decision</Title>
            {isDemo && <MockDataBadge label="Demo Mode" />}
          </Group>
          <Alert color="gray" variant="light" data-testid="no-permission-message">
            You do not have permission to make release decisions.
          </Alert>
        </Stack>
      </Card>
    );
  }

  return (
    <Card withBorder radius="md" p="md" data-testid="decision-card">
      <Stack gap="md">
        <Group justify="space-between" align="center">
          <Title order={4}>Submit Release Decision</Title>
          {isDemo && <MockDataBadge label="Demo Mode" />}
        </Group>

        {/* Rationale — required */}
        <Box>
          <Textarea
            label="Rationale"
            description="Required. Explain your decision (this is permanently recorded in the audit log)."
            placeholder="Enter your decision rationale…"
            required
            minRows={3}
            maxRows={8}
            autosize
            value={rationale}
            onChange={(e) => setRationale(e.currentTarget.value)}
            maxLength={RATIONALE_MAX}
            error={rationaleError}
            data-testid="rationale-textarea"
          />
          <Text size="xs" c="dimmed" ta="right" mt={2}>
            {rationale.length} / {RATIONALE_MAX}
          </Text>
        </Box>

        {/* Comment — optional */}
        <Box>
          <Textarea
            label="Additional Comment (optional)"
            description="Any supplementary notes for this decision."
            placeholder="Optional: add context or conditions…"
            minRows={2}
            maxRows={6}
            autosize
            value={comment}
            onChange={(e) => setComment(e.currentTarget.value)}
            maxLength={RATIONALE_MAX}
            data-testid="comment-textarea"
          />
          <Text size="xs" c="dimmed" ta="right" mt={2}>
            {comment.length} / {RATIONALE_MAX}
          </Text>
        </Box>

        {/* Action buttons */}
        <Group gap="sm" justify="flex-end">
          {canApprove && (
            <Button
              color="green"
              disabled={!rationaleValid || isSubmitting}
              loading={isSubmitting}
              onClick={() => onApprove(rationale.trim(), comment.trim())}
              data-testid="approve-btn"
            >
              Approve Release
            </Button>
          )}
          {canBlock && (
            <Button
              color="red"
              disabled={!rationaleValid || isSubmitting}
              loading={isSubmitting}
              onClick={() => onBlock(rationale.trim(), comment.trim())}
              data-testid="block-btn"
            >
              Block Release
            </Button>
          )}
        </Group>
      </Stack>
    </Card>
  );
}
