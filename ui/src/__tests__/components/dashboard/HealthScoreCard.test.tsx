import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { HealthScoreCard, healthScoreColor } from '@/components/dashboard/HealthScoreCard';
import { HEALTHY_SCORE_FIXTURE, WARNING_SCORE_FIXTURE, CRITICAL_SCORE_FIXTURE, ZERO_SCORE_FIXTURE, PERFECT_SCORE_FIXTURE } from '@/test/fixtures/scores';

describe('HealthScoreCard', () => {
  it('renders the card heading', () => {
    render(<HealthScoreCard score={HEALTHY_SCORE_FIXTURE} />);
    expect(screen.getByText('Engineering Health Score')).toBeInTheDocument();
  });

  it('renders a ScoreRing SVG with the overall score', () => {
    render(<HealthScoreCard score={HEALTHY_SCORE_FIXTURE} />);
    const svg = document.querySelector('svg[role="img"]');
    expect(svg).toBeInTheDocument();
    expect(svg?.getAttribute('aria-label')).toContain('85');
  });

  it('renders 5 DimensionBar components', () => {
    render(<HealthScoreCard score={HEALTHY_SCORE_FIXTURE} />);
    expect(screen.getByText('Code Quality')).toBeInTheDocument();
    expect(screen.getByText('Test Coverage')).toBeInTheDocument();
    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByText('Documentation')).toBeInTheDocument();
    expect(screen.getByText('Operations Readiness')).toBeInTheDocument();
  });

  it('shows individual dimension scores', () => {
    render(<HealthScoreCard score={HEALTHY_SCORE_FIXTURE} />);
    expect(screen.getByText('88%')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
  });

  it('renders a score of 0 without crashing', () => {
    render(<HealthScoreCard score={ZERO_SCORE_FIXTURE} />);
    const svgs = document.querySelectorAll('svg[role="img"]');
    expect(svgs.length).toBeGreaterThan(0);
    expect(svgs[0]?.getAttribute('aria-label')).toContain('0');
  });

  it('renders a perfect score of 100 without overflow', () => {
    render(<HealthScoreCard score={PERFECT_SCORE_FIXTURE} />);
    const svg = document.querySelector('svg[role="img"]');
    expect(svg?.getAttribute('aria-label')).toContain('100');
  });

  it('uses green color for a healthy score (≥ 70)', () => {
    render(<HealthScoreCard score={HEALTHY_SCORE_FIXTURE} />);
    const progressCircle = document.querySelectorAll('circle')[1];
    expect(progressCircle?.getAttribute('stroke')).toContain('#16a34a');
  });

  it('uses amber/warning color for a borderline score (50–69)', () => {
    render(<HealthScoreCard score={WARNING_SCORE_FIXTURE} />);
    const progressCircle = document.querySelectorAll('circle')[1];
    expect(progressCircle?.getAttribute('stroke')).toContain('#d97706');
  });

  it('uses red/danger color for a critical score (< 50)', () => {
    render(<HealthScoreCard score={CRITICAL_SCORE_FIXTURE} />);
    const progressCircle = document.querySelectorAll('circle')[1];
    expect(progressCircle?.getAttribute('stroke')).toContain('#dc2626');
  });
});

// ---------------------------------------------------------------------------
// healthScoreColor unit tests
// ---------------------------------------------------------------------------

describe('healthScoreColor', () => {
  it('returns green color for score 70 (boundary)', () => {
    expect(healthScoreColor(70)).toContain('#16a34a');
  });

  it('returns green color for score 100 (perfect)', () => {
    expect(healthScoreColor(100)).toContain('#16a34a');
  });

  it('returns green color for score 85', () => {
    expect(healthScoreColor(85)).toContain('#16a34a');
  });

  it('returns amber color for score 69 (just below green)', () => {
    expect(healthScoreColor(69)).toContain('#d97706');
  });

  it('returns amber color for score 50 (boundary)', () => {
    expect(healthScoreColor(50)).toContain('#d97706');
  });

  it('returns red color for score 49 (just below amber)', () => {
    expect(healthScoreColor(49)).toContain('#dc2626');
  });

  it('returns red color for score 0', () => {
    expect(healthScoreColor(0)).toContain('#dc2626');
  });
});
