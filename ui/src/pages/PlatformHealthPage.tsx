/**
 * Platform Health placeholder page — to be implemented in later WOs.
 */
import { type JSX } from 'react';
import { Stack, Text, Title } from '@mantine/core';

export function PlatformHealthPage(): JSX.Element {
  return (
    <Stack gap="md">
      <Title order={2}>Platform Health</Title>
      <Text c="dimmed">Platform monitoring — coming soon.</Text>
    </Stack>
  );
}
