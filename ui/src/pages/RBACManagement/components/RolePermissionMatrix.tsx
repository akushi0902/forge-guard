import { type JSX } from 'react';
import { ScrollArea, Table, Text } from '@mantine/core';

import {
  ALL_PERMISSIONS,
  ALL_ROLES,
  PERMISSION_LABELS,
  ROLE_LABELS,
  ROLE_PERMISSION_MATRIX,
} from '@/constants/rolePermissions';

export function RolePermissionMatrix(): JSX.Element {
  return (
    <ScrollArea data-testid="role-permission-matrix">
      <Table
        withTableBorder
        withColumnBorders
        highlightOnHover
        stickyHeader
        style={{ minWidth: 700 }}
      >
        <Table.Thead>
          <Table.Tr>
            <Table.Th style={{ minWidth: 180 }}>Permission</Table.Th>
            {ALL_ROLES.map((role) => (
              <Table.Th key={role} style={{ textAlign: 'center', minWidth: 110 }}>
                <Text size="xs" fw={600}>
                  {ROLE_LABELS[role]}
                </Text>
              </Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {ALL_PERMISSIONS.map((permission) => (
            <Table.Tr key={permission} data-testid={`matrix-row-${permission}`}>
              <Table.Td>
                <Text size="sm" fw={500}>
                  {PERMISSION_LABELS[permission]}
                </Text>
                <Text size="xs" c="dimmed">
                  {permission}
                </Text>
              </Table.Td>
              {ALL_ROLES.map((role) => (
                <Table.Td
                  key={role}
                  style={{ textAlign: 'center' }}
                  data-testid={`matrix-cell-${permission}-${role}`}
                >
                  {ROLE_PERMISSION_MATRIX[role][permission] ? (
                    <Text size="lg" c="green" aria-label="granted">
                      ✓
                    </Text>
                  ) : (
                    <Text size="sm" c="dimmed" aria-label="not granted">
                      —
                    </Text>
                  )}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}
