/**
 * Unit tests for ServiceHealthCard / HealthCheckRow (WO-081).
 *
 * Covers up/down/degraded/unknown status rendering and icon display.
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { render } from '@/test-utils';
import {
  ServiceHealthCard,
  HealthCheckRow,
  type ServiceHealthRow,
} from '@/components/platform/ServiceHealthCard';

const makeRow = (overrides: Partial<ServiceHealthRow> = {}): ServiceHealthRow => ({
  name: 'Backend API',
  status: 'up',
  lastChecked: '10:00:00',
  ...overrides,
});

describe('HealthCheckRow', () => {
  it('shows "Operational" badge for up status', () => {
    render(<HealthCheckRow {...makeRow({ status: 'up' })} />);
    expect(screen.getByTestId('service-status-backend-api')).toHaveTextContent('Operational');
  });

  it('shows "Degraded" badge for degraded status', () => {
    render(<HealthCheckRow {...makeRow({ status: 'degraded' })} />);
    expect(screen.getByTestId('service-status-backend-api')).toHaveTextContent('Degraded');
  });

  it('shows "Down" badge for down status', () => {
    render(<HealthCheckRow {...makeRow({ status: 'down' })} />);
    expect(screen.getByTestId('service-status-backend-api')).toHaveTextContent('Down');
  });

  it('shows "Unknown" badge for unknown status', () => {
    render(<HealthCheckRow {...makeRow({ status: 'unknown' })} />);
    expect(screen.getByTestId('service-status-backend-api')).toHaveTextContent('Unknown');
  });

  it('renders the service name', () => {
    render(<HealthCheckRow {...makeRow({ name: 'LLM Provider' })} />);
    expect(screen.getByText('LLM Provider')).toBeInTheDocument();
  });

  it('renders the lastChecked timestamp', () => {
    render(<HealthCheckRow {...makeRow({ lastChecked: '09:55:00' })} />);
    expect(screen.getByText('09:55:00')).toBeInTheDocument();
  });

  it('renders optional detail when provided', () => {
    render(<HealthCheckRow {...makeRow({ detail: 'v1.0.0' })} />);
    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
  });

  it('does not render detail element when omitted', () => {
    render(<HealthCheckRow {...makeRow({ detail: undefined })} />);
    // No crash and no spurious text
    expect(screen.queryByText('v1.0.0')).not.toBeInTheDocument();
  });
});

describe('ServiceHealthCard', () => {
  const rows: ServiceHealthRow[] = [
    makeRow({ name: 'Backend API',    status: 'up'       }),
    makeRow({ name: 'Database',       status: 'up'       }),
    makeRow({ name: 'Frontend',       status: 'up'       }),
    makeRow({ name: 'LLM Provider',   status: 'degraded' }),
    makeRow({ name: 'CI/CD Pipeline', status: 'unknown'  }),
  ];

  it('renders all five service rows', () => {
    render(<ServiceHealthCard rows={rows} lastUpdated="10:00:00" />);
    expect(screen.getByText('Backend API')).toBeInTheDocument();
    expect(screen.getByText('Database')).toBeInTheDocument();
    expect(screen.getByText('Frontend')).toBeInTheDocument();
    expect(screen.getByText('LLM Provider')).toBeInTheDocument();
    expect(screen.getByText('CI/CD Pipeline')).toBeInTheDocument();
  });

  it('renders the "Last checked" timestamp when provided', () => {
    render(<ServiceHealthCard rows={rows} lastUpdated="09:59:01" />);
    expect(screen.getByText(/Last checked: 09:59:01/)).toBeInTheDocument();
  });

  it('does not render last-checked text when null', () => {
    render(<ServiceHealthCard rows={rows} lastUpdated={null} />);
    expect(screen.queryByText(/Last checked/)).not.toBeInTheDocument();
  });

  it('renders the service health card container', () => {
    render(<ServiceHealthCard rows={rows} lastUpdated={null} />);
    expect(screen.getByTestId('service-health-card')).toBeInTheDocument();
  });
});
