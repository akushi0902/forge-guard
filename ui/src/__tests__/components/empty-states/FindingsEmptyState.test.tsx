import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { FindingsEmptyState } from '@/components/empty-states/FindingsEmptyState';

describe('FindingsEmptyState', () => {
  it('renders the correct title (AC-2)', () => {
    render(<FindingsEmptyState onTriggerEvaluation={vi.fn()} />);
    expect(screen.getByText('No Findings')).toBeInTheDocument();
  });

  it('renders the CTA button with correct label', () => {
    render(<FindingsEmptyState onTriggerEvaluation={vi.fn()} />);
    expect(screen.getByRole('button', { name: /run evaluation/i })).toBeInTheDocument();
  });

  it('calls onTriggerEvaluation when CTA is clicked', async () => {
    const handler = vi.fn();
    render(<FindingsEmptyState onTriggerEvaluation={handler} />);
    await userEvent.click(screen.getByRole('button', { name: /run evaluation/i }));
    expect(handler).toHaveBeenCalledOnce();
  });

  it('renders onboarding steps explaining how findings are generated', () => {
    render(<FindingsEmptyState onTriggerEvaluation={vi.fn()} />);
    expect(screen.getByText('Run a policy evaluation')).toBeInTheDocument();
  });

  it('renders an illustration with aria-hidden', () => {
    render(<FindingsEmptyState onTriggerEvaluation={vi.fn()} />);
    expect(document.querySelector('svg[aria-hidden="true"]')).toBeInTheDocument();
  });
});
