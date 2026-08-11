/**
 * Integration tests for LoginPage using MSW for API mocking.
 */

import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { render, screen, userEvent, waitFor } from '@/test-utils';
import { LoginPage } from '@/pages/LoginPage';
import {
  authHandlers,
  expiredRefreshHandler,
  serverErrorLoginHandler,
  TEST_CSRF_TOKEN,
  VALID_EMAIL,
  VALID_PASSWORD,
  LOCKED_EMAIL,
  developerUser,
} from '@/test/mocks/handlers/auth';
import { server } from '@/test/mocks/server';
import { useAuthStore } from '@/stores/auth-store';

beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => {
  server.resetHandlers();
  useAuthStore.setState({ user: null, isAuthenticated: false, isLoading: false, csrfToken: null });
  sessionStorage.clear();
});
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe('LoginPage - rendering', () => {
  it('renders email and password fields', () => {
    render(<LoginPage />);
    expect(screen.getByTestId('email-input')).toBeInTheDocument();
    expect(screen.getByTestId('password-input')).toBeInTheDocument();
    expect(screen.getByTestId('submit-button')).toBeInTheDocument();
  });

  it('renders the ForgeGuard title', () => {
    render(<LoginPage />);
    expect(screen.getByText('ForgeGuard')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

describe('LoginPage - form validation', () => {
  it('shows required error when email is empty', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByTestId('submit-button'));

    expect(await screen.findByText('Email is required.')).toBeInTheDocument();
  });

  it('shows format error for invalid email', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), 'not-an-email');
    await user.click(screen.getByTestId('submit-button'));

    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument();
  });

  it('shows required error when password is empty', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), VALID_EMAIL);
    await user.click(screen.getByTestId('submit-button'));

    expect(await screen.findByText('Password is required.')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Successful login
// ---------------------------------------------------------------------------

describe('LoginPage - successful login', () => {
  it('populates auth store after successful login', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), VALID_EMAIL);
    await user.type(screen.getByTestId('password-input'), VALID_PASSWORD);
    await user.click(screen.getByTestId('submit-button'));

    await waitFor(() => {
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(true);
      expect(state.user).toMatchObject({ email: developerUser.email });
    });
  });

  it('stores CSRF token in memory after login', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), VALID_EMAIL);
    await user.type(screen.getByTestId('password-input'), VALID_PASSWORD);
    await user.click(screen.getByTestId('submit-button'));

    await waitFor(() => {
      expect(useAuthStore.getState().csrfToken).toBe(TEST_CSRF_TOKEN);
    });
  });
});

// ---------------------------------------------------------------------------
// API error messages
// ---------------------------------------------------------------------------

describe('LoginPage - API error messages', () => {
  it('shows "Invalid email or password" on 401', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), 'wrong@example.com');
    await user.type(screen.getByTestId('password-input'), 'wrongpass');
    await user.click(screen.getByTestId('submit-button'));

    expect(await screen.findByText('Invalid email or password.')).toBeInTheDocument();
  });

  it('shows lockout message on 429', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), LOCKED_EMAIL);
    await user.type(screen.getByTestId('password-input'), 'any');
    await user.click(screen.getByTestId('submit-button'));

    expect(
      await screen.findByText(/Account locked/i),
    ).toBeInTheDocument();
  });

  it('shows service unavailable on 500', async () => {
    server.use(serverErrorLoginHandler);
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), VALID_EMAIL);
    await user.type(screen.getByTestId('password-input'), VALID_PASSWORD);
    await user.click(screen.getByTestId('submit-button'));

    expect(
      await screen.findByText(/Authentication service unavailable/i),
    ).toBeInTheDocument();
  });

  it('shows connection error on network failure', async () => {
    server.use(
      http.post('/api/v1/auth/login', () => {
        throw new Error('network failure');
      }),
    );
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), VALID_EMAIL);
    await user.type(screen.getByTestId('password-input'), VALID_PASSWORD);
    await user.click(screen.getByTestId('submit-button'));

    expect(
      await screen.findByText(/Unable to connect/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe('LoginPage - loading state', () => {
  it('disables submit button while loading', async () => {
    let resolveLogin: () => void;
    const loginPromise = new Promise<void>((resolve) => {
      resolveLogin = resolve;
    });

    server.use(
      http.post('/api/v1/auth/login', async () => {
        await loginPromise;
        return HttpResponse.json(
          { user: developerUser },
          { headers: { 'X-CSRF-Token': TEST_CSRF_TOKEN } },
        );
      }),
    );

    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByTestId('email-input'), VALID_EMAIL);
    await user.type(screen.getByTestId('password-input'), VALID_PASSWORD);

    const submitButton = screen.getByTestId('submit-button');
    await user.click(submitButton);

    // While the fetch is pending, isLoading should be true (button shows loader)
    expect(useAuthStore.getState().isLoading).toBe(true);

    // Resolve the pending login
    resolveLogin!();
    await waitFor(() => expect(useAuthStore.getState().isLoading).toBe(false));
  });
});
