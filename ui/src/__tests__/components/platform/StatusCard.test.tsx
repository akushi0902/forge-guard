/**
 * Unit tests for StatusCard and healthThreshold utilities (WO-081).
 *
 * Covers threshold evaluation boundary values for all defined metrics,
 * StatusCard rendering with each status, and the worstStatus aggregator.
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { render } from '@/test-utils';
import { StatusCard } from '@/components/platform/StatusCard';
import {
  evaluateThreshold,
  worstStatus,
  HEALTH_THRESHOLDS,
} from '@/constants/healthThresholds';

// ---------------------------------------------------------------------------
// evaluateThreshold — pure function tests (no DOM required)
// ---------------------------------------------------------------------------

describe('evaluateThreshold', () => {
  describe('apiSuccessRate — higherIsBetter, green ≥ 99, yellow ≥ 95', () => {
    const cfg = HEALTH_THRESHOLDS.apiSuccessRate;

    it('returns green when value equals green boundary (99)', () => {
      expect(evaluateThreshold(99, cfg)).toBe('green');
    });

    it('returns green when value exceeds green boundary (100)', () => {
      expect(evaluateThreshold(100, cfg)).toBe('green');
    });

    it('returns yellow between boundaries (97)', () => {
      expect(evaluateThreshold(97, cfg)).toBe('yellow');
    });

    it('returns yellow when value equals yellow boundary (95)', () => {
      expect(evaluateThreshold(95, cfg)).toBe('yellow');
    });

    it('returns red when value is one below yellow boundary (94.9)', () => {
      expect(evaluateThreshold(94.9, cfg)).toBe('red');
    });

    it('returns red when value is 0', () => {
      expect(evaluateThreshold(0, cfg)).toBe('red');
    });
  });

  describe('dbPoolUtilizationPct — lowerIsBetter, green ≤ 70, yellow ≤ 90', () => {
    const cfg = HEALTH_THRESHOLDS.dbPoolUtilizationPct;

    it('returns green when value is well below boundary (15)', () => {
      expect(evaluateThreshold(15, cfg)).toBe('green');
    });

    it('returns green when value equals green boundary (70)', () => {
      expect(evaluateThreshold(70, cfg)).toBe('green');
    });

    it('returns yellow between boundaries (80)', () => {
      expect(evaluateThreshold(80, cfg)).toBe('yellow');
    });

    it('returns yellow when value equals yellow boundary (90)', () => {
      expect(evaluateThreshold(90, cfg)).toBe('yellow');
    });

    it('returns red when value exceeds yellow boundary (91)', () => {
      expect(evaluateThreshold(91, cfg)).toBe('red');
    });

    it('returns red when value is 100 (fully saturated)', () => {
      expect(evaluateThreshold(100, cfg)).toBe('red');
    });
  });

  describe('apiLatencyMs — lowerIsBetter, green ≤ 200, yellow ≤ 500', () => {
    const cfg = HEALTH_THRESHOLDS.apiLatencyMs;

    it('returns green at boundary (200)', () => {
      expect(evaluateThreshold(200, cfg)).toBe('green');
    });

    it('returns yellow at boundary (500)', () => {
      expect(evaluateThreshold(500, cfg)).toBe('yellow');
    });

    it('returns red above boundary (501)', () => {
      expect(evaluateThreshold(501, cfg)).toBe('red');
    });
  });

  describe('errorRatePct — lowerIsBetter, green ≤ 1, yellow ≤ 5', () => {
    const cfg = HEALTH_THRESHOLDS.errorRatePct;

    it('returns green at 0%', () => {
      expect(evaluateThreshold(0, cfg)).toBe('green');
    });

    it('returns green at boundary (1%)', () => {
      expect(evaluateThreshold(1, cfg)).toBe('green');
    });

    it('returns yellow between boundaries (3%)', () => {
      expect(evaluateThreshold(3, cfg)).toBe('yellow');
    });

    it('returns red above yellow boundary (5.1%)', () => {
      expect(evaluateThreshold(5.1, cfg)).toBe('red');
    });
  });
});

// ---------------------------------------------------------------------------
// worstStatus
// ---------------------------------------------------------------------------

describe('worstStatus', () => {
  it('returns green when all statuses are green', () => {
    expect(worstStatus(['green', 'green', 'green'])).toBe('green');
  });

  it('returns yellow when at least one yellow and no red', () => {
    expect(worstStatus(['green', 'yellow', 'green'])).toBe('yellow');
  });

  it('returns red when at least one red', () => {
    expect(worstStatus(['green', 'yellow', 'red'])).toBe('red');
  });

  it('returns red even when mixed with all other statuses', () => {
    expect(worstStatus(['red', 'yellow', 'green'])).toBe('red');
  });

  it('returns green for an empty array', () => {
    expect(worstStatus([])).toBe('green');
  });
});

// ---------------------------------------------------------------------------
// StatusCard component rendering
// ---------------------------------------------------------------------------

describe('StatusCard', () => {
  it('renders title, value, and unit', () => {
    render(<StatusCard title="API Success Rate" value="99.5" unit="%" status="green" />);
    expect(screen.getByText('API Success Rate')).toBeInTheDocument();
    expect(screen.getByText('99.5')).toBeInTheDocument();
    expect(screen.getByText('%')).toBeInTheDocument();
  });

  it('renders description when provided', () => {
    render(
      <StatusCard title="Test Metric" value="50" status="green" description="Some detail" />,
    );
    expect(screen.getByText('Some detail')).toBeInTheDocument();
  });

  it('does not render description element when omitted', () => {
    render(<StatusCard title="Test Metric" value="50" status="green" />);
    expect(screen.queryByText('Some detail')).not.toBeInTheDocument();
  });

  it('renders accessible aria-label', () => {
    render(<StatusCard title="DB Pool Utilization" value="85" unit="%" status="yellow" />);
    const card = screen.getByTestId('status-card-db-pool-utilization');
    expect(card).toHaveAttribute('aria-label', 'DB Pool Utilization: 85 %');
  });

  it('renders correct data-testid for each status', () => {
    const { rerender } = render(<StatusCard title="Rate" value="99" status="green" />);
    expect(screen.getByTestId('status-card-rate')).toBeInTheDocument();

    rerender(<StatusCard title="Rate" value="93" status="yellow" />);
    expect(screen.getByTestId('status-card-rate')).toBeInTheDocument();

    rerender(<StatusCard title="Rate" value="50" status="red" />);
    expect(screen.getByTestId('status-card-rate')).toBeInTheDocument();
  });

  it('renders value without unit when unit is omitted', () => {
    render(<StatusCard title="Score" value="95" status="green" />);
    expect(screen.getByText('95')).toBeInTheDocument();
  });
});
