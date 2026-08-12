import { type JSX, useMemo, useState } from 'react';
import { Loader, Stack, Text, TextInput } from '@mantine/core';

import { useUsers } from '@/hooks/api/useUsers';
import { useAuthStore } from '@/stores/auth-store';
import { UsersTable } from './UsersTable';

export function UsersPanel(): JSX.Element {
  const [search, setSearch] = useState('');
  const { data, isLoading, isError } = useUsers();
  const currentUserId = useAuthStore((s) => s.user?.id ?? null);

  const filteredUsers = useMemo(() => {
    if (!data?.users) return [];
    const q = search.trim().toLowerCase();
    if (!q) return data.users;
    return data.users.filter(
      (u) =>
        u.name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q),
    );
  }, [data?.users, search]);

  if (isLoading) {
    return (
      <Stack align="center" py="xl">
        <Loader size="sm" />
      </Stack>
    );
  }

  if (isError) {
    return (
      <Stack align="center" py="xl">
        <Text c="red" size="sm" data-testid="users-error">
          Failed to load users. Please refresh and try again.
        </Text>
      </Stack>
    );
  }

  return (
    <Stack gap="md" data-testid="users-panel">
      <TextInput
        placeholder="Search by name or email…"
        value={search}
        onChange={(e) => setSearch(e.currentTarget.value)}
        data-testid="user-search"
        style={{ maxWidth: 400 }}
      />
      <UsersTable users={filteredUsers} currentUserId={currentUserId} />
    </Stack>
  );
}
