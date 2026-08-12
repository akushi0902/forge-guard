import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { ResolutionRateCard } from '@/pages/EngineeringManager/components/ResolutionRateCard';
import { ASSESSMENT_TRENDS_RESPONSE } from '@/test/fixtures/managerDashboardData';

describe('ResolutionRateCard', () => {
  it('renders the card heading', () => {
    render(
      <ResolutionRateCard
        data={ASSESSMENT_TRENDS_RESPONSE.resolution_rates}
        isLoading={false}
      />,
    );
    expect(screen.getByText('Finding Resolution Rate — Last 6 Months')).toBeInTheDocument();
  });

  it('renders the chart container with accessible aria-label', () => {
    render(
      <ResolutionRateCard
        data={ASSESSMENT_TRENDS_RESPONSE.resolution_rates}
        isLoading={false}
      />,
    );
    const chart = screen.getByRole('img', {
      name: /bar chart showing monthly finding resolution rates/i,
    });
    expect(chart).toBeInTheDocument();
  });

  it('shows loading text while fetching', () => {
    render(<ResolutionRateCard data={undefined} isLoading={true} />);
    expect(screen.getByText('Loading resolution data…')).toBeInTheDocument();
  });

  it('shows empty state when data is undefined and not loading', () => {
    render(<ResolutionRateCard data={undefined} isLoading={false} />);
    expect(screen.getByText('No resolution data available.')).toBeInTheDocument();
  });

  it('shows empty state for empty array', () => {
    render(<ResolutionRateCard data={[]} isLoading={false} />);
    expect(screen.getByText('No resolution data available.')).toBeInTheDocument();
  });
});
