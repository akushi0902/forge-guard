/**
 * TabBar — horizontal tab navigation using Mantine Tabs.
 */

import { Tabs, type TabsProps } from '@mantine/core';
import { type ReactNode } from 'react';

export interface TabItem {
  value: string;
  label: string;
  icon?: ReactNode;
  disabled?: boolean;
}

export interface TabBarProps extends Omit<TabsProps, 'children'> {
  tabs: TabItem[];
  /** Content panel for the active tab. Render your panel externally if preferred. */
  children?: ReactNode;
}

/**
 * @example
 * const tabs = [
 *   { value: 'overview', label: 'Overview' },
 *   { value: 'findings', label: 'Findings' },
 * ];
 * <TabBar tabs={tabs} defaultValue="overview" />
 */
export function TabBar({ tabs, children, ...tabsProps }: TabBarProps) {
  return (
    <Tabs {...tabsProps}>
      <Tabs.List>
        {tabs.map((tab) => (
          <Tabs.Tab
            key={tab.value}
            value={tab.value}
            leftSection={tab.icon}
            disabled={tab.disabled}
          >
            {tab.label}
          </Tabs.Tab>
        ))}
      </Tabs.List>
      {children}
    </Tabs>
  );
}
