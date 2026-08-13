import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { MockDataBanner } from '@/components/common/MockDataBanner';

beforeEach(() => {
  sessionStorage.clear();
});

describe('MockDataBanner', () => {
  it('renders the banner with title "Simulated Data" (AC-1)', () => {
    render(<MockDataBanner />);
    expect(screen.getByText('Simulated Data')).toBeInTheDocument();
  });

  it('renders the description about demo data (AC-1)', () => {
    render(<MockDataBanner />);
    expect(
      screen.getByText(/demo data for demonstration purposes/i),
    ).toBeInTheDocument();
  });

  it('has role="status" for screen reader announcement (AC-5)', () => {
    render(<MockDataBanner />);
    expect(screen.getByTestId('mock-data-banner')).toHaveAttribute(
      'role',
      'status',
    );
  });

  it('has aria-label describing demo data context (AC-5)', () => {
    render(<MockDataBanner />);
    expect(screen.getByTestId('mock-data-banner')).toHaveAttribute(
      'aria-label',
      'This service uses simulated demo data',
    );
  });

  it('is visible in the document', () => {
    render(<MockDataBanner />);
    expect(screen.getByTestId('mock-data-banner')).toBeVisible();
  });

  it('renders with orange color — not red or green (constraint)', () => {
    render(<MockDataBanner />);
    const banner = screen.getByTestId('mock-data-banner');
    expect(banner).toHaveAttribute('data-color', 'orange');
  });

  it('is dismissible — hides after close button is clicked', async () => {
    render(<MockDataBanner />);
    const closeBtn = screen.getByRole('button', { name: /close/i });
    await userEvent.click(closeBtn);
    expect(screen.queryByTestId('mock-data-banner')).not.toBeInTheDocument();
  });

  it('persists dismissed state in sessionStorage', async () => {
    render(<MockDataBanner />);
    const closeBtn = screen.getByRole('button', { name: /close/i });
    await userEvent.click(closeBtn);
    expect(sessionStorage.getItem('forgeguard-demo-banner-dismissed')).toBe('true');
  });

  it('does not render when already dismissed via sessionStorage', () => {
    sessionStorage.setItem('forgeguard-demo-banner-dismissed', 'true');
    render(<MockDataBanner />);
    expect(screen.queryByTestId('mock-data-banner')).not.toBeInTheDocument();
  });
});
