import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { MockDataBadge } from '@/components/common/MockDataBadge';

describe('MockDataBadge', () => {
  it('renders the default label "Simulated"', () => {
    render(<MockDataBadge />);
    expect(screen.getByTestId('mock-data-badge')).toHaveTextContent('Simulated');
  });

  it('renders a custom label when provided', () => {
    render(<MockDataBadge label="Demo Mode" />);
    expect(screen.getByTestId('mock-data-badge')).toHaveTextContent('Demo Mode');
  });

  it('has aria-label="Simulated data" for screen reader accessibility (AC-6)', () => {
    render(<MockDataBadge />);
    expect(screen.getByTestId('mock-data-badge')).toHaveAttribute(
      'aria-label',
      'Simulated data',
    );
  });

  it('is visible in the document', () => {
    render(<MockDataBadge />);
    expect(screen.getByTestId('mock-data-badge')).toBeVisible();
  });

  it('uses orange color via Mantine data-color attribute', () => {
    render(<MockDataBadge />);
    const badge = screen.getByTestId('mock-data-badge');
    expect(badge).toHaveAttribute('data-color', 'orange');
  });

  it('is not rendered with red or green color (AC-1 constraint)', () => {
    render(<MockDataBadge />);
    const badge = screen.getByTestId('mock-data-badge');
    expect(badge).not.toHaveAttribute('data-color', 'red');
    expect(badge).not.toHaveAttribute('data-color', 'green');
  });
});
