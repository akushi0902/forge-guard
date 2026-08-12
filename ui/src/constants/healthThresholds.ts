/**
 * Health threshold constants for the Operator Platform Health dashboard (WO-081).
 *
 * Each threshold defines green/yellow/red boundaries and the comparison direction.
 * Call evaluateThreshold(value, config) to get a ThresholdStatus.
 */

export type ThresholdStatus = 'green' | 'yellow' | 'red';

export interface ThresholdConfig {
  /** When true, a higher value is healthier (e.g. success rates).
   *  When false, a lower value is healthier (e.g. latency, utilization). */
  higherIsBetter: boolean;
  /** Value at or above which status is 'green' (higherIsBetter),
   *  or at or below which status is 'green' (!higherIsBetter). */
  greenBoundary: number;
  /** Value at or above which status is at least 'yellow' (higherIsBetter),
   *  or at or below which status is at least 'yellow' (!higherIsBetter). */
  yellowBoundary: number;
}

/**
 * Evaluate a metric value against a threshold config.
 * Returns 'green', 'yellow', or 'red'.
 */
export function evaluateThreshold(value: number, config: ThresholdConfig): ThresholdStatus {
  if (config.higherIsBetter) {
    if (value >= config.greenBoundary) return 'green';
    if (value >= config.yellowBoundary) return 'yellow';
    return 'red';
  }
  if (value <= config.greenBoundary) return 'green';
  if (value <= config.yellowBoundary) return 'yellow';
  return 'red';
}

/** Threshold definitions for all StatusGrid metrics. */
export const HEALTH_THRESHOLDS: Record<string, ThresholdConfig> = {
  /** API success rate (%): green ≥ 99%, yellow ≥ 95%, red < 95%. */
  apiSuccessRate: { higherIsBetter: true, greenBoundary: 99, yellowBoundary: 95 },
  /** Assessment completion rate (%): green ≥ 95%, yellow ≥ 80%, red < 80%. */
  assessmentCompletionRate: { higherIsBetter: true, greenBoundary: 95, yellowBoundary: 80 },
  /** DB connection pool utilization (%): green ≤ 70%, yellow ≤ 90%, red > 90%. */
  dbPoolUtilizationPct: { higherIsBetter: false, greenBoundary: 70, yellowBoundary: 90 },
  /** Audit log write success rate (%): green ≥ 99%, yellow ≥ 95%, red < 95%. */
  auditLogSuccessRate: { higherIsBetter: true, greenBoundary: 99, yellowBoundary: 95 },
  /** API latency (ms): green ≤ 200ms, yellow ≤ 500ms, red > 500ms. */
  apiLatencyMs: { higherIsBetter: false, greenBoundary: 200, yellowBoundary: 500 },
  /** Error rate (%): green ≤ 1%, yellow ≤ 5%, red > 5%. */
  errorRatePct: { higherIsBetter: false, greenBoundary: 1, yellowBoundary: 5 },
};

/** Map ThresholdStatus to a Mantine color name. */
export const STATUS_COLOR: Record<ThresholdStatus, string> = {
  green: 'green',
  yellow: 'yellow',
  red: 'red',
};

/** Derive the worst (most severe) status from an array of statuses. */
export function worstStatus(statuses: ThresholdStatus[]): ThresholdStatus {
  if (statuses.includes('red')) return 'red';
  if (statuses.includes('yellow')) return 'yellow';
  return 'green';
}
