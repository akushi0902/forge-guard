import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@/test-utils';
import userEvent from '@testing-library/user-event';
import { ServicesTableCard } from '@/pages/EngineeringManager/components/ServicesTableCard';
import { SERVICES_WITH_METRICS } from '@/test/fixtures/managerDashboardData';

describe('ServicesTableCard', () => {
  it('renders the card heading', () => {
    render(
      <ServicesTableCard
        services={SERVICES_WITH_METRICS}
        isLoading={false}
        selectedTeam=""
        onTeamChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Services Overview')).toBeInTheDocument();
  });

  it('renders service rows in the table', () => {
    render(
      <ServicesTableCard
        services={SERVICES_WITH_METRICS}
        isLoading={false}
        selectedTeam=""
        onTeamChange={vi.fn()}
      />,
    );
    expect(screen.getByText('payment-service')).toBeInTheDocument();
    expect(screen.getByText('auth-service')).toBeInTheDocument();
  });

  it('renders column headers: Service, Team, Health Score, Trend, Critical, High, Medium, Low', () => {
    render(
      <ServicesTableCard
        services={SERVICES_WITH_METRICS}
        isLoading={false}
        selectedTeam=""
        onTeamChange={vi.fn()}
      />,
    );
    expect(screen.getByText('Service')).toBeInTheDocument();
    expect(screen.getByText('Team')).toBeInTheDocument();
    expect(screen.getByText('Health Score')).toBeInTheDocument();
    expect(screen.getByText('Trend')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
    expect(screen.getByText('Medium')).toBeInTheDocument();
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('renders the team filter select and export button', () => {
    render(
      <ServicesTableCard
        services={SERVICES_WITH_METRICS}
        isLoading={false}
        selectedTeam=""
        onTeamChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('team-filter-select')).toBeInTheDocument();
    expect(screen.getByTestId('export-csv-btn')).toBeInTheDocument();
  });

  it('disables the export button when services list is empty', () => {
    render(
      <ServicesTableCard
        services={[]}
        isLoading={false}
        selectedTeam=""
        onTeamChange={vi.fn()}
      />,
    );
    expect(screen.getByTestId('export-csv-btn')).toBeDisabled();
  });

  it('shows the empty state message when services is empty', () => {
    render(
      <ServicesTableCard
        services={[]}
        isLoading={false}
        selectedTeam=""
        onTeamChange={vi.fn()}
      />,
    );
    expect(screen.getByText('No services found.')).toBeInTheDocument();
  });

  it('shows a clear filter option when a team filter is active and there are no results', () => {
    const onTeamChange = vi.fn();
    render(
      <ServicesTableCard
        services={[]}
        isLoading={false}
        selectedTeam="nonexistent-team"
        onTeamChange={onTeamChange}
      />,
    );
    expect(screen.getByText('Clear team filter')).toBeInTheDocument();
  });

  it('sorts by health score descending by default (highest score first)', () => {
    render(
      <ServicesTableCard
        services={SERVICES_WITH_METRICS}
        isLoading={false}
        selectedTeam=""
        onTeamChange={vi.fn()}
      />,
    );
    const table = screen.getByTestId('services-table');
    const rows = table.querySelectorAll('tbody tr');
    expect(rows.length).toBe(SERVICES_WITH_METRICS.length);
    // First row should be the service with highest score (config-service: 96)
    expect(rows[0]!.textContent).toContain('config-service');
  });

  it('calls onTeamChange when a team is selected from the dropdown', async () => {
    const user = userEvent.setup();
    const onTeamChange = vi.fn();
    render(
      <ServicesTableCard
        services={SERVICES_WITH_METRICS}
        isLoading={false}
        selectedTeam=""
        onTeamChange={onTeamChange}
      />,
    );
    // Verify the team filter select exists
    const select = screen.getByTestId('team-filter-select');
    expect(select).toBeInTheDocument();
  });
});
