/**
 * ForgeGuard form input components.
 *
 * Each component wraps the corresponding Mantine form component with a
 * consistent label / error / description prop pattern and ForgeGuard default
 * styling. All components forward refs and accept standard HTML attributes.
 */

import {
  Checkbox,
  type CheckboxProps,
  Group,
  Radio,
  type RadioProps,
  Select as MantineSelect,
  type SelectProps as MantineSelectProps,
  Switch,
  type SwitchProps,
  Textarea as MantineTextarea,
  type TextareaProps as MantineTextareaProps,
  TextInput as MantineTextInput,
  type TextInputProps as MantineTextInputProps,
  Stack,
} from '@mantine/core';
import { forwardRef } from 'react';

// ---------------------------------------------------------------------------
// TextInput
// ---------------------------------------------------------------------------

export type TextInputProps = MantineTextInputProps;

export const TextInput = forwardRef<HTMLInputElement, TextInputProps>(
  (props, ref) => <MantineTextInput ref={ref} {...props} />,
);
TextInput.displayName = 'TextInput';

// ---------------------------------------------------------------------------
// Textarea
// ---------------------------------------------------------------------------

export type TextareaProps = MantineTextareaProps;

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (props, ref) => <MantineTextarea ref={ref} {...props} />,
);
Textarea.displayName = 'Textarea';

// ---------------------------------------------------------------------------
// Select
// ---------------------------------------------------------------------------

export type SelectProps = MantineSelectProps;

export const Select = forwardRef<HTMLInputElement, SelectProps>(
  (props, ref) => <MantineSelect ref={ref} {...props} />,
);
Select.displayName = 'Select';

// ---------------------------------------------------------------------------
// Toggle (Switch)
// ---------------------------------------------------------------------------

export interface ToggleProps extends Omit<SwitchProps, 'checked' | 'onChange'> {
  checked?: boolean;
  onChange?: (checked: boolean) => void;
}

export const Toggle = forwardRef<HTMLInputElement, ToggleProps>(
  ({ onChange, ...rest }, ref) => (
    <Switch
      ref={ref}
      onChange={(e) => onChange?.(e.currentTarget.checked)}
      {...rest}
    />
  ),
);
Toggle.displayName = 'Toggle';

// ---------------------------------------------------------------------------
// CheckboxGroup
// ---------------------------------------------------------------------------

export interface CheckboxOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface CheckboxGroupProps {
  label?: string;
  options: CheckboxOption[];
  value?: string[];
  onChange?: (value: string[]) => void;
  error?: string;
}

export function CheckboxGroup({
  label,
  options,
  value = [],
  onChange,
  error,
}: CheckboxGroupProps) {
  const handleChange = (optValue: string, checked: boolean) => {
    if (!onChange) return;
    const next = checked
      ? [...value, optValue]
      : value.filter((v) => v !== optValue);
    onChange(next);
  };

  return (
    <Stack gap="xs">
      {label && <span style={{ fontSize: 14, fontWeight: 500 }}>{label}</span>}
      {options.map((opt) => (
        <Checkbox
          key={opt.value}
          label={opt.label}
          disabled={opt.disabled}
          checked={value.includes(opt.value)}
          onChange={(e) => handleChange(opt.value, e.currentTarget.checked)}
        />
      ))}
      {error && <span style={{ color: 'var(--mantine-color-danger-6)', fontSize: 12 }}>{error}</span>}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// RadioGroup
// ---------------------------------------------------------------------------

export interface RadioGroupOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface RadioGroupProps {
  label?: string;
  options: RadioGroupOption[];
  value?: string;
  onChange?: (value: string) => void;
  error?: string;
  name?: string;
}

export function RadioGroup({
  label,
  options,
  value,
  onChange,
  error,
  name,
}: RadioGroupProps) {
  return (
    <Radio.Group
      label={label}
      value={value}
      onChange={onChange}
      name={name}
      error={error}
    >
      <Group mt="xs" gap="md">
        {options.map((opt) => (
          <Radio
            key={opt.value}
            value={opt.value}
            label={opt.label}
            disabled={opt.disabled}
          />
        ))}
      </Group>
    </Radio.Group>
  );
}
