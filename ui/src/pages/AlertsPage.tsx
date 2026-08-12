/**
 * Alerts placeholder page — to be implemented in later WOs.
 */
import { type JSX } from 'react';
import { Stack, Text, Title } from '@mantine/core';

export function AlertsPage(): JSX.Element {
  return (
    <Stack gap="md">
      <Title order={2}>Alerts</Title>
      <Text c="dimmed">Platform alerts — coming soon.</Text>
    </Stack>
  );
}
