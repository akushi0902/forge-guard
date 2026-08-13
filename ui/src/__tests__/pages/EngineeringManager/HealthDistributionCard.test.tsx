import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { HealthDistributionCard } from '@/pages/EngineeringManager/components/HealthDistributionCard';
import { SERVICES_WITH_METRICS } from '@/test/fixtures/managerDashboardData';

describe('HealthDistributionCard', () => {
  it('renders the card heading', () => {
    render(<HealthDistributionCard services={SERVICES_WITH_METRICS} />);
    expect(screen.getByText('Health Score Distribution')).toBeInTheDocument();
  });

  it('renders the distribution legend', () => {
    render(<HealthDistributionCard services={SERVICES_WITH_METRICS} />);
    const legend = screen.getByTestId('distribution-legend');
    expect(legend).toBeInTheDocument();
    expect(legend.textContent).toContain('85–100 Healthy');
    expect(legend.textContent).toContain('70–84 Good');
    expect(legend.textContent).toContain('50–69 Warning');
    expect(legend.textContent).toContain('0–49 Critical');
  });

  it('renders the accessible progress bar with aria-label', () => {
    render(<HealthDistributionCard services={SERVICES_WITH_METRICS} />);
    const bar = screen.getByRole('progressbar');
    expect(bar).toBeInTheDocument();
  });

  it('shows the empty state when no services are provided', () => {
    render(<HealthDistributionCard services={[]} />);
    expect(screen.getByText('No evaluated services.')).toBeInTheDocument();
  });

  it('shows the empty state when all services have null scores', () => {
    const noScoreServices = SERVICES_WITH_METRICS.filter((s) => s.health_score == null);
    render(<HealthDistributionCard services={noScoreServices} />);
    expect(screen.getByText('No evaluated services.')).toBeInTheDocument();
  });
});
