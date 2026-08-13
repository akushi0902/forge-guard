/**
 * Custom render utility for ForgeGuard component tests.
 *
 * Wraps the component under test in all application providers, mirroring the
 * provider stack in App.tsx. This ensures tests exercise components in a
 * realistic context without requiring a fully mounted App.
 *
 * Usage:
 *   import { render, screen } from '@/test-utils';
 *   render(<MyComponent />);
 *   expect(screen.getByText('Hello')).toBeInTheDocument();
 */

import '@mantine/core/styles.css';

import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  render,
  type RenderOptions,
  type RenderResult,
} from '@testing-library/react';
import { type JSX, type PropsWithChildren } from 'react';
import { MemoryRouter, type MemoryRouterProps } from 'react-router-dom';

import { theme } from '@/theme';

// Re-export everything from Testing Library so tests only need one import.
export * from '@testing-library/react';
export { default as userEvent } from '@testing-library/user-event';

// --------------------------------------------------------------------------
// Provider wrapper
// --------------------------------------------------------------------------

interface WrapperProps extends PropsWithChildren {
  routerProps?: MemoryRouterProps;
}

/**
 * Create a fresh QueryClient for each test to prevent cache leakage.
 * Retries are disabled so tests fail fast instead of waiting for retry delays.
 */
function makeTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function AllProviders({ children, routerProps }: WrapperProps): JSX.Element {
  const queryClient = makeTestQueryClient();

  return (
    <MantineProvider theme={theme}>
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <MemoryRouter {...routerProps}>{children}</MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

// --------------------------------------------------------------------------
// Custom render function
// --------------------------------------------------------------------------

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  routerProps?: MemoryRouterProps;
}

/**
 * Renders a component inside all ForgeGuard providers.
 *
 * @param ui           - The component to render.
 * @param options      - Testing Library render options plus optional routerProps.
 * @returns            - Standard Testing Library RenderResult.
 */
function customRender(
  ui: React.ReactElement,
  { routerProps, ...renderOptions }: CustomRenderOptions = {},
): RenderResult {
  return render(ui, {
    wrapper: ({ children }) => (
      <AllProviders routerProps={routerProps}>{children}</AllProviders>
    ),
    ...renderOptions,
  });
}

// Override the default render with the custom one.
export { customRender as render };
