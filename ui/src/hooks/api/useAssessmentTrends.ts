import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type AssessmentTrendsResponse } from '@/types/api';

export const trendKeys = {
  all: ['manager', 'assessment-trends'] as const,
  range: (months = 6) =>
    ['manager', 'assessment-trends', { months }] as const,
};

export function useAssessmentTrends(months = 6) {
  return useQuery({
    queryKey: trendKeys.range(months),
    queryFn: () => {
      const params = new URLSearchParams();
      params.set('months', String(months));
      return apiClient<AssessmentTrendsResponse>(
        `/api/v1/assessments/trends?${params.toString()}`,
      );
    },
    refetchInterval: 60_000,
  });
}
