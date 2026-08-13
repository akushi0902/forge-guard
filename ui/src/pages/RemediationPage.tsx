/**
 * Remediation page — placeholder; shows empty state until remediation listing is implemented.
 */
import { type JSX } from 'react';
import { Stack, Title } from '@mantine/core';
import { useNavigate } from 'react-router-dom';
import { RemediationEmptyState } from '@/components/empty-states/RemediationEmptyState';

export function RemediationPage(): JSX.Element {
  const navigate = useNavigate();

  return (
    <Stack gap="md">
      <Title order={2}>Remediation</Title>
      <RemediationEmptyState onViewFindings={() => void navigate('/health')} />
    </Stack>
  );
}
