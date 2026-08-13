import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { HealthScoreCard } from '@/components/dashboard/HealthScoreCard';
import { HEALTHY_SCORE_FIXTURE, ZERO_SCORE_FIXTURE, PERFECT_SCORE_FIXTURE } from '@/test/fixtures/scores';

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
});
