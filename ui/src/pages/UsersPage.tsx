/**
 * Users placeholder page — to be implemented in later WOs.
 */
import { type JSX } from 'react';
import { Stack, Text, Title } from '@mantine/core';

export function UsersPage(): JSX.Element {
  return (
    <Stack gap="md">
      <Title order={2}>Users</Title>
      <Text c="dimmed">User management — coming soon.</Text>
    </Stack>
  );
}
