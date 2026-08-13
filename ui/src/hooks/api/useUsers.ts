import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type Role } from '@/types';

// --------------------------------------------------------------------------
// Types
// --------------------------------------------------------------------------

export interface RbacUser {
  id: string;
  name: string;
  email: string;
  role: Role;
  last_role_change: string | null;
  created_at: string;
}

export interface RbacRoleInfo {
  name: string;
  description: string;
  permissions: string[];
}

export interface UsersResponse {
  users: RbacUser[];
  roles: RbacRoleInfo[];
}

export interface UpdateUserRoleResponse {
  id: string;
  name: string;
  role: Role;
  previous_role: Role;
  changed_at: string;
  audit_id: string;
}

// --------------------------------------------------------------------------
// Query keys
// --------------------------------------------------------------------------

export const userKeys = {
  all: ['rbac-users'] as const,
  list: () => ['rbac-users', 'list'] as const,
};

// --------------------------------------------------------------------------
// Hooks
// --------------------------------------------------------------------------

export function useUsers() {
  return useQuery({
    queryKey: userKeys.list(),
    queryFn: () => apiClient<UsersResponse>('/api/v1/admin/roles'),
  });
}

export function useUpdateUserRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
      apiClient<UpdateUserRoleResponse>(`/api/v1/admin/users/${userId}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}
