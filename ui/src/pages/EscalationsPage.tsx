/**
 * Escalations placeholder page — to be implemented in later WOs.
 */
import { type JSX } from 'react';
import { Stack, Text, Title } from '@mantine/core';

export function EscalationsPage(): JSX.Element {
  return (
    <Stack gap="md">
      <Title order={2}>Escalations</Title>
      <Text c="dimmed">Escalated security findings — coming soon.</Text>
    </Stack>
  );
}
