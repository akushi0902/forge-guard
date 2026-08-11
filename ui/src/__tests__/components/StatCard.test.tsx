import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { render } from '@/test-utils';
import { StatCard, KPICard } from '@/components/shared/StatCard';

describe('StatCard', () => {
  it('renders title and value', () => {
    render(<StatCard title="Open Findings" value={24} />);
    expect(screen.getByText('Open Findings')).toBeInTheDocument();
    expect(screen.getByText('24')).toBeInTheDocument();
  });

  it('renders string value', () => {
    render(<StatCard title="Health Score" value="87%" />);
    expect(screen.getByText('87%')).toBeInTheDocument();
  });

  it('renders optional subtitle', () => {
    render(<StatCard title="Issues" value={5} subtitle="vs. last week" />);
    expect(screen.getByText('vs. last week')).toBeInTheDocument();
  });

  it('renders trend up with aria-label', () => {
    render(<StatCard title="Coverage" value="82%" trend="up" />);
    expect(screen.getByLabelText('Trend: up')).toBeInTheDocument();
  });

  it('renders trend down with aria-label', () => {
    render(<StatCard title="Bugs" value={12} trend="down" />);
    expect(screen.getByLabelText('Trend: down')).toBeInTheDocument();
  });

  it('renders trend neutral with aria-label', () => {
    render(<StatCard title="Score" value={50} trend="neutral" />);
    expect(screen.getByLabelText('Trend: neutral')).toBeInTheDocument();
  });

  it('does not render trend indicator when trend prop is omitted', () => {
    render(<StatCard title="Issues" value={3} />);
    expect(screen.queryByLabelText(/trend/i)).not.toBeInTheDocument();
  });

  it('renders icon when provided', () => {
    render(
      <StatCard
        title="Services"
        value={10}
        icon={<span data-testid="icon">★</span>}
      />,
    );
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('renders without icon when not provided', () => {
    expect(() => render(<StatCard title="Items" value={0} />)).not.toThrow();
  });
});

describe('KPICard', () => {
  it('renders title, value, subtitle, and caption', () => {
    render(
      <KPICard
        title="Deployment Frequency"
        value="4x"
        subtitle="Per week"
        caption="DORA metric"
      />,
    );
    expect(screen.getByText('Deployment Frequency')).toBeInTheDocument();
    expect(screen.getByText('4x')).toBeInTheDocument();
    expect(screen.getByText('Per week · DORA metric')).toBeInTheDocument();
  });

  it('renders caption alone when no subtitle provided', () => {
    render(<KPICard title="MTR" value="2h" caption="Mean time to restore" />);
    expect(screen.getByText('Mean time to restore')).toBeInTheDocument();
  });

  it('renders with minimum required props', () => {
    expect(() => render(<KPICard title="Score" value={100} />)).not.toThrow();
  });
});
