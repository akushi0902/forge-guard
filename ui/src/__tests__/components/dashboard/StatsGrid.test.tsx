import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { StatsGrid, formatRelativeTime } from '@/components/dashboard/StatsGrid';

describe('StatsGrid', () => {
  const defaultProps = {
    overallScore: 85,
    openFindingsCount: 4,
    criticalHighCount: 2,
    lastEvaluatedAt: '2026-08-11T10:00:00Z',
  };

  it('renders 4 StatCards', () => {
    render(<StatsGrid {...defaultProps} />);
    expect(screen.getByText('Health Score')).toBeInTheDocument();
    expect(screen.getByText('Open Findings')).toBeInTheDocument();
    expect(screen.getByText('Critical / High')).toBeInTheDocument();
    expect(screen.getByText('Last Evaluation')).toBeInTheDocument();
  });

  it('displays the correct health score value', () => {
    render(<StatsGrid {...defaultProps} />);
    expect(screen.getByText('85')).toBeInTheDocument();
  });

  it('displays the correct open findings count', () => {
    render(<StatsGrid {...defaultProps} />);
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('displays the critical/high count', () => {
    render(<StatsGrid {...defaultProps} />);
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows a relative timestamp for lastEvaluatedAt', () => {
    render(<StatsGrid {...defaultProps} />);
    const lastEvalCard = screen.getByText('Last Evaluation').closest('[class]');
    expect(lastEvalCard).toBeTruthy();
    // Relative time rendered — we just verify it's not the raw ISO string
    expect(screen.queryByText('2026-08-11T10:00:00Z')).not.toBeInTheDocument();
  });

  it('shows "Never" when lastEvaluatedAt is null', () => {
    render(<StatsGrid {...defaultProps} lastEvaluatedAt={null} />);
    expect(screen.getByText('Never')).toBeInTheDocument();
  });

  it('renders with zero open findings', () => {
    render(<StatsGrid {...defaultProps} openFindingsCount={0} criticalHighCount={0} />);
    expect(screen.getByText('Open Findings')).toBeInTheDocument();
  });
});

describe('formatRelativeTime', () => {
  it('returns "Never" for null', () => {
    expect(formatRelativeTime(null)).toBe('Never');
  });

  it('returns "Never" for undefined', () => {
    expect(formatRelativeTime(undefined)).toBe('Never');
  });

  it('returns a minutes-ago string for recent times', () => {
    const twoMinsAgo = new Date(Date.now() - 2 * 60_000).toISOString();
    expect(formatRelativeTime(twoMinsAgo)).toBe('2 min ago');
  });

  it('returns hours-ago for times within the same day', () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60_000).toISOString();
    expect(formatRelativeTime(threeHoursAgo)).toBe('3h ago');
  });

  it('returns "Yesterday" for exactly 1 day ago', () => {
    const oneDayAgo = new Date(Date.now() - 24 * 60 * 60_000 - 60_000).toISOString();
    expect(formatRelativeTime(oneDayAgo)).toBe('Yesterday');
  });

  it('appends a warning symbol for dates older than 30 days', () => {
    const oldDate = new Date(Date.now() - 35 * 24 * 60 * 60_000).toISOString();
    expect(formatRelativeTime(oldDate)).toContain('⚠');
  });
});
