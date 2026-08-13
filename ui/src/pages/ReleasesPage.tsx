/**
 * Release Assessments page — placeholder; shows empty state until release listing is implemented.
 */
import { type JSX } from 'react';
import { Stack, Title } from '@mantine/core';
import { useNavigate } from 'react-router-dom';
import { ReleasesEmptyState } from '@/components/empty-states/ReleasesEmptyState';

export function ReleasesPage(): JSX.Element {
  const navigate = useNavigate();

  return (
    <Stack gap="md">
      <Title order={2}>Release Assessments</Title>
      <ReleasesEmptyState onRequestAssessment={() => void navigate('/releases/new')} />
    </Stack>
  );
}
