import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { type Role, type User } from '@/types';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
}

interface AuthActions {
  login: (user: User, accessToken: string) => void;
  logout: () => void;
  setAccessToken: (token: string) => void;
}

type AuthStore = AuthState & AuthActions;

const initialState: AuthState = {
  user: null,
  accessToken: null,
  isAuthenticated: false,
};

/**
 * Zustand auth store.
 *
 * State is persisted to sessionStorage so it survives page refreshes within
 * the same browser tab but is cleared when the tab is closed. This matches
 * the 15-minute access token TTL — the user must re-authenticate after an
 * inactive session.
 *
 * The `accessToken` field is intentionally stored separately from the User
 * record so it can be rotated (via the refresh-token flow) without
 * re-rendering components that only depend on user identity.
 */
export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      ...initialState,

      login: (user: User, accessToken: string) => {
        set({ user, accessToken, isAuthenticated: true });
      },

      logout: () => {
        set(initialState);
      },

      setAccessToken: (token: string) => {
        set({ accessToken: token });
      },
    }),
    {
      name: 'forgeguard-auth',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);

/** Selector: return the current access token for use in API interceptors. */
export const getAccessToken = (): string | null =>
  useAuthStore.getState().accessToken;

/** Selector: return whether the user is currently authenticated. */
export const getIsAuthenticated = (): boolean =>
  useAuthStore.getState().isAuthenticated;

/** Selector: current role for RBAC-aware UI rendering. */
export const getUserRole = (): Role | null =>
  useAuthStore.getState().user?.role ?? null;
