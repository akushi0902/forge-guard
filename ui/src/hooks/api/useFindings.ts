import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type Finding, type PaginatedResponse, type RemediationRecommendation } from '@/types/api';

export interface FindingFilters {
  severity?: string;
  dimension?: string;
  cursor?: string | null;
  limit?: number;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
}

export const findingKeys = {
  service: (serviceId: string, filters?: FindingFilters) =>
    ['services', serviceId, 'findings', filters ?? {}] as const,
  recommendation: (findingId: string) =>
    ['findings', findingId, 'recommendation'] as const,
};

export function useServiceFindings(serviceId: string, filters?: FindingFilters) {
  return useQuery({
    queryKey: findingKeys.service(serviceId, filters),
    queryFn: () => {
      const params = new URLSearchParams();
      if (filters?.severity) params.set('severity', filters.severity);
      if (filters?.dimension) params.set('dimension', filters.dimension);
      if (filters?.cursor) params.set('cursor', filters.cursor);
      if (filters?.limit) params.set('limit', String(filters.limit));
      if (filters?.sort_by) params.set('sort_by', filters.sort_by);
      if (filters?.sort_dir) params.set('sort_dir', filters.sort_dir);
      const qs = params.toString();
      return apiClient<PaginatedResponse<Finding>>(
        `/api/v1/services/${serviceId}/findings${qs ? `?${qs}` : ''}`,
      );
    },
    enabled: Boolean(serviceId),
  });
}

export function useFindingRecommendation(findingId: string) {
  return useQuery({
    queryKey: findingKeys.recommendation(findingId),
    queryFn: () =>
      apiClient<RemediationRecommendation>(`/api/v1/findings/${findingId}/recommendation`),
    enabled: Boolean(findingId),
  });
}
