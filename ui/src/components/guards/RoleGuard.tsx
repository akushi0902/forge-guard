/**
 * RoleGuard — permission gate for feature routes.
 *
 * Reads user.permissions from the auth store and checks whether the
 * required permission is present. Renders children on success; renders
 * ForbiddenPage on failure.
 *
 * NOTE: Client-side convenience only. Server-side RBAC is authoritative.
 */

import { type JSX, type ReactNode } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { ForbiddenPage } from '@/pages/ForbiddenPage';

export interface RoleGuardProps {
  /** Permission slug that the user must possess to access the guarded content. */
  requiredPermission: string;
  children: ReactNode;
}

export function RoleGuard({ requiredPermission, children }: RoleGuardProps): JSX.Element {
  const permissions = useAuthStore((s) => s.user?.permissions ?? []);
  const hasPermission = permissions.includes(requiredPermission);

  if (!hasPermission) {
    return <ForbiddenPage missingPermission={requiredPermission} />;
  }

  return <>{children}</>;
}
