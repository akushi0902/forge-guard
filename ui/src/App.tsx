import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClientProvider } from '@tanstack/react-query';
import { type JSX } from 'react';
import { RouterProvider } from 'react-router-dom';

import { queryClient } from '@/lib/query-client';
import { router } from '@/router';
import { theme } from '@/theme';

/**
 * Root application component.
 *
 * Provider order (outer → inner):
 *   MantineProvider       — design system, theming, CSS variables
 *   Notifications         — toast notification manager (must be inside Mantine)
 *   QueryClientProvider   — TanStack Query server-state cache
 *   RouterProvider        — React Router 6 navigation
 */
export function App(): JSX.Element {
  return (
    <MantineProvider theme={theme} defaultColorScheme="light">
      <Notifications position="top-right" limit={5} />
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </MantineProvider>
  );
}
