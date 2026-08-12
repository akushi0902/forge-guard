import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { TrendChartCard } from '@/pages/EngineeringManager/components/TrendChartCard';
import { ASSESSMENT_TRENDS_RESPONSE } from '@/test/fixtures/managerDashboardData';

describe('TrendChartCard', () => {
  it('renders the card heading', () => {
    render(<TrendChartCard data={ASSESSMENT_TRENDS_RESPONSE.trends} isLoading={false} />);
    expect(screen.getByText('Health Score Trend — Last 6 Months')).toBeInTheDocument();
  });

  it('renders the chart container with accessible aria-label when data is present', () => {
    render(<TrendChartCard data={ASSESSMENT_TRENDS_RESPONSE.trends} isLoading={false} />);
    const chart = screen.getByRole('img', { name: /bar chart showing monthly average health scores/i });
    expect(chart).toBeInTheDocument();
  });

  it('shows loading text while fetching', () => {
    render(<TrendChartCard data={undefined} isLoading={true} />);
    expect(screen.getByText('Loading trend data…')).toBeInTheDocument();
  });

  it('shows empty state when data is undefined and not loading', () => {
    render(<TrendChartCard data={undefined} isLoading={false} />);
    expect(screen.getByText('No trend data available.')).toBeInTheDocument();
  });

  it('shows empty state for empty array', () => {
    render(<TrendChartCard data={[]} isLoading={false} />);
    expect(screen.getByText('No trend data available.')).toBeInTheDocument();
  });
});
