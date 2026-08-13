/**
 * ForgeGuard auth store.
 *
 * Design:
 *  - Persists only non-sensitive data (user profile, isAuthenticated) to
 *    sessionStorage.  Tokens are httpOnly cookies managed by the browser and
 *    are NEVER stored in JS-accessible storage.
 *  - csrfToken is kept in-memory only (not persisted) — it is refreshed on
 *    every login/refresh call and intentionally lost on page reload so the
 *    browser is forced to re-authenticate.
 *  - isLoading guards the submit button and prevents double-submissions.
 */

import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { apiClient } from '@/lib/api-client';
import { type Role } from '@/types';

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  permissions: string[];
}

interface LoginResponse {
  user: User;
}

// ---------------------------------------------------------------------------
// Store shape
// ---------------------------------------------------------------------------

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** CSRF token received from X-CSRF-Token response header — in-memory only. */
  csrfToken: string | null;
}

interface AuthActions {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<void>;
  setUser: (user: User | null) => void;
  setCsrfToken: (token: string | null) => void;
}

type AuthStore = AuthState & AuthActions;

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

const initialState: AuthState = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  csrfToken: null,
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      ...initialState,

      login: async (email: string, password: string): Promise<void> => {
        set({ isLoading: true });
        try {
          // Use raw fetch so we can read response headers for the CSRF token.
          const response = await fetch('/api/v1/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ email, password }),
          });

          if (!response.ok) {
            const body = await response.json().catch(() => ({})) as { detail?: string };
            throw Object.assign(new Error(body.detail ?? response.statusText), {
              status: response.status,
            });
          }

          const data = (await response.json()) as LoginResponse;
          const csrfToken = response.headers.get('X-CSRF-Token');

          set({
            user: data.user,
            isAuthenticated: true,
            csrfToken,
            isLoading: false,
          });
        } catch (err) {
          set({ isLoading: false });
          throw err;
        }
      },

      logout: async (): Promise<void> => {
        set({ isLoading: true });
        try {
          const { csrfToken } = get();
          await fetch('/api/v1/auth/logout', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
            },
            credentials: 'include',
          }).catch(() => {
            // Best-effort — clear local state even if the server call fails.
          });
        } finally {
          set({ ...initialState });
          // Clear sessionStorage persistence
          sessionStorage.removeItem('forgeguard-auth');
        }
      },

      refreshToken: async (): Promise<void> => {
        const response = await fetch('/api/v1/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          credentials: 'include',
        });

        if (!response.ok) {
          // Refresh failed — clear state to force re-login
          set({ ...initialState });
          sessionStorage.removeItem('forgeguard-auth');
          throw Object.assign(new Error('Session expired'), { status: response.status });
        }

        const data = (await response.json()) as LoginResponse;
        const csrfToken = response.headers.get('X-CSRF-Token');

        set({
          user: data.user,
          isAuthenticated: true,
          csrfToken,
        });
      },

      setUser: (user: User | null): void => {
        set({ user, isAuthenticated: user !== null });
      },

      setCsrfToken: (token: string | null): void => {
        set({ csrfToken: token });
      },
    }),
    {
      name: 'forgeguard-auth',
      storage: createJSONStorage(() => sessionStorage),
      // Only persist non-sensitive user profile data — never tokens.
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);

// ---------------------------------------------------------------------------
// Selectors (for use outside of React components)
// ---------------------------------------------------------------------------

/** Returns the current CSRF token for injection into mutation requests. */
export const getCsrfToken = (): string | null =>
  useAuthStore.getState().csrfToken;

/** Returns whether the current session is authenticated. */
export const getIsAuthenticated = (): boolean =>
  useAuthStore.getState().isAuthenticated;

/** Returns the current user's role for RBAC-aware rendering. */
export const getUserRole = (): Role | null =>
  useAuthStore.getState().user?.role ?? null;
