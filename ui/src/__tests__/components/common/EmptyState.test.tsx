import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { EmptyState } from '@/components/common/EmptyState';

const defaultProps = {
  title: 'Nothing Here',
  description: 'There is nothing to display right now.',
  ctaLabel: 'Get Started',
  ctaAction: vi.fn(),
};

describe('EmptyState — base component', () => {
  it('renders the title', () => {
    render(<EmptyState {...defaultProps} />);
    expect(screen.getByTestId('empty-state-title')).toHaveTextContent('Nothing Here');
  });

  it('renders the description', () => {
    render(<EmptyState {...defaultProps} />);
    expect(screen.getByTestId('empty-state-description')).toHaveTextContent(
      'There is nothing to display right now.',
    );
  });

  it('renders the CTA button with correct label', () => {
    render(<EmptyState {...defaultProps} />);
    expect(screen.getByTestId('empty-state-cta')).toHaveTextContent('Get Started');
  });

  it('calls ctaAction when CTA button is clicked', async () => {
    const handler = vi.fn();
    render(<EmptyState {...defaultProps} ctaAction={handler} />);
    await userEvent.click(screen.getByTestId('empty-state-cta'));
    expect(handler).toHaveBeenCalledOnce();
  });

  it('renders a CTA as anchor when ctaAction is a string href', () => {
    render(<EmptyState {...defaultProps} ctaAction="/releases/new" />);
    const cta = screen.getByTestId('empty-state-cta');
    expect(cta.tagName).toBe('A');
    expect(cta).toHaveAttribute('href', '/releases/new');
  });

  it('renders the illustration when provided', () => {
    render(
      <EmptyState
        {...defaultProps}
        illustration={<span data-testid="illus">📊</span>}
      />,
    );
    expect(screen.getByTestId('illus')).toBeInTheDocument();
  });

  it('does not render an illustration wrapper when illustration is omitted', () => {
    render(<EmptyState {...defaultProps} />);
    expect(screen.queryByLabelText('illustration')).not.toBeInTheDocument();
  });

  it('renders onboarding steps when provided', () => {
    const steps = [
      { label: 'Step one' },
      { label: 'Step two', description: 'More detail about step two.' },
    ];
    render(<EmptyState {...defaultProps} steps={steps} />);
    expect(screen.getByTestId('empty-state-steps')).toBeInTheDocument();
    expect(screen.getByText('Step one')).toBeInTheDocument();
    expect(screen.getByText('Step two')).toBeInTheDocument();
    expect(screen.getByText('More detail about step two.')).toBeInTheDocument();
  });

  it('does not render a steps list when steps prop is omitted', () => {
    render(<EmptyState {...defaultProps} />);
    expect(screen.queryByTestId('empty-state-steps')).not.toBeInTheDocument();
  });

  it('does not render a steps list when steps array is empty', () => {
    render(<EmptyState {...defaultProps} steps={[]} />);
    expect(screen.queryByTestId('empty-state-steps')).not.toBeInTheDocument();
  });

  it('applies a custom testId to the root element', () => {
    render(<EmptyState {...defaultProps} testId="custom-empty" />);
    expect(screen.getByTestId('custom-empty')).toBeInTheDocument();
  });

  it('defaults to data-testid="empty-state" when testId is omitted', () => {
    render(<EmptyState {...defaultProps} />);
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
  });

  it('CTA button is keyboard focusable (has tabIndex accessible via role=button)', async () => {
    render(<EmptyState {...defaultProps} />);
    const btn = screen.getByRole('button', { name: /get started/i });
    expect(btn).toBeInTheDocument();
    btn.focus();
    expect(btn).toHaveFocus();
  });

  it('activates CTA via keyboard Enter key', async () => {
    const handler = vi.fn();
    render(<EmptyState {...defaultProps} ctaAction={handler} />);
    const btn = screen.getByRole('button', { name: /get started/i });
    btn.focus();
    await userEvent.keyboard('{Enter}');
    expect(handler).toHaveBeenCalledOnce();
  });

  it('renders illustration with aria-hidden wrapper (illustration is decorative)', () => {
    render(
      <EmptyState
        {...defaultProps}
        illustration={<svg data-testid="svg-illus" />}
      />,
    );
    const wrapper = screen.getByTestId('svg-illus').parentElement;
    expect(wrapper).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders a ctaIcon inside the CTA button when provided', () => {
    render(
      <EmptyState
        {...defaultProps}
        ctaIcon={<span data-testid="cta-icon">▶</span>}
      />,
    );
    expect(screen.getByTestId('cta-icon')).toBeInTheDocument();
  });
});
