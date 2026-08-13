/**
 * Dropdown — action menu using Mantine Menu.
 */

import { Menu, type MenuProps, UnstyledButton } from '@mantine/core';
import { type ReactNode } from 'react';

export interface DropdownItem {
  key: string;
  label: string;
  icon?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  color?: string;
  /** If true, renders a Divider above this item. */
  divider?: boolean;
}

export interface DropdownProps extends Omit<MenuProps, 'children'> {
  /** The trigger element. */
  trigger: ReactNode;
  items: DropdownItem[];
  triggerAriaLabel?: string;
}

/**
 * @example
 * <Dropdown
 *   trigger={<Button variant="ghost">Actions</Button>}
 *   items={[
 *     { key: 'edit', label: 'Edit', onClick: handleEdit },
 *     { key: 'delete', label: 'Delete', color: 'red', onClick: handleDelete },
 *   ]}
 * />
 */
export function Dropdown({ trigger, items, triggerAriaLabel, ...menuProps }: DropdownProps) {
  return (
    <Menu {...menuProps}>
      <Menu.Target>
        <UnstyledButton aria-label={triggerAriaLabel}>{trigger}</UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        {items.map((item) => (
          <div key={item.key}>
            {item.divider && <Menu.Divider />}
            <Menu.Item
              leftSection={item.icon}
              onClick={item.onClick}
              disabled={item.disabled}
              color={item.color}
            >
              {item.label}
            </Menu.Item>
          </div>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}
