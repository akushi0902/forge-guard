/**
 * ForbiddenPage — 403 Access Denied page.
 *
 * Shown when a user navigates to a route they lack permission to access.
 * Displays the missing permission in human-readable form, the role that
 * grants it, and a call-to-action to contact their Platform Admin.
 *
 * NOTE: Permission names are displayed as human-readable labels (e.g.
 * "Manage Policies") — never as raw internal slugs — to avoid aiding
 * privilege escalation.
 */

import { Button, Center, Stack, Text, Title } from '@mantine/core';
import { type JSX } from 'react';
import { Link } from 'react-router-dom';
import {
  getPermissionLabel,
  getRequiredRoleForPermission,
} from '@/config/permissions';

export interface ForbiddenPageProps {
  /** The permission slug the user is missing. */
  missingPermission?: string;
}

export function ForbiddenPage({ missingPermission }: ForbiddenPageProps): JSX.Element {
  const permissionLabel = missingPermission
    ? getPermissionLabel(missingPermission)
    : 'the required permission';

  const requiredRole = missingPermission
    ? getRequiredRoleForPermission(missingPermission)
    : 'Platform Admin';

  return (
    <Center style={{ minHeight: '100vh' }} role="main" aria-label="Access denied">
      <Stack align="center" gap="md" maw={480} ta="center">
        <Text size="xl" fw={700} c="red" aria-label="403">
          403
        </Text>
        <Title order={2}>Access Denied</Title>
        <Text c="dimmed" data-testid="forbidden-message">
          This action requires the <strong>{permissionLabel}</strong> permission assigned
          to the <strong>{requiredRole}</strong> role. Contact your Platform Admin for access.
        </Text>
        <Button
          component={Link}
          to="/dashboard"
          variant="light"
          aria-label="Return to Dashboard"
        >
          Return to Dashboard
        </Button>
      </Stack>
    </Center>
  );
}
