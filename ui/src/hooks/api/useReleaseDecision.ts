/**
 * TanStack Query mutation hooks for Security Review release decisions (WO-077).
 *
 * Focused on the Security Reviewer's block and override actions, with
 * automatic cache invalidation of security findings and escalations queries.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { securityKeys } from './useSecurityFindings';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Payload for POST /api/v1/releases/{id}/decide */
export interface ReleaseDecisionBody {
  decision: 'BLOCK' | 'APPROVE' | 'OVERRIDE';
  rationale: string;
  comment?: string;
}

/** Response from POST /api/v1/releases/{id}/decide */
export interface ReleaseDecisionResult {
  id: string;
  decision: string;
  decided_by: string;
  decided_at: string;
  was_escalated: boolean;
}

/** Payload for POST /api/v1/exceptions/{id}/decide */
export interface ExceptionDecisionBody {
  decision: 'approve' | 'reject';
  rationale: string;
}

/** Response from POST /api/v1/exceptions/{id}/decide */
export interface ExceptionDecisionResult {
  id: string;
  decision: string;
  decided_at: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

/**
 * Mutation hook for blocking a release assessment from the Security Review page.
 *
 * On success, invalidates security findings and escalations queries so the
 * page refreshes to reflect the resolved state.
 */
export function useBlockRelease() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      releaseId,
      body,
    }: {
      releaseId: string;
      body: ReleaseDecisionBody;
    }) =>
      apiClient<ReleaseDecisionResult>(`/api/v1/releases/${releaseId}/decide`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: securityKeys.escalations() });
      void queryClient.invalidateQueries({ queryKey: ['security-findings'] });
    },
  });
}

/**
 * Mutation hook for deciding on an exception request.
 *
 * On success, invalidates the pending exceptions query.
 */
export function useExceptionDecision() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      exceptionId,
      body,
    }: {
      exceptionId: string;
      body: ExceptionDecisionBody;
    }) =>
      apiClient<ExceptionDecisionResult>(`/api/v1/exceptions/${exceptionId}/decide`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: securityKeys.exceptions() });
    },
  });
}
