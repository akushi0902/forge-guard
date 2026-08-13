import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { ServiceHealthEmptyState } from '@/components/empty-states/ServiceHealthEmptyState';

describe('ServiceHealthEmptyState', () => {
  it('renders the correct title (AC-1)', () => {
    render(<ServiceHealthEmptyState onRunEvaluation={vi.fn()} />);
    expect(screen.getByText('No Evaluations Yet')).toBeInTheDocument();
  });

  it('renders the CTA button with correct label', () => {
    render(<ServiceHealthEmptyState onRunEvaluation={vi.fn()} />);
    expect(screen.getByRole('button', { name: /run first evaluation/i })).toBeInTheDocument();
  });

  it('calls onRunEvaluation when CTA is clicked', async () => {
    const handler = vi.fn();
    render(<ServiceHealthEmptyState onRunEvaluation={handler} />);
    await userEvent.click(screen.getByRole('button', { name: /run first evaluation/i }));
    expect(handler).toHaveBeenCalledOnce();
  });

  it('renders 3 onboarding steps', () => {
    render(<ServiceHealthEmptyState onRunEvaluation={vi.fn()} />);
    expect(screen.getByText('Register your service')).toBeInTheDocument();
    expect(screen.getByText('Configure policies')).toBeInTheDocument();
    expect(screen.getByText('Run first evaluation')).toBeInTheDocument();
  });

  it('renders an illustration', () => {
    render(<ServiceHealthEmptyState onRunEvaluation={vi.fn()} />);
    expect(document.querySelector('svg[aria-hidden="true"]')).toBeInTheDocument();
  });

  it('has accessible CTA button name', () => {
    render(<ServiceHealthEmptyState onRunEvaluation={vi.fn()} />);
    expect(
      screen.getByRole('button', { name: /run first evaluation/i }),
    ).toBeVisible();
  });
});
