/**
 * Release Assessments placeholder page — to be implemented in later WOs.
 */
import { type JSX } from 'react';
import { Stack, Text, Title } from '@mantine/core';

export function ReleasesPage(): JSX.Element {
  return (
    <Stack gap="md">
      <Title order={2}>Release Assessments</Title>
      <Text c="dimmed">Release risk scoring and decisions — coming soon.</Text>
    </Stack>
  );
}
