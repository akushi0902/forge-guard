/**
* TanStack Query hooks for the Security Review page (WO-077).
 *
 * Endpoints:
 *   GET /api/v1/findings?dimension=security&severity=critical,high
 *   GET /api/v1/releases?status=escalated
 *   GET /api/v1/exceptions?status=pending
 */

import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type PaginatedResponse } from '@/types/api';

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

/** Security finding with denormalised service_name for display. */
export interface SecurityFinding {
  id: string;
  service_id: string;
  service_name: string;
  dimension: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | string;
  title: string;
  description: string;
  status: string;
  created_at: string;
}

/** Escalated release assessment with the primary security finding embedded. */
export interface EscalatedRelease {
  id: string;
  service_id: string;
  service_name: string;
  commit_sha: string;
  status: string;
  risk_score: number | null;
  created_at: string;
  /** Severity of the triggering security finding. */
  severity: 'critical' | 'high' | string;
  /** Title of the triggering security finding. */
  finding_title: string;
  /** Description of the triggering security finding. */
  finding_description: string;
}

/** Exception request pending approval. */
export interface PendingException {
  id: string;
  finding_id: string;
  finding_title: string;
  service_name: string;
  severity: string;
  justification: string;
  status: string;
  created_at: string;
  expires_at: string | null;
}

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const securityKeys = {
  findings: (filters?: SecurityFindingsFilters) =>
    ['security-findings', filters ?? {}] as const,
  escalations: () => ['security-escalations'] as const,
  exceptions: () => ['security-exceptions'] as const,
};

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

export interface SecurityFindingsFilters {
  severity?: string;
  status?: string | undefined;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  limit?: number;
  cursor?: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

/**
 * Fetch security findings (dimension=security) from the findings API.
 * Defaults to returning critical and high severity findings.
 */
export function useSecurityFindings(filters?: SecurityFindingsFilters) {
  return useQuery({
    queryKey: securityKeys.findings(filters),
    queryFn: () => {
      const params = new URLSearchParams({ dimension: 'security' });
      params.set('severity', filters?.severity ?? 'critical,high');
      if (filters?.status) params.set('status', filters.status);
      if (filters?.sort_by) params.set('sort_by', filters.sort_by);
      if (filters?.sort_dir) params.set('sort_dir', filters.sort_dir);
      if (filters?.limit) params.set('limit', String(filters.limit));
      if (filters?.cursor) params.set('cursor', filters.cursor);
      return apiClient<PaginatedResponse<SecurityFinding>>(
        `/api/v1/findings?${params.toString()}`,
      );
    },
    staleTime: 30_000,
  });
}

/** Fetch release assessments that have been escalated to Security Reviewer. */
export function usePendingEscalations() {
  return useQuery({
    queryKey: securityKeys.escalations(),
    queryFn: () =>
      apiClient<PaginatedResponse<EscalatedRelease>>('/api/v1/releases?status=escalated'),
    staleTime: 30_000,
  });
}

/** Fetch exception requests pending Security Reviewer approval. */
export function usePendingExceptions() {
  return useQuery({
    queryKey: securityKeys.exceptions(),
    queryFn: () =>
      apiClient<PaginatedResponse<PendingException>>('/api/v1/exceptions?status=pending'),
    staleTime: 30_000,
  });
}
