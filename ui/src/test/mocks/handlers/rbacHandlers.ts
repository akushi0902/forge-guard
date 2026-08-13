import { http, HttpResponse } from 'msw';

import { Role } from '@/types';
import { type RbacUser } from '@/hooks/api/useUsers';
import { USERS_RESPONSE_FIXTURE } from '@/test/fixtures/rbacData';

let users: RbacUser[] = [...USERS_RESPONSE_FIXTURE.users];
const PLATFORM_ADMIN_ID = 'usr-009'; // Isabel Torres — the only admin initially

export function resetRbacUsers() {
  users = [...USERS_RESPONSE_FIXTURE.users];
}

export const rbacHandlers = [
  // GET /api/v1/admin/roles — list all users with roles
  http.get('/api/v1/admin/roles', () =>
    HttpResponse.json({ users, roles: USERS_RESPONSE_FIXTURE.roles }),
  ),

  // PUT /api/v1/admin/users/:id/role — update a user's role
  http.put('/api/v1/admin/users/:id/role', async ({ params, request }) => {
    const { id } = params as { id: string };
    const body = (await request.json()) as { role: Role };

    const user = users.find((u) => u.id === id);
    if (!user) {
      return HttpResponse.json({ detail: 'User not found.' }, { status: 404 });
    }

    // Prevent removing the last Platform Admin
    if (
      user.role === Role.PlatformAdmin &&
      body.role !== Role.PlatformAdmin &&
      users.filter((u) => u.role === Role.PlatformAdmin).length <= 1
    ) {
      return HttpResponse.json(
        {
          detail: 'Cannot change role: this is the last Platform Admin. Assign another admin first.',
          error_code: 'LAST_ADMIN',
        },
        { status: 400 },
      );
    }

    const previousRole = user.role;
    users = users.map((u) =>
      u.id === id
        ? { ...u, role: body.role, last_role_change: new Date().toISOString() }
        : u,
    );

    return HttpResponse.json({
      id,
      name: user.name,
      role: body.role,
      previous_role: previousRole,
      changed_at: new Date().toISOString(),
      audit_id: `audit-${Date.now()}`,
    });
  }),
];
