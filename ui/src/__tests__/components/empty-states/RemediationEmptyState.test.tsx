import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { RemediationEmptyState } from '@/components/empty-states/RemediationEmptyState';

describe('RemediationEmptyState', () => {
  it('renders the correct title (AC-4)', () => {
    render(<RemediationEmptyState onViewFindings={vi.fn()} />);
    expect(screen.getByText('No Remediation Items')).toBeInTheDocument();
  });

  it('renders the CTA button with correct label', () => {
    render(<RemediationEmptyState onViewFindings={vi.fn()} />);
    expect(screen.getByRole('button', { name: /view findings/i })).toBeInTheDocument();
  });

  it('calls onViewFindings when CTA is clicked', async () => {
    const handler = vi.fn();
    render(<RemediationEmptyState onViewFindings={handler} />);
    await userEvent.click(screen.getByRole('button', { name: /view findings/i }));
    expect(handler).toHaveBeenCalledOnce();
  });

  it('renders onboarding steps explaining the remediation lifecycle', () => {
    render(<RemediationEmptyState onViewFindings={vi.fn()} />);
    expect(screen.getByText('Generate findings via evaluation')).toBeInTheDocument();
  });

  it('renders an illustration with aria-hidden', () => {
    render(<RemediationEmptyState onViewFindings={vi.fn()} />);
    expect(document.querySelector('svg[aria-hidden="true"]')).toBeInTheDocument();
  });
});
