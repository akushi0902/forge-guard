import { describe, expect, it, vi, afterEach } from 'vitest';
import { render } from '@/test-utils';
import { ScoreRing } from '@/components/shared/ScoreRing';

describe('ScoreRing', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders an SVG with role="img"', () => {
    const { container } = render(<ScoreRing score={75} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute('role', 'img');
  });

  it('aria-label includes score and label for score=0', () => {
    const { container } = render(<ScoreRing score={0} label="Health score" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-label', 'Health score: 0 out of 100');
  });

  it('aria-label includes score for score=50', () => {
    const { container } = render(<ScoreRing score={50} label="Security" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-label', 'Security: 50 out of 100');
  });

  it('aria-label includes score for score=100', () => {
    const { container } = render(<ScoreRing score={100} label="Quality" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-label', 'Quality: 100 out of 100');
  });

  it('uses default label "Score" when no label prop is given', () => {
    const { container } = render(<ScoreRing score={42} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-label', 'Score: 42 out of 100');
  });

  it('clamps score above 100 and warns in development', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { container } = render(<ScoreRing score={150} label="Test" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-label', 'Test: 100 out of 100');
    expect(warn).toHaveBeenCalled();
  });

  it('clamps negative score to 0 and warns in development', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { container } = render(<ScoreRing score={-10} label="Test" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-label', 'Test: 0 out of 100');
    expect(warn).toHaveBeenCalled();
  });

  it('handles NaN score gracefully and logs an error', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { container } = render(<ScoreRing score={NaN} label="Test" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('aria-label', 'Test: 0 out of 100');
    expect(error).toHaveBeenCalled();
  });

  it('applies custom size', () => {
    const { container } = render(<ScoreRing score={60} size={120} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('width', '120');
    expect(svg).toHaveAttribute('height', '120');
  });

  it('applies custom color override', () => {
    const { container } = render(<ScoreRing score={60} color="#ff0000" />);
    const circles = container.querySelectorAll('circle');
    // Second circle is the progress arc
    const progressCircle = circles[1];
    expect(progressCircle).toHaveAttribute('stroke', '#ff0000');
  });
});
