import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';

import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type JSX } from 'react';
import { RouterProvider } from 'react-router-dom';

import { router } from '@/router';
import { theme } from '@/theme';

/**
 * QueryClient configuration.
 *
 * - staleTime: 60s — data is considered fresh for 1 minute, avoiding
 *   redundant background refetches in rapid navigation scenarios.
 * - retry: 1 — retry failed queries once before surfacing an error; avoids
 *   hammering the backend on transient 5xx failures.
 * - refetchOnWindowFocus: false — prevents unexpected refetches when users
 *   switch browser tabs (the explicit "Refresh" action is preferred).
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

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
