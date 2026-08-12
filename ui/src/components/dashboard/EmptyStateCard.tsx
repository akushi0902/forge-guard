import { type JSX } from 'react';
import { Alert, Card, List, Stack, Text, Title } from '@mantine/core';
import { Button } from '@/components/shared';
import { useRequestAssessment } from '@/hooks/api/useReleases';

export interface EmptyStateCardProps {
  /** Service ID for which to trigger the first assessment. */
  serviceId: string;
}

/**
 * Onboarding card shown when a service has no evaluations yet.
 * Provides a 3-step guide and a CTA to run the first assessment.
 *
 * @example
 * <EmptyStateCard serviceId="svc-001" />
 */
export function EmptyStateCard({ serviceId }: EmptyStateCardProps): JSX.Element {
  const mutation = useRequestAssessment();

  const handleRunAssessment = () => {
    mutation.mutate({ service_id: serviceId, commit_sha: 'HEAD' });
  };

  return (
    <Card withBorder style={{ textAlign: 'center', padding: '3rem' }}>
      <Stack align="center" gap="lg">
        <Text style={{ fontSize: 52, lineHeight: 1 }} aria-hidden="true">
          📊
        </Text>

        <Title order={3}>No evaluations yet</Title>

        <Text c="dimmed" maw={480}>
          Get started by running your first engineering health assessment. Follow
          these steps to see your service's health score and findings.
        </Text>

        <List
          type="ordered"
          spacing="xs"
          style={{ textAlign: 'left', width: '100%', maxWidth: 340 }}
        >
          <List.Item>Register your service</List.Item>
          <List.Item>Configure policies</List.Item>
          <List.Item>Trigger your first evaluation</List.Item>
        </List>

        {mutation.isError && (
          <Alert color="red" title="Assessment request failed" role="alert">
            Unable to start the assessment. Please try again or contact support.
          </Alert>
        )}

        <Button
          onClick={handleRunAssessment}
          loading={mutation.isPending}
          disabled={!serviceId}
          data-testid="run-assessment-btn"
        >
          Run First Assessment
        </Button>
      </Stack>
    </Card>
  );
}
