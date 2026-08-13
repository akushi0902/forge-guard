/**
 * TanStack Query mutation hook for triggering finding re-evaluation (WO-082).
 *
 * POST /api/v1/findings/{id}/re-evaluate
 *
 * On success, invalidates the finding detail query so the status badge updates.
 * Re-evaluation may take up to 30 seconds; the hook respects the 30s timeout
 * configured in apiClient.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type ReEvaluationResult } from '@/types/api';
import { findingDetailKeys } from './useFinding';

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Mutation hook for re-evaluating an open finding.
 *
 * @example
 * const { mutate, isPending } = useReEvaluate(findingId);
 * mutate(undefined, {
 *   onSuccess: (result) => setLastResult(result),
 *   onError: (err) => showToast({ type: 'error', message: err.message }),
 * });
 */
export function useReEvaluate(findingId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiClient<ReEvaluationResult>(
        `/api/v1/findings/${findingId}/re-evaluate`,
        {
          method: 'POST',
          body: JSON.stringify({}),
          // Re-evaluation can take up to 30 seconds per work order constraint
          timeout: 35_000,
        },
      ),
    onSuccess: async () => {
      // Invalidate finding detail so status badge reflects the new state
      await queryClient.invalidateQueries({
        queryKey: findingDetailKeys.detail(findingId),
      });
      // Also invalidate recommendation in case updated_guidance was returned
      await queryClient.invalidateQueries({
        queryKey: findingDetailKeys.recommendation(findingId),
      });
    },
  });
}
