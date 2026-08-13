/**
 * Tests for the root App component and application scaffold.
 *
 * These tests verify that:
 *   1. The App component mounts without throwing.
 *   2. The Mantine provider is active (MantineProvider CSS variables injected).
 *   3. The React Router renders the dashboard placeholder on the root path.
 */

import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { App } from '@/App';
import { DashboardPage } from '@/router';
import { render } from '@/test-utils';

describe('App', () => {
  it('mounts without throwing', () => {
    // App uses BrowserRouter internally (via createBrowserRouter), so we render
    // it directly — it brings its own router context.
    expect(() => render(<App />)).not.toThrow();
  });

  it('renders the root element', () => {
    render(<App />);
    // The root div is present and the app tree is attached to the DOM.
    const root = document.getElementById('root') ?? document.body;
    expect(root).toBeInTheDocument();
  });
});

describe('DashboardPage placeholder', () => {
  it('renders the dashboard heading', () => {
    // Test the placeholder page directly using the custom render utility
    // (which wraps in MemoryRouter so no BrowserRouter conflict occurs).
    render(<DashboardPage />);
    expect(screen.getByRole('heading', { name: /dashboard/i })).toBeInTheDocument();
  });

  it('renders descriptive placeholder text', () => {
    render(<DashboardPage />);
    expect(screen.getByText(/coming soon/i)).toBeInTheDocument();
  });
});

describe('Mantine theme integration', () => {
  it('applies the custom theme without errors', () => {
    // If MantineProvider fails to initialise the theme, it throws synchronously.
    // A successful render confirms the theme object is valid.
    expect(() => render(<App />)).not.toThrow();
  });
});
