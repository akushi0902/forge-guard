/**
 * ModalDialog — accessible confirm/cancel modal using Mantine Modal.
 *
 * Focus is automatically trapped within the modal by Mantine and restored
 * on close. The modal renders inside a Portal so z-index stacking is handled.
 */

import {
  Button,
  Group,
  Modal as MantineModal,
  type ModalProps as MantineModalProps,
  Text,
} from '@mantine/core';
import { type ReactNode } from 'react';

export interface ModalDialogProps
  extends Omit<MantineModalProps, 'children'> {
  /** Modal body content. */
  children: ReactNode;
  /** Label for the primary action button. */
  confirmLabel?: string;
  /** Label for the cancel button. */
  cancelLabel?: string;
  /** Called when the user clicks the confirm button. */
  onConfirm?: () => void;
  /** If true, the confirm button shows a loading spinner. */
  confirmLoading?: boolean;
  /** Color of the confirm button. Defaults to 'brand'. */
  confirmColor?: string;
  /** If true, no footer buttons are rendered (content-only modal). */
  contentOnly?: boolean;
}

/**
 * @example
 * <ModalDialog
 *   opened={isOpen}
 *   onClose={() => setOpen(false)}
 *   title="Confirm deletion"
 *   confirmLabel="Delete"
 *   confirmColor="red"
 *   onConfirm={handleDelete}
 * >
 *   Are you sure you want to delete this service?
 * </ModalDialog>
 */
export function ModalDialog({
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onClose,
  confirmLoading,
  confirmColor = 'brand',
  contentOnly = false,
  ...modalProps
}: ModalDialogProps) {
  return (
    <MantineModal onClose={onClose} {...modalProps}>
      <Text component="div">{children}</Text>
      {!contentOnly && (
        <Group justify="flex-end" mt="lg">
          <Button variant="subtle" color="neutral" onClick={onClose}>
            {cancelLabel}
          </Button>
          <Button
            color={confirmColor}
            onClick={onConfirm}
            loading={confirmLoading}
          >
            {confirmLabel}
          </Button>
        </Group>
      )}
    </MantineModal>
  );
}
