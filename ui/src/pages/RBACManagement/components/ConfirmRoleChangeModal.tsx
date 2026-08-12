import { type JSX } from 'react';
import { Badge, Button, Group, Modal, Stack, Text } from '@mantine/core';

import { ROLE_LABELS } from '@/constants/rolePermissions';
import { type Role } from '@/types';

const ROLE_COLORS: Partial<Record<Role, string>> = {
  platform_admin: 'red',
  engineering_manager: 'grape',
  tech_lead: 'blue',
  security_reviewer: 'orange',
  developer: 'teal',
  operator: 'gray',
};

export interface ConfirmRoleChangeModalProps {
  opened: boolean;
  userName: string;
  currentRole: Role;
  newRole: Role;
  isPending: boolean;
  error: string | null;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmRoleChangeModal({
  opened,
  userName,
  currentRole,
  newRole,
  isPending,
  error,
  onConfirm,
  onClose,
}: ConfirmRoleChangeModalProps): JSX.Element {
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="Confirm Role Change"
      size="sm"
      data-testid="confirm-role-modal"
    >
      <Stack gap="md">
        <Text size="sm">
          You are about to change the role for{' '}
          <Text component="span" fw={600}>{userName}</Text>:
        </Text>

        <Group gap="sm" align="center" justify="center">
          <Badge
            color={ROLE_COLORS[currentRole] ?? 'gray'}
            size="lg"
            data-testid="current-role-badge"
          >
            {ROLE_LABELS[currentRole] ?? currentRole}
          </Badge>
          <Text size="sm" c="dimmed">→</Text>
          <Badge
            color={ROLE_COLORS[newRole] ?? 'gray'}
            size="lg"
            data-testid="new-role-badge"
          >
            {ROLE_LABELS[newRole] ?? newRole}
          </Badge>
        </Group>

        <Text size="xs" c="dimmed">
          This change takes effect immediately and will be recorded in the audit log.
        </Text>

        {error && (
          <Text size="sm" c="red" data-testid="modal-error">
            {error}
          </Text>
        )}

        <Group justify="flex-end" mt="xs">
          <Button variant="default" onClick={onClose} disabled={isPending}>
            Cancel
          </Button>
          <Button
            color="blue"
            onClick={onConfirm}
            loading={isPending}
            data-testid="confirm-btn"
          >
            Confirm
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
