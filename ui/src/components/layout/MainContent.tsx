/**
 * MainContent — page content wrapper.
 *
 * Applies consistent padding, max-width, and overflow behaviour.
 * Renders as a <main> element with a configurable aria-label.
 */

import { Box, type BoxProps } from '@mantine/core';
import { type ReactNode } from 'react';

export interface MainContentProps extends Omit<BoxProps, 'component'> {
  children: ReactNode;
  /** Accessible label for the main landmark (page title). */
  ariaLabel?: string;
  /** Max content width. Defaults to '1280px'. */
  maxWidth?: string | number;
}

/**
 * @example
 * <MainContent ariaLabel="Dashboard">
 *   <DashboardContent />
 * </MainContent>
 */
export function MainContent({
  children,
  ariaLabel = 'Page content',
  maxWidth = '1280px',
  style,
  ...boxProps
}: MainContentProps) {
  return (
    <Box
      component="main"
      aria-label={ariaLabel}
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: 'var(--mantine-spacing-lg)',
        maxWidth,
        width: '100%',
        ...style,
      }}
      {...boxProps}
    >
      {children}
    </Box>
  );
}
