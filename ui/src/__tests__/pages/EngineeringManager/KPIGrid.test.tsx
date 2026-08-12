import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { KPIGrid } from '@/pages/EngineeringManager/components/KPIGrid';
import {
  SERVICES_WITH_METRICS,
  EMPTY_SERVICES_RESPONSE,
} from '@/test/fixtures/managerDashboardData';

describe('KPIGrid', () => {
  it('renders all 4 KPI card titles', () => {
    render(<KPIGrid services={SERVICES_WITH_METRICS} />);
    expect(screen.getByText('Avg Health Score')).toBeInTheDocument();
    expect(screen.getByText('Services ≥ 70')).toBeInTheDocument();
    expect(screen.getByText('Critical Findings')).toBeInTheDocument();
    expect(screen.getByText('Avg Time to Remediate')).toBeInTheDocument();
  });

  it('computes correct average health score from fixture data', () => {
    render(<KPIGrid services={SERVICES_WITH_METRICS} />);
    // 19 scored services (svc-020 has null score)
    // Sum: 85+91+72+55+88+45+78+62+93+38+80+67+74+89+76+83+96+70+82 = 1424; avg = Math.round(1424/19) = 75
    const kpiCard = screen.getByTestId('kpi-avg-score');
    expect(kpiCard).toBeInTheDocument();
    expect(screen.getByText('75')).toBeInTheDocument();
  });

  it('counts services with health_score >= 70', () => {
    render(<KPIGrid services={SERVICES_WITH_METRICS} />);
    // Services >= 70: 85,91,72,88,78,93,80,74,89,76,83,96,70,82 = 14
    const kpiCard = screen.getByTestId('kpi-above-threshold');
    expect(kpiCard.textContent).toContain('14');
  });

  it('sums critical findings across all services', () => {
    render(<KPIGrid services={SERVICES_WITH_METRICS} />);
    // Sum of critical_findings: 1+0+0+2+0+3+0+1+0+4+0+1+0+0+0+0+0+0+0+0 = 12
    const kpiCard = screen.getByTestId('kpi-critical-findings');
    expect(kpiCard.textContent).toContain('12');
  });

  it('shows em-dash for avg score when no services are provided', () => {
    render(<KPIGrid services={[]} />);
    expect(screen.getByTestId('kpi-avg-score').textContent).toContain('—');
  });

  it('shows em-dash for avg TTR when no services have TTR data', () => {
    render(
      <KPIGrid
        services={EMPTY_SERVICES_RESPONSE.items}
      />,
    );
    expect(screen.getByTestId('kpi-avg-ttr').textContent).toContain('—');
  });
});
