import axios, {
  type AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { getAccessToken, useAuthStore } from '@/stores/auth';
import { type ApiError } from '@/types';

/**
 * Configured Axios instance for all ForgeGuard API requests.
 *
 * Base URL: /api/v1 (proxied to backend:8000 in development via Vite config)
 * Auth:     Bearer token injected from Zustand auth store on every request
 * Errors:   Standardised handling for 401, 403, 429, and 5xx responses
 */
export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// --------------------------------------------------------------------------
// Request interceptor — inject Bearer token when available
// --------------------------------------------------------------------------
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig): InternalAxiosRequestConfig => {
    const token = getAccessToken();
    if (token) {
      config.headers.set('Authorization', `Bearer ${token}`);
    }
    return config;
  },
  (error: unknown) => Promise.reject(error),
);

// --------------------------------------------------------------------------
// Response interceptor — normalise error responses
// --------------------------------------------------------------------------
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: unknown): Promise<never> => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(error);
    }

    const axiosError = error as AxiosError<ApiError>;
    const status = axiosError.response?.status;
    const requestId = axiosError.response?.headers['x-request-id'] as string | undefined;
    const detail =
      axiosError.response?.data?.detail ?? axiosError.message ?? 'An unexpected error occurred.';

    switch (status) {
      case 401:
        // Token expired or invalid — clear auth state and redirect to login.
        useAuthStore.getState().logout();
        // Defer navigation so the logout state propagates before redirect.
        queueMicrotask(() => {
          window.location.href = '/login';
        });
        break;

      case 403:
        showNotification({
          title: 'Permission Denied',
          message: detail,
          color: 'danger',
        });
        break;

      case 429: {
        const retryAfter = axiosError.response?.headers['retry-after'];
        const retryMsg = retryAfter
          ? ` Please retry after ${retryAfter} seconds.`
          : '';
        showNotification({
          title: 'Rate Limit Exceeded',
          message: `Too many requests.${retryMsg}`,
          color: 'warning',
        });
        break;
      }

      default:
        if (status !== undefined && status >= 500) {
          const requestIdSuffix = requestId ? ` (Request ID: ${requestId})` : '';
          showNotification({
            title: 'Server Error',
            message: `${detail}${requestIdSuffix}`,
            color: 'danger',
          });
        }
        break;
    }

    return Promise.reject(axiosError);
  },
);

/**
 * Thin wrapper around Mantine notifications.
 *
 * Imported lazily to avoid a hard circular dependency at module load time —
 * notifications may not be available until the provider mounts.
 */
function showNotification(opts: {
  title: string;
  message: string;
  color: string;
}): void {
  import('@mantine/notifications').then(({ notifications }) => {
    notifications.show({
      title: opts.title,
      message: opts.message,
      color: opts.color,
      autoClose: 6000,
    });
  }).catch(() => {
    // Swallow — notifications not available (e.g. during tests).
  });
}
