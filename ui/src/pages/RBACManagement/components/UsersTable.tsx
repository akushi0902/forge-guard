import { type JSX, useState } from 'react';
import {
  Center,
  Select,
  Table,
  Text,
  Tooltip,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';

import { type Role } from '@/types';
import { ROLE_LABELS, ALL_ROLES } from '@/constants/rolePermissions';
import { maskEmail } from '@/utils/piiMask';
import { useUpdateUserRole, type RbacUser } from '@/hooks/api/useUsers';
import { ConfirmRoleChangeModal } from './ConfirmRoleChangeModal';
import { ApiError } from '@/types/errors';

const ROLE_OPTIONS = ALL_ROLES.map((r) => ({
  value: r,
  label: ROLE_LABELS[r],
}));

interface PendingChange {
  user: RbacUser;
  newRole: Role;
}

export interface UsersTableProps {
  users: RbacUser[];
  currentUserId: string | null;
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function UsersTable({ users, currentUserId }: UsersTableProps): JSX.Element {
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
  const { mutateAsync: updateRole, isPending } = useUpdateUserRole();

  async function handleConfirm() {
    if (!pending) return;
    setModalError(null);
    try {
      await updateRole({ userId: pending.user.id, role: pending.newRole });
      notifications.show({
        title: 'Role updated',
        message: `${pending.user.name}'s role changed to ${ROLE_LABELS[pending.newRole]}.`,
        color: 'green',
      });
      setPending(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setModalError(err.detail);
      } else {
        notifications.show({
          title: 'Role change failed',
          message: 'An unexpected error occurred. Please try again.',
          color: 'red',
        });
        setPending(null);
      }
    }
  }

  if (users.length === 0) {
    return (
      <Center py="xl" data-testid="users-empty-state">
        <Text c="dimmed" size="sm">No users match your search.</Text>
      </Center>
    );
  }

  return (
    <>
      <Table striped highlightOnHover data-testid="users-table">
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Name</Table.Th>
            <Table.Th>Email</Table.Th>
            <Table.Th>Current Role</Table.Th>
            <Table.Th>Last Role Change</Table.Th>
            <Table.Th>Actions</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {users.map((user) => {
            const isSelf = user.id === currentUserId;
            return (
              <Table.Tr key={user.id} data-testid={`user-row-${user.id}`}>
                <Table.Td>
                  <Text size="sm" fw={500} truncate style={{ maxWidth: 200 }}>
                    {user.name}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed" data-testid={`email-${user.id}`}>
                    {maskEmail(user.email)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm">
                    {ROLE_LABELS[user.role] ?? user.role}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" c="dimmed">
                    {formatDate(user.last_role_change)}
                  </Text>
                </Table.Td>
                <Table.Td>
                  {isSelf ? (
                    <Tooltip label="You cannot change your own role" withArrow>
                      <Select
                        data={ROLE_OPTIONS}
                        value={user.role}
                        disabled
                        size="xs"
                        style={{ minWidth: 150 }}
                        aria-label={`Role for ${user.name} (self)`}
                        data-testid={`role-select-${user.id}`}
                      />
                    </Tooltip>
                  ) : (
                    <Select
                      data={ROLE_OPTIONS}
                      value={user.role}
                      onChange={(newRole) => {
                        if (newRole && newRole !== user.role) {
                          setModalError(null);
                          setPending({ user, newRole: newRole as Role });
                        }
                      }}
                      size="xs"
                      style={{ minWidth: 150 }}
                      aria-label={`Change role for ${user.name}`}
                      data-testid={`role-select-${user.id}`}
                    />
                  )}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>

      {pending && (
        <ConfirmRoleChangeModal
          opened={Boolean(pending)}
          userName={pending.user.name}
          currentRole={pending.user.role}
          newRole={pending.newRole}
          isPending={isPending}
          error={modalError}
          onConfirm={handleConfirm}
          onClose={() => {
            setPending(null);
            setModalError(null);
          }}
        />
      )}
    </>
  );
}
