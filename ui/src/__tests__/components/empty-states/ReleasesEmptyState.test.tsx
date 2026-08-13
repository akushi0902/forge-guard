import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { ReleasesEmptyState } from '@/components/empty-states/ReleasesEmptyState';

describe('ReleasesEmptyState', () => {
  it('renders the correct title (AC-3)', () => {
    render(<ReleasesEmptyState onRequestAssessment={vi.fn()} />);
    expect(screen.getByText('No Release Assessments')).toBeInTheDocument();
  });

  it('renders the CTA button with correct label', () => {
    render(<ReleasesEmptyState onRequestAssessment={vi.fn()} />);
    expect(screen.getByRole('button', { name: /request release assessment/i })).toBeInTheDocument();
  });

  it('calls onRequestAssessment when CTA is clicked', async () => {
    const handler = vi.fn();
    render(<ReleasesEmptyState onRequestAssessment={handler} />);
    await userEvent.click(screen.getByRole('button', { name: /request release assessment/i }));
    expect(handler).toHaveBeenCalledOnce();
  });

  it('renders onboarding steps explaining the assessment flow', () => {
    render(<ReleasesEmptyState onRequestAssessment={vi.fn()} />);
    expect(screen.getByText('Select a service and commit')).toBeInTheDocument();
  });

  it('renders an illustration with aria-hidden', () => {
    render(<ReleasesEmptyState onRequestAssessment={vi.fn()} />);
    expect(document.querySelector('svg[aria-hidden="true"]')).toBeInTheDocument();
  });
});
