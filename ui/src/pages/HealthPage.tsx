/**
 * Service Health placeholder page — to be implemented in later WOs.
 */
import { type JSX } from 'react';
import { Stack, Text, Title } from '@mantine/core';

export function HealthPage(): JSX.Element {
  return (
    <Stack gap="md">
      <Title order={2}>Service Health</Title>
      <Text c="dimmed">Per-service policy evaluation — coming soon.</Text>
    </Stack>
  );
}
