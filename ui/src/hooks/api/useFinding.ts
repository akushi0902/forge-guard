/**
 * TanStack Query hook for fetching a single finding by ID (WO-082).
 *
 * GET /api/v1/findings/{id}
 */

import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type FindingDetail, type FindingRecommendation } from '@/types/api';

// ---------------------------------------------------------------------------
// Query key factory
// ---------------------------------------------------------------------------

export const findingDetailKeys = {
  detail: (findingId: string) => ['findings', findingId] as const,
  recommendation: (findingId: string) =>
    ['findings', findingId, 'recommendation'] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

/**
 * Fetch a single finding by ID.
 * Returns the full FindingDetail including AI explanation and evidence.
 */
export function useFinding(findingId: string) {
  return useQuery({
    queryKey: findingDetailKeys.detail(findingId),
    queryFn: () =>
      apiClient<FindingDetail>(`/api/v1/findings/${findingId}`),
    enabled: Boolean(findingId),
  });
}

/**
 * Fetch the AI remediation recommendation for a finding.
 * Returns FindingRecommendation with business impact, steps, and confidence.
 */
export function useFindingRemediation(findingId: string) {
  return useQuery({
    queryKey: findingDetailKeys.recommendation(findingId),
    queryFn: () =>
      apiClient<FindingRecommendation>(
        `/api/v1/findings/${findingId}/recommendation`,
      ),
    enabled: Boolean(findingId),
    retry: (failureCount, error) => {
      // Do not retry on 404 — recommendation may still be generating
      if (error && typeof error === 'object' && 'status' in error) {
        if ((error as { status: number }).status === 404) return false;
      }
      return failureCount < 3;
    },
  });
}
