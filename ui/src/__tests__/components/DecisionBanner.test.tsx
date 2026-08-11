import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '@/test-utils';
import { DecisionBanner } from '@/components/shared/DecisionBanner';

describe('DecisionBanner', () => {
  it('renders "approve" banner with correct title', () => {
    render(<DecisionBanner decision="approve" />);
    expect(screen.getByText(/approved.*ready to release/i)).toBeInTheDocument();
  });

  it('renders "conditional_approve" banner with correct title', () => {
    render(<DecisionBanner decision="conditional_approve" />);
    expect(screen.getByText(/conditionally approved/i)).toBeInTheDocument();
  });

  it('renders "block" banner with correct title', () => {
    render(<DecisionBanner decision="block" />);
    expect(screen.getByText(/blocked.*do not release/i)).toBeInTheDocument();
  });

  it('renders "pending" banner with correct title', () => {
    render(<DecisionBanner decision="pending" />);
    expect(screen.getByText(/assessment pending/i)).toBeInTheDocument();
  });

  it('renders default description when no description prop is given', () => {
    render(<DecisionBanner decision="approve" />);
    expect(screen.getByText(/all policy checks passed/i)).toBeInTheDocument();
  });

  it('renders custom description when provided', () => {
    render(<DecisionBanner decision="block" description="2 critical findings." />);
    expect(screen.getByText('2 critical findings.')).toBeInTheDocument();
  });

  it('sets data-decision attribute on approve', () => {
    const { container } = render(<DecisionBanner decision="approve" />);
    const alert = container.querySelector('[data-decision="approve"]');
    expect(alert).toBeInTheDocument();
  });

  it('sets data-decision attribute on block', () => {
    const { container } = render(<DecisionBanner decision="block" />);
    const alert = container.querySelector('[data-decision="block"]');
    expect(alert).toBeInTheDocument();
  });

  it('sets data-decision attribute on conditional_approve', () => {
    const { container } = render(<DecisionBanner decision="conditional_approve" />);
    const alert = container.querySelector('[data-decision="conditional_approve"]');
    expect(alert).toBeInTheDocument();
  });
});
