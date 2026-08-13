/**
 * TanStack Query hooks for the Operator Platform Health dashboard (WO-081).
 *
 * All hooks poll every 10 seconds with placeholderData to avoid UI flicker.
 * Health endpoints (/health, /ready) are public — no auth token injected.
 */

import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import {
  type PlatformHealthSummary,
  type SystemHealthStatus,
  type ReadinessCheck,
  type PlatformMetrics,
  type PlatformLogsResponse,
} from '@/types/api';

const REFETCH_INTERVAL_MS = 10_000;

export const platformHealthKeys = {
  summary: () => ['platform', 'health', 'summary'] as const,
  system:  () => ['platform', 'health', 'system']  as const,
  ready:   () => ['platform', 'health', 'ready']   as const,
  metrics: () => ['platform', 'metrics']           as const,
  logs:    () => ['platform', 'logs']              as const,
};

/** Aggregated platform health summary from the backend metrics store. */
export function usePlatformHealthSummary() {
  return useQuery({
    queryKey: platformHealthKeys.summary(),
    queryFn: () => apiClient<PlatformHealthSummary>('/api/v1/platform/health'),
    refetchInterval: REFETCH_INTERVAL_MS,
    placeholderData: (prev) => prev,
  });
}

/** Basic liveness check — endpoint is public, no auth token required. */
export function useSystemHealth() {
  return useQuery({
    queryKey: platformHealthKeys.system(),
    queryFn: () => apiClient<SystemHealthStatus>('/health'),
    refetchInterval: REFETCH_INTERVAL_MS,
    placeholderData: (prev) => prev,
  });
}

/** Readiness check including database connectivity — public endpoint. */
export function useReadinessStatus() {
  return useQuery({
    queryKey: platformHealthKeys.ready(),
    queryFn: () => apiClient<ReadinessCheck>('/ready'),
    refetchInterval: REFETCH_INTERVAL_MS,
    placeholderData: (prev) => prev,
  });
}

/** Response time time-series for the last 60 minutes (chart data). */
export function usePlatformMetrics() {
  return useQuery({
    queryKey: platformHealthKeys.metrics(),
    queryFn: () => apiClient<PlatformMetrics>('/api/v1/platform/metrics'),
    refetchInterval: REFETCH_INTERVAL_MS,
    placeholderData: (prev) => prev,
  });
}

/** Six most recent operational log entries. */
export function usePlatformLogs() {
  return useQuery({
    queryKey: platformHealthKeys.logs(),
    queryFn: () => apiClient<PlatformLogsResponse>('/api/v1/platform/logs'),
    refetchInterval: REFETCH_INTERVAL_MS,
    placeholderData: (prev) => prev,
  });
}
