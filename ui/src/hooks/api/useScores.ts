import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type ServiceScore } from '@/types/api';

export const scoreKeys = {
  service: (serviceId: string) => ['services', serviceId, 'scores'] as const,
};

export function useServiceScores(serviceId: string) {
  return useQuery({
    queryKey: scoreKeys.service(serviceId),
    queryFn: () => apiClient<ServiceScore>(`/api/v1/services/${serviceId}/scores`),
    enabled: Boolean(serviceId),
  });
}
