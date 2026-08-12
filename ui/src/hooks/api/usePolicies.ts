import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import {
  type CreatePolicyRuleBody,
  type DimensionWeight,
  type PolicyRule,
  type PolicyRulesResponse,
  type ScoreThresholds,
  type UpdatePolicyRuleBody,
} from '@/types/api';

export interface PolicyFilters {
  search?: string;
  dimension?: string;
  severity?: string;
}

export const policyKeys = {
  all: ['policies'] as const,
  list: (filters?: PolicyFilters) => ['policies', 'list', filters ?? {}] as const,
  detail: (id: string) => ['policies', 'detail', id] as const,
  dimensions: () => ['policies', 'dimensions'] as const,
  thresholds: () => ['policies', 'thresholds'] as const,
};

export function usePolicies(filters?: PolicyFilters) {
  return useQuery({
    queryKey: policyKeys.list(filters),
    queryFn: () => {
      const params = new URLSearchParams();
      if (filters?.search) params.set('search', filters.search);
      if (filters?.dimension) params.set('dimension', filters.dimension);
      if (filters?.severity) params.set('severity', filters.severity);
      const qs = params.toString();
      return apiClient<PolicyRulesResponse>(`/api/v1/policies${qs ? `?${qs}` : ''}`);
    },
  });
}

export function useCreatePolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreatePolicyRuleBody) =>
      apiClient<PolicyRule>('/api/v1/policies', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onMutate: async (newRule) => {
      await queryClient.cancelQueries({ queryKey: policyKeys.all });
      const previous = queryClient.getQueryData<PolicyRulesResponse>(policyKeys.list());
      if (previous) {
        const optimistic: PolicyRule = {
          id: `optimistic-${Date.now()}`,
          name: newRule.name,
          dimension: newRule.dimension,
          severity: newRule.severity,
          threshold: newRule.threshold,
          description: newRule.description ?? null,
          enabled: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        queryClient.setQueryData<PolicyRulesResponse>(policyKeys.list(), {
          ...previous,
          items: [optimistic, ...previous.items],
          total: previous.total + 1,
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(policyKeys.list(), context.previous);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: policyKeys.all });
    },
  });
}

export function useUpdatePolicy(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdatePolicyRuleBody) =>
      apiClient<PolicyRule>(`/api/v1/policies/${id}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: policyKeys.all });
    },
  });
}

export function useDeletePolicy(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient<void>(`/api/v1/policies/${id}`, { method: 'DELETE' }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: policyKeys.all });
    },
  });
}

export function useDimensionWeights() {
  return useQuery({
    queryKey: policyKeys.dimensions(),
    queryFn: () => apiClient<DimensionWeight[]>('/api/v1/policies/dimensions'),
  });
}

export function useUpdateDimensionWeights() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (weights: DimensionWeight[]) =>
      apiClient<DimensionWeight[]>('/api/v1/policies/dimensions', {
        method: 'PUT',
        body: JSON.stringify(weights),
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: policyKeys.dimensions() });
    },
  });
}

export function useScoreThresholds() {
  return useQuery({
    queryKey: policyKeys.thresholds(),
    queryFn: () => apiClient<ScoreThresholds>('/api/v1/policies/thresholds'),
  });
}

export function useUpdateScoreThresholds() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (thresholds: ScoreThresholds) =>
      apiClient<ScoreThresholds>('/api/v1/policies/thresholds', {
        method: 'PUT',
        body: JSON.stringify(thresholds),
      }),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: policyKeys.thresholds() });
    },
  });
}
