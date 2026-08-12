/**
 * AssessmentRequestForm — form for submitting a release risk assessment request (WO-074).
 *
 * Validates:
 *   - service_id:   required
 *   - commit_sha:   required, exactly 40 hex chars (trimmed)
 *   - pr_reference: optional
 */

import { type JSX } from 'react';
import { Alert, Anchor, Button, Select, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';

import { useRequestReleaseAssessment } from '@/hooks/api/useReleases';
import { useServices } from '@/hooks/api/useServices';

export interface AssessmentRequestFormProps {
  onAssessmentCreated: (assessmentId: string) => void;
  defaultServiceId?: string;
}

const COMMIT_SHA_REGEX = /^[0-9a-f]{40}$/i;

export function AssessmentRequestForm({
  onAssessmentCreated,
  defaultServiceId,
}: AssessmentRequestFormProps): JSX.Element {
  const { data: servicesData, isLoading: servicesLoading } = useServices();
  const mutation = useRequestReleaseAssessment();

  const form = useForm({
    initialValues: {
      service_id: defaultServiceId ?? '',
      commit_sha: '',
      pr_reference: '',
    },
    validate: {
      service_id: (value) => (!value ? 'Please select a service' : null),
      commit_sha: (value) => {
        const trimmed = value.trim();
        if (!trimmed) return 'Commit SHA is required';
        if (!COMMIT_SHA_REGEX.test(trimmed))
          return 'Commit SHA must be exactly 40 hexadecimal characters';
        return null;
      },
    },
  });

  const serviceOptions =
    servicesData?.items.map((s) => ({ value: s.id, label: s.name })) ?? [];

  const noServices = !servicesLoading && serviceOptions.length === 0;

  const handleSubmit = form.onSubmit(async (values) => {
    try {
      const result = await mutation.mutateAsync({
        service_id: values.service_id,
        commit_sha: values.commit_sha.trim(),
        pr_reference: values.pr_reference.trim() || undefined,
      });
      onAssessmentCreated(result.id);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Unable to submit assessment request';
      notifications.show({
        title: 'Request failed',
        message,
        color: 'red',
      });
    }
  });

  return (
    <form onSubmit={handleSubmit} aria-label="Assessment request form">
      <Stack gap="md">
        {noServices ? (
          <Alert color="yellow" title="No services available">
            <Text size="sm">
              No services registered —{' '}
              <Anchor href="/services">register a service first</Anchor>.
            </Text>
          </Alert>
        ) : (
          <Select
            label="Service"
            placeholder="Select a service"
            data={serviceOptions}
            value={form.values.service_id || null}
            onChange={(value) => form.setFieldValue('service_id', value ?? '')}
            error={form.errors['service_id'] as string | undefined}
            disabled={servicesLoading || mutation.isPending}
            required
            aria-label="Service"
          />
        )}

        <TextInput
          label="Commit SHA"
          placeholder="e.g., a1b2c3d4e5f6..."
          styles={{ input: { fontFamily: 'monospace' } }}
          disabled={mutation.isPending}
          required
          {...form.getInputProps('commit_sha')}
        />

        <TextInput
          label="PR Reference"
          placeholder="e.g., #123 or https://github.com/org/repo/pull/123"
          disabled={mutation.isPending}
          {...form.getInputProps('pr_reference')}
        />

        <Button
          type="submit"
          loading={mutation.isPending}
          disabled={mutation.isPending || noServices}
        >
          Request Assessment
        </Button>
      </Stack>
    </form>
  );
}
