import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type PaginatedResponse, type Service } from '@/types/api';

export const serviceKeys = {
  all: ['services'] as const,
  list: (cursor?: string, limit?: number) =>
    ['services', { cursor, limit }] as const,
  detail: (id: string) => ['services', id] as const,
};

export function useServices(cursor?: string, limit = 20) {
  return useQuery({
    queryKey: serviceKeys.list(cursor, limit),
    queryFn: () => {
      const params = new URLSearchParams();
      if (cursor) params.set('cursor', cursor);
      params.set('limit', String(limit));
      return apiClient<PaginatedResponse<Service>>(
        `/api/v1/services?${params.toString()}`,
      );
    },
  });
}

export function useService(id: string) {
  return useQuery({
    queryKey: serviceKeys.detail(id),
    queryFn: () => apiClient<Service>(`/api/v1/services/${id}`),
    enabled: Boolean(id),
  });
}
