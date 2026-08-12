/**
 * RBAC Management page (WO-080).
 *
 * Two-tab interface for Platform Admins to manage user roles:
 *   - Users — searchable table with inline role dropdowns and confirmation modal
 *   - Roles & Permissions — read-only role-permission matrix grid
 *
 * Protected by RoleGuard requiring the 'rbac.manage' permission.
 */

import { type JSX } from 'react';
import { Container, Stack, Tabs, Title } from '@mantine/core';

import { RoleGuard } from '@/components/guards/RoleGuard';
import { UsersPanel } from './components/UsersPanel';
import { RolePermissionMatrix } from './components/RolePermissionMatrix';

function RBACManagementContent(): JSX.Element {
  return (
    <Container size="xl" py="md">
      <Stack gap="lg">
        <Title order={2}>RBAC Management</Title>

        <Tabs defaultValue="users" data-testid="rbac-tabs">
          <Tabs.List>
            <Tabs.Tab value="users" data-testid="tab-users">
              Users
            </Tabs.Tab>
            <Tabs.Tab value="matrix" data-testid="tab-matrix">
              Roles &amp; Permissions
            </Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="users" pt="md">
            <UsersPanel />
          </Tabs.Panel>

          <Tabs.Panel value="matrix" pt="md">
            <RolePermissionMatrix />
          </Tabs.Panel>
        </Tabs>
      </Stack>
    </Container>
  );
}

export function RBACManagement(): JSX.Element {
  return (
    <RoleGuard requiredPermission="rbac.manage">
      <RBACManagementContent />
    </RoleGuard>
  );
}
