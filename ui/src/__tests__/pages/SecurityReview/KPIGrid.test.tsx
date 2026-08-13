/**
 * Unit tests for SecurityReview KPIGrid component (WO-077).
 *
 * Verifies KPI values computed from findings, escalations, and exceptions data.
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { render } from '@/test-utils';
import { KPIGrid } from '@/pages/SecurityReview/components/KPIGrid';
import {
  SECURITY_FINDINGS_PAGINATED,
  ESCALATIONS_PAGINATED,
  PENDING_EXCEPTIONS_PAGINATED,
} from '@/test/fixtures/securityFindings';

const defaultFindings = SECURITY_FINDINGS_PAGINATED.items;
const defaultEscalations = ESCALATIONS_PAGINATED.items;
const defaultExceptions = PENDING_EXCEPTIONS_PAGINATED.items;

describe('KPIGrid — rendering', () => {
  it('renders the KPI grid container', () => {
    render(
      <KPIGrid
        findings={defaultFindings}
        escalations={defaultEscalations}
        exceptions={defaultExceptions}
      />,
    );
    expect(screen.getByTestId('security-kpi-grid')).toBeInTheDocument();
  });

  it('renders all four KPI cards', () => {
    render(
      <KPIGrid
        findings={defaultFindings}
        escalations={defaultEscalations}
        exceptions={defaultExceptions}
      />,
    );
    expect(screen.getByTestId('kpi-critical-count')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-high-count')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-blocked-releases')).toBeInTheDocument();
    expect(screen.getByTestId('kpi-pending-exceptions')).toBeInTheDocument();
  });

  it('displays correct labels', () => {
    render(
      <KPIGrid
        findings={defaultFindings}
        escalations={defaultEscalations}
        exceptions={defaultExceptions}
      />,
    );
    expect(screen.getByText('Critical Findings')).toBeInTheDocument();
    expect(screen.getByText('High Findings')).toBeInTheDocument();
    expect(screen.getByText('Blocked Releases')).toBeInTheDocument();
    expect(screen.getByText('Pending Exceptions')).toBeInTheDocument();
  });
});

describe('KPIGrid — values', () => {
  it('shows correct critical count from findings', () => {
    // 2 critical findings in the fixture (both open)
    render(
      <KPIGrid
        findings={defaultFindings}
        escalations={[]}
        exceptions={[]}
      />,
    );
    expect(screen.getByTestId('kpi-critical-count')).toHaveTextContent('2');
  });

  it('shows correct high count from findings', () => {
    // 2 high findings in the fixture (1 open, 1 in_progress)
    render(
      <KPIGrid
        findings={defaultFindings}
        escalations={[]}
        exceptions={[]}
      />,
    );
    expect(screen.getByTestId('kpi-high-count')).toHaveTextContent('2');
  });

  it('shows zero critical when no critical findings', () => {
    render(
      <KPIGrid
        findings={[]}
        escalations={[]}
        exceptions={[]}
      />,
    );
    expect(screen.getByTestId('kpi-critical-count')).toHaveTextContent('0');
  });

  it('shows pending exceptions count', () => {
    // 2 pending exceptions in the fixture
    render(
      <KPIGrid
        findings={[]}
        escalations={[]}
        exceptions={defaultExceptions}
      />,
    );
    expect(screen.getByTestId('kpi-pending-exceptions')).toHaveTextContent('2');
  });

  it('excludes resolved findings from counts', () => {
    render(
      <KPIGrid
        findings={[
          {
            id: 'resolved-crit',
            service_id: 'svc-001',
            service_name: 'test',
            dimension: 'security',
            severity: 'critical',
            title: 'Resolved finding',
            description: 'Already fixed.',
            status: 'resolved',
            created_at: '2026-08-01T00:00:00Z',
          },
        ]}
        escalations={[]}
        exceptions={[]}
      />,
    );
    expect(screen.getByTestId('kpi-critical-count')).toHaveTextContent('0');
  });

  it('shows loading placeholder when isLoading is true', () => {
    render(
      <KPIGrid
        findings={[]}
        escalations={[]}
        exceptions={[]}
        isLoading={true}
      />,
    );
    // All cards should show the loading placeholder
    const criticalCard = screen.getByTestId('kpi-critical-count');
    expect(criticalCard).toHaveTextContent('…');
  });
});
