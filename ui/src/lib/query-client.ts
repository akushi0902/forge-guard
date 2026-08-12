/**
 * Centralised TanStack QueryClient with application-wide defaults.
 * Import this singleton into App.tsx instead of defining it inline.
 */

import { notifications } from '@mantine/notifications';
import { QueryClient } from '@tanstack/react-query';

import { ApiError, NetworkError } from '@/types/errors';

function getErrorMessage(error: unknown): { title: string; message: string; color: string } | null {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 400:
        return { title: 'Bad Request', message: error.detail, color: 'red' };
      case 401:
        return { title: 'Unauthorised', message: 'Please log in again.', color: 'red' };
      case 403:
        // 403 responses are handled by the permission interceptor in api-client.ts
        // which shows a rich notification with the specific permission and role.
        // Return null to skip the generic fallback notification here.
        return null;
      case 404:
        return {
          title: 'Not Found',
          message: 'The requested resource was not found.',
          color: 'yellow',
        };
      case 429:
        return {
          title: 'Too Many Requests',
          message: 'Too many requests — please wait and try again.',
          color: 'yellow',
        };
      default:
        if (error.status >= 500) {
          return {
            title: 'Server Error',
            message: 'An unexpected error occurred — please try again later.',
            color: 'red',
          };
        }
        return { title: 'Error', message: error.detail, color: 'red' };
    }
  }

  if (error instanceof NetworkError) {
    return {
      title: 'Connection Error',
      message: 'Unable to connect to the server — check your network connection.',
      color: 'red',
    };
  }

  return {
    title: 'Error',
    message: 'An unexpected error occurred.',
    color: 'red',
  };
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 10_000),
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: 0,
      onError: (error) => {
        const result = getErrorMessage(error);
        if (result === null) return; // handled by permission interceptor
        const { title, message, color } = result;
        notifications.show({ title, message, color, autoClose: 5000 });
      },
    },
  },
});

