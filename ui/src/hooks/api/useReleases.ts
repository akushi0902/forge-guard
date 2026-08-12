import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type DecisionType, type ReleaseAssessment, type ReleaseDecision } from '@/types/api';
import { scoreKeys } from './useScores';

export const releaseKeys = {
  detail: (id: string) => ['releases', id] as const,
};

export interface UseReleaseOptions {
  refetchInterval?: number | false | ((query: any) => number | false | undefined);
}

export function useRelease(id: string, options?: UseReleaseOptions) {
  return useQuery({
    queryKey: releaseKeys.detail(id),
    queryFn: () => apiClient<ReleaseAssessment>(`/api/v1/releases/${id}`),
    enabled: Boolean(id),
    ...(options ?? {}),
  });
}

export interface RequestReleaseAssessmentBody {
  service_id: string;
  commit_sha: string;
  pr_reference?: string;
}

export function useRequestReleaseAssessment() {
  return useMutation({
    mutationFn: (body: RequestReleaseAssessmentBody) =>
      apiClient<ReleaseAssessment>('/api/v1/releases/assess', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  });
}

export interface SubmitDecisionBody {
  decision: DecisionType;
  rationale: string;
  comment?: string;
}

export function useSubmitDecision(releaseId: string) {
  const queryClientInstance = useQueryClient();
  return useMutation({
    mutationFn: (body: SubmitDecisionBody) =>
      apiClient<ReleaseDecision>(`/api/v1/releases/${releaseId}/decide`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: async (data) => {
      await queryClientInstance.invalidateQueries({ queryKey: releaseKeys.detail(releaseId) });
      await queryClientInstance.invalidateQueries({
        queryKey: scoreKeys.service(data.release_assessment_id),
      });
    },
  });
}

export interface RequestAssessmentBody {
  service_id: string;
  commit_sha: string;
  pr_reference?: string;
}

export function useRequestAssessment() {
  return useMutation({
    mutationFn: (body: RequestAssessmentBody) =>
      apiClient<ReleaseAssessment>(`/api/v1/services/${body.service_id}/assess`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  });
}
