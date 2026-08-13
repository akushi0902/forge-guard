/**
 * MSW handlers for platform health endpoints (WO-081).
 *
 * Provides healthy, degraded, and down scenarios for testing.
 */

import { http, HttpResponse } from 'msw';

import {
  type PlatformHealthSummary,
  type SystemHealthStatus,
  type ReadinessCheck,
  type PlatformMetrics,
  type PlatformLogsResponse,
} from '@/types/api';

// ---------------------------------------------------------------------------
// Fixtures — healthy state
// ---------------------------------------------------------------------------

export const SYSTEM_HEALTH_FIXTURE: SystemHealthStatus = {
  status: 'healthy',
  timestamp: '2026-08-12T10:00:00Z',
  version: '1.0.0',
};

export const READINESS_FIXTURE: ReadinessCheck = {
  status: 'ok',
  database: { status: 'ok', latency_ms: 5 },
  migration_version: '20260812_000d',
};

export const PLATFORM_HEALTH_FIXTURE: PlatformHealthSummary = {
  status: 'healthy',
  timestamp: '2026-08-12T10:00:00Z',
  api_success_rate: 99.5,
  assessment_completion_rate: 100.0,
  audit_log_write_success_rate: 100.0,
  db_connection_pool_utilization: 0.15,
  llm_circuit_breaker_status: 'closed',
};

// ---------------------------------------------------------------------------
// Fixtures — degraded state (LLM half-open, elevated DB usage)
// ---------------------------------------------------------------------------

export const PLATFORM_HEALTH_DEGRADED_FIXTURE: PlatformHealthSummary = {
  ...PLATFORM_HEALTH_FIXTURE,
  status: 'degraded',
  api_success_rate: 92.0,
  db_connection_pool_utilization: 0.85,
  llm_circuit_breaker_status: 'half-open',
};

// ---------------------------------------------------------------------------
// Fixtures — down state (circuit open, DB degraded)
// ---------------------------------------------------------------------------

export const PLATFORM_HEALTH_DOWN_FIXTURE: PlatformHealthSummary = {
  ...PLATFORM_HEALTH_FIXTURE,
  status: 'unhealthy',
  api_success_rate: 60.0,
  assessment_completion_rate: 30.0,
  audit_log_write_success_rate: 85.0,
  db_connection_pool_utilization: 0.97,
  llm_circuit_breaker_status: 'open',
};

// ---------------------------------------------------------------------------
// Response time chart data — 60 data points covering the last hour
// ---------------------------------------------------------------------------

function buildResponseTimeData(baseMs: number): PlatformMetrics['response_times'] {
  const now = new Date('2026-08-12T10:00:00Z');
  return Array.from({ length: 60 }, (_, i) => {
    const minute = new Date(now.getTime() - (59 - i) * 60_000);
    const jitter = Math.abs(Math.sin(i * 0.7) * 30 + Math.cos(i * 0.3) * 20);
    return { minute: minute.toISOString(), p50_ms: Math.round(baseMs + jitter) };
  });
}

export const PLATFORM_METRICS_FIXTURE: PlatformMetrics = {
  response_times: buildResponseTimeData(95),
};

// ---------------------------------------------------------------------------
// Recent operational log fixtures
// ---------------------------------------------------------------------------

export const PLATFORM_LOGS_FIXTURE: PlatformLogsResponse = {
  entries: [
    {
      id: 'log-001',
      timestamp: '2026-08-12T09:58:00Z',
      level: 'info',
      service: 'backend',
      message: 'Health check passed — all systems operational',
    },
    {
      id: 'log-002',
      timestamp: '2026-08-12T09:55:00Z',
      level: 'info',
      service: 'backend',
      message: 'Assessment completed for service payment-service',
    },
    {
      id: 'log-003',
      timestamp: '2026-08-12T09:52:00Z',
      level: 'warn',
      service: 'llm',
      message: 'LLM response time elevated: 450ms (threshold 400ms)',
    },
    {
      id: 'log-004',
      timestamp: '2026-08-12T09:50:00Z',
      level: 'info',
      service: 'database',
      message: 'Connection pool utilization: 15%',
    },
    {
      id: 'log-005',
      timestamp: '2026-08-12T09:45:00Z',
      level: 'info',
      service: 'audit',
      message: 'Audit log partition maintenance completed successfully',
    },
    {
      id: 'log-006',
      timestamp: '2026-08-12T09:40:00Z',
      level: 'error',
      service: 'llm',
      message: 'Circuit breaker half-open — LLM provider timeout',
    },
  ],
  total: 6,
};

// ---------------------------------------------------------------------------
// MSW handlers
// ---------------------------------------------------------------------------

export const healthHandlers = [
  http.get('/health',                    () => HttpResponse.json(SYSTEM_HEALTH_FIXTURE)),
  http.get('/ready',                     () => HttpResponse.json(READINESS_FIXTURE)),
  http.get('/api/v1/platform/health',    () => HttpResponse.json(PLATFORM_HEALTH_FIXTURE)),
  http.get('/api/v1/platform/metrics',   () => HttpResponse.json(PLATFORM_METRICS_FIXTURE)),
  http.get('/api/v1/platform/logs',      () => HttpResponse.json(PLATFORM_LOGS_FIXTURE)),
];
