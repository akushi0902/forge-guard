import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { DimensionBar } from '@/components/dashboard/DimensionBar';

describe('DimensionBar', () => {
  it('renders a human-readable label for a snake_case name', () => {
    render(<DimensionBar name="code_quality" score={80} />);
    expect(screen.getByText('Code Quality')).toBeInTheDocument();
  });

  it('renders the numeric score as a percentage', () => {
    render(<DimensionBar name="security" score={87} />);
    expect(screen.getByText('87%')).toBeInTheDocument();
  });

  it('has an aria-label combining label and score', () => {
    render(<DimensionBar name="test_coverage" score={75} />);
    expect(
      screen.getByRole('img', { hidden: true }) ||
        document.querySelector('[aria-label*="Test Coverage"]'),
    ).toBeDefined();
    const wrapper = document.querySelector('[aria-label="Test Coverage: 75 out of 100"]');
    expect(wrapper).toBeInTheDocument();
  });

  it('renders all known dimension labels', () => {
    const dimensions = [
      { name: 'code_quality',         label: 'Code Quality' },
      { name: 'test_coverage',        label: 'Test Coverage' },
      { name: 'security',             label: 'Security' },
      { name: 'documentation',        label: 'Documentation' },
      { name: 'operations_readiness', label: 'Operations Readiness' },
    ];
    for (const { name, label } of dimensions) {
      const { unmount } = render(<DimensionBar name={name} score={70} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });

  it('clamps a score above 100 to 100', () => {
    render(<DimensionBar name="security" score={150} />);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('clamps a score below 0 to 0', () => {
    render(<DimensionBar name="security" score={-10} />);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('renders a score of exactly 0', () => {
    render(<DimensionBar name="security" score={0} />);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('renders a score of exactly 100', () => {
    render(<DimensionBar name="security" score={100} />);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('uses a fallback label for an unknown dimension key', () => {
    render(<DimensionBar name="unknown_dimension" score={50} />);
    expect(screen.getByText('unknown dimension')).toBeInTheDocument();
  });

  it('renders a progress bar element', () => {
    render(<DimensionBar name="security" score={70} />);
    const bar = document.querySelector('[role="progressbar"]');
    expect(bar).toBeInTheDocument();
  });
});
