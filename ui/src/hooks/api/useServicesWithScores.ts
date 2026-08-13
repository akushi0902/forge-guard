import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type ServicesWithMetricsResponse } from '@/types/api';

export const managerServiceKeys = {
  all: ['manager', 'services-with-metrics'] as const,
  filtered: (team?: string) =>
    ['manager', 'services-with-metrics', { team }] as const,
};

export function useServicesWithScores(team?: string) {
  return useQuery({
    queryKey: managerServiceKeys.filtered(team),
    queryFn: () => {
      const params = new URLSearchParams();
      if (team) params.set('team', team);
      const qs = params.toString();
      return apiClient<ServicesWithMetricsResponse>(
        `/api/v1/services/with-metrics${qs ? `?${qs}` : ''}`,
      );
    },
    refetchInterval: 60_000,
  });
}
