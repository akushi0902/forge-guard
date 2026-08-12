import { type JSX } from 'react';
import {
  Button,
  Group,
  Modal,
  NumberInput,
  Select,
  Stack,
  Textarea,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';

import { PolicyDimension, PolicySeverity } from '@/types/api';
import { useCreatePolicy } from '@/hooks/api/usePolicies';
import { notifications } from '@mantine/notifications';
import { ApiError } from '@/types/errors';

const DIMENSION_OPTIONS = [
  { value: PolicyDimension.CodeQuality, label: 'Code Quality' },
  { value: PolicyDimension.TestCoverage, label: 'Test Coverage' },
  { value: PolicyDimension.Security, label: 'Security' },
  { value: PolicyDimension.Documentation, label: 'Documentation' },
  { value: PolicyDimension.OperationsReadiness, label: 'Operations Readiness' },
];

const SEVERITY_OPTIONS = [
  { value: PolicySeverity.Critical, label: 'Critical' },
  { value: PolicySeverity.High, label: 'High' },
  { value: PolicySeverity.Medium, label: 'Medium' },
  { value: PolicySeverity.Low, label: 'Low' },
];

interface CreateRuleFormValues {
  name: string;
  dimension: PolicyDimension | '';
  severity: PolicySeverity | '';
  threshold: number | '';
  description: string;
}

export interface CreateRuleModalProps {
  opened: boolean;
  onClose: () => void;
}

export function CreateRuleModal({ opened, onClose }: CreateRuleModalProps): JSX.Element {
  const { mutateAsync: createRule, isPending } = useCreatePolicy();

  const form = useForm<CreateRuleFormValues>({
    initialValues: {
      name: '',
      dimension: '',
      severity: '',
      threshold: '',
      description: '',
    },
    validate: {
      name: (v) =>
        v.trim().length < 3 ? 'Name must be at least 3 characters' : null,
      dimension: (v) => (!v ? 'Dimension is required' : null),
      severity: (v) => (!v ? 'Severity is required' : null),
      threshold: (v) => {
        if (v === '' || v === null || v === undefined) return 'Threshold is required';
        if (typeof v === 'number' && (v < 0 || v > 100)) return 'Threshold must be between 0 and 100';
        return null;
      },
      description: (v) =>
        v.length > 500 ? 'Description must be 500 characters or less' : null,
    },
  });

  async function handleSubmit(values: CreateRuleFormValues) {
    try {
      await createRule({
        name: values.name.trim(),
        dimension: values.dimension as PolicyDimension,
        severity: values.severity as PolicySeverity,
        threshold: values.threshold as number,
        description: values.description.trim() || undefined,
      });
      notifications.show({
        title: 'Rule created',
        message: `"${values.name.trim()}" was added successfully.`,
        color: 'green',
      });
      form.reset();
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        form.setFieldError('name', 'A rule with this name already exists.');
      } else {
        notifications.show({
          title: 'Failed to create rule',
          message: 'An unexpected error occurred. Please try again.',
          color: 'red',
        });
      }
    }
  }

  function handleClose() {
    form.reset();
    onClose();
  }

  return (
    <Modal
      opened={opened}
      onClose={handleClose}
      title="Create Policy Rule"
      size="md"
      data-testid="create-rule-modal"
    >
      <form onSubmit={form.onSubmit(handleSubmit)} data-testid="create-rule-form">
        <Stack gap="sm">
          <TextInput
            label="Rule Name"
            placeholder="e.g. No critical SQL injection vulnerabilities"
            required
            data-testid="field-name"
            {...form.getInputProps('name')}
          />
          <Select
            label="Dimension"
            placeholder="Select dimension"
            data={DIMENSION_OPTIONS}
            required
            data-testid="field-dimension"
            {...form.getInputProps('dimension')}
          />
          <Select
            label="Severity"
            placeholder="Select severity"
            data={SEVERITY_OPTIONS}
            required
            data-testid="field-severity"
            {...form.getInputProps('severity')}
          />
          <NumberInput
            label="Threshold"
            placeholder="0–100"
            min={0}
            max={100}
            required
            data-testid="field-threshold"
            {...form.getInputProps('threshold')}
          />
          <Textarea
            label="Description"
            placeholder="Optional description (max 500 characters)"
            maxLength={500}
            autosize
            minRows={2}
            maxRows={4}
            data-testid="field-description"
            {...form.getInputProps('description')}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={handleClose} disabled={isPending}>
              Cancel
            </Button>
            <Button type="submit" loading={isPending} data-testid="submit-btn">
              Create Rule
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
