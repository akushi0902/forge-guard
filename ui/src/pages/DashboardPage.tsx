/**
 * Dashboard placeholder page — to be implemented in later WOs.
 */
import { type JSX } from 'react';
import { Stack, Text, Title } from '@mantine/core';

export function DashboardPage(): JSX.Element {
  return (
    <Stack gap="md">
      <Title order={2}>Dashboard</Title>
      <Text c="dimmed">Engineering health overview — coming soon.</Text>
    </Stack>
  );
}
