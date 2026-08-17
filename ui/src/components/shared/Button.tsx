/**
 * ForgeGuard Button — wraps Mantine Button with the four design-system variants.
 *
 * Variants:
 *   primary     — solid brand-blue fill (default)
 *   secondary   — outlined brand-blue, transparent fill
 *   ghost       — no border, subtle hover
 *   destructive — solid danger-red fill
 *
 * All variants support three sizes (sm / md / lg) and disabled / loading states.
 */

import {
  Button as MantineButton,
  type ButtonProps as MantineButtonProps,
} from '@mantine/core';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'destructive';

export interface ButtonProps
  extends Omit<MantineButtonProps, 'variant' | 'color'>,
    Omit<ComponentPropsWithoutRef<'button'>, 'color'> {
  /** Visual style of the button. */
  variant?: ButtonVariant;
}

const VARIANT_MAP: Record<
  ButtonVariant,
  Pick<MantineButtonProps, 'variant' | 'color'>
> = {
  primary: { variant: 'filled', color: 'brand' },
  secondary: { variant: 'outline', color: 'brand' },
  ghost: { variant: 'subtle', color: 'brand' },
  destructive: { variant: 'filled', color: 'danger' },
};

/**
 * Application button with ForgeGuard design-system variants.
 *
 * @example
 * <Button variant="primary" size="md" onClick={handleSave}>Save</Button>
 * <Button variant="destructive" loading>Deleting…</Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', ...rest }, ref) => {
    const { variant: mantineVariant, color } = VARIANT_MAP[variant];
    return (
      <MantineButton
        ref={ref}
        variant={mantineVariant}
        color={color}
        {...rest}
      />
    );
  },
);

Button.displayName = 'Button';
