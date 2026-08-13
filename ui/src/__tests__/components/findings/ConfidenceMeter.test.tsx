import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '@/test-utils';
import { ConfidenceMeter } from '@/components/findings/ConfidenceMeter';

describe('ConfidenceMeter', () => {
  it('renders percentage label for fractional score', () => {
    render(<ConfidenceMeter score={0.92} />);
    expect(screen.getByText('92%')).toBeInTheDocument();
  });

  it('renders percentage label for integer score', () => {
    render(<ConfidenceMeter score={75} />);
    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('renders 0% label for zero score', () => {
    render(<ConfidenceMeter score={0} />);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('renders 100% label for score of 1', () => {
    render(<ConfidenceMeter score={1} />);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('renders 100% label for score of 100', () => {
    render(<ConfidenceMeter score={100} />);
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('renders default "Confidence" label', () => {
    render(<ConfidenceMeter score={0.5} />);
    expect(screen.getByText('Confidence')).toBeInTheDocument();
  });

  it('renders custom label', () => {
    render(<ConfidenceMeter score={0.8} label="AI Confidence" />);
    expect(screen.getByText('AI Confidence')).toBeInTheDocument();
  });

  it('renders a progress bar with correct aria attributes', () => {
    render(<ConfidenceMeter score={0.75} />);
    const progressbar = screen.getByRole('progressbar');
    expect(progressbar).toBeInTheDocument();
    expect(progressbar).toHaveAttribute('aria-valuenow', '75');
    expect(progressbar).toHaveAttribute('aria-valuemin', '0');
    expect(progressbar).toHaveAttribute('aria-valuemax', '100');
  });

  it('clamps score > 1 that exceeds 100 to 100', () => {
    render(<ConfidenceMeter score={1.5} />);
    // 1.5 > 1, so treated as percentage; clamped to 100
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  it('clamps negative score to 0', () => {
    render(<ConfidenceMeter score={-0.5} />);
    expect(screen.getByText('0%')).toBeInTheDocument();
  });

  it('accepts data-testid prop', () => {
    render(<ConfidenceMeter score={0.8} data-testid="my-meter" />);
    expect(screen.getByTestId('my-meter')).toBeInTheDocument();
  });
});
