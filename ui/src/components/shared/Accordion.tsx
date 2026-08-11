/**
 * Accordion — collapsible section list using Mantine Accordion.
 */

import {
  Accordion as MantineAccordion,
  type AccordionProps as MantineAccordionProps,
} from '@mantine/core';
import { type ReactNode } from 'react';

export interface AccordionItem {
  value: string;
  label: string;
  content: ReactNode;
  icon?: ReactNode;
}

export interface AccordionProps
  extends Omit<MantineAccordionProps, 'children'> {
  items: AccordionItem[];
}

/**
 * @example
 * <Accordion items={[
 *   { value: 'security', label: 'Security', content: <SecurityFindings /> },
 *   { value: 'tests', label: 'Test Coverage', content: <CoverageDetail /> },
 * ]} />
 */
export function Accordion({ items, ...accordionProps }: AccordionProps) {
  return (
    <MantineAccordion {...accordionProps}>
      {items.map((item) => (
        <MantineAccordion.Item key={item.value} value={item.value}>
          <MantineAccordion.Control icon={item.icon}>
            {item.label}
          </MantineAccordion.Control>
          <MantineAccordion.Panel>{item.content}</MantineAccordion.Panel>
        </MantineAccordion.Item>
      ))}
    </MantineAccordion>
  );
}
