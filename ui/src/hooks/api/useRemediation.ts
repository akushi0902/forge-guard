import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type Exception, type ReleaseAssessment } from '@/types/api';
import { scoreKeys } from './useScores';

export interface RequestExceptionBody {
  justification: string;
  expires_at?: string;
}

export function useRequestException(findingId: string) {
  return useMutation({
    mutationFn: (body: RequestExceptionBody) =>
      apiClient<Exception>(`/api/v1/findings/${findingId}/exception`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  });
}

export function useRequestReEvaluation(serviceId: string) {
  const queryClientInstance = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient<ReleaseAssessment>(`/api/v1/services/${serviceId}/re-evaluate`, {
        method: 'POST',
        body: JSON.stringify({}),
      }),
    onSuccess: async () => {
      await queryClientInstance.invalidateQueries({ queryKey: scoreKeys.service(serviceId) });
    },
  });
}
