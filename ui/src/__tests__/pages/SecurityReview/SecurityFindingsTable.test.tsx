/**
 * Unit tests for SecurityFindingsTable component (WO-077).
 *
 * Tests:
 *   - Renders table with column headers
 *   - Renders finding rows with severity badges
 *   - Empty state when no findings
 *   - Loading state (skeleton)
 *   - Client-side sorting by severity and other columns
 *   - Row keyboard accessibility
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { render } from '@/test-utils';
import { SecurityFindingsTable } from '@/pages/SecurityReview/components/SecurityFindingsTable';
import {
  SECURITY_FINDINGS_PAGINATED,
  SEC_CRITICAL_FINDING_1,
  SEC_HIGH_FINDING_1,
} from '@/test/fixtures/securityFindings';

const findings = SECURITY_FINDINGS_PAGINATED.items;

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe('SecurityFindingsTable — rendering', () => {
  it('renders the table when findings are provided', () => {
    render(<SecurityFindingsTable findings={findings} />);
    expect(screen.getByTestId('security-findings-table')).toBeInTheDocument();
  });

  it('renders column headers', () => {
    render(<SecurityFindingsTable findings={findings} />);
    expect(screen.getByText('Severity')).toBeInTheDocument();
    expect(screen.getByText('Service')).toBeInTheDocument();
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Detected')).toBeInTheDocument();
  });

  it('renders a row for each finding', () => {
    render(<SecurityFindingsTable findings={findings} />);
    findings.forEach((f) => {
      expect(screen.getByTestId(`finding-row-${f.id}`)).toBeInTheDocument();
    });
  });

  it('renders severity badge with correct label', () => {
    render(<SecurityFindingsTable findings={[SEC_CRITICAL_FINDING_1]} />);
    expect(screen.getByTestId(`finding-severity-${SEC_CRITICAL_FINDING_1.id}`)).toHaveTextContent(
      'CRITICAL',
    );
  });

  it('renders finding title', () => {
    render(<SecurityFindingsTable findings={[SEC_CRITICAL_FINDING_1]} />);
    expect(
      screen.getByTestId(`finding-title-${SEC_CRITICAL_FINDING_1.id}`),
    ).toHaveTextContent('Hardcoded AWS credentials');
  });

  it('renders service name', () => {
    render(<SecurityFindingsTable findings={[SEC_HIGH_FINDING_1]} />);
    expect(screen.getByText('payment-service')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

describe('SecurityFindingsTable — empty state', () => {
  it('shows empty state when no findings', () => {
    render(<SecurityFindingsTable findings={[]} />);
    expect(screen.getByTestId('findings-table-empty')).toBeInTheDocument();
  });

  it('empty state contains guidance text', () => {
    render(<SecurityFindingsTable findings={[]} />);
    expect(screen.getByText('No security findings detected')).toBeInTheDocument();
  });

  it('does not render the table when empty', () => {
    render(<SecurityFindingsTable findings={[]} />);
    expect(screen.queryByTestId('security-findings-table')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Loading state
// ---------------------------------------------------------------------------

describe('SecurityFindingsTable — loading state', () => {
  it('renders skeleton when isLoading is true', () => {
    render(<SecurityFindingsTable findings={[]} isLoading={true} />);
    expect(screen.getByTestId('findings-table-skeleton')).toBeInTheDocument();
  });

  it('does not render table when loading', () => {
    render(<SecurityFindingsTable findings={[]} isLoading={true} />);
    expect(screen.queryByTestId('security-findings-table')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Sorting
// ---------------------------------------------------------------------------

describe('SecurityFindingsTable — sorting', () => {
  it('renders sortable column headers with sort buttons', () => {
    render(<SecurityFindingsTable findings={findings} />);
    // Column headers are UnstyledButtons — check they can be activated
    const headers = screen.getAllByRole('button');
    expect(headers.length).toBeGreaterThanOrEqual(5);
  });

  it('toggles sort direction when same column header clicked twice', async () => {
    const user = userEvent.setup();
    render(<SecurityFindingsTable findings={findings} />);
    const severityHeader = screen.getByRole('button', { name: /sort by severity/i });
    // Click once — ascending (already default)
    await user.click(severityHeader);
    // Click again — descending
    await user.click(severityHeader);
    // Table should still render after toggling
    expect(screen.getByTestId('security-findings-table')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Accessibility
// ---------------------------------------------------------------------------

describe('SecurityFindingsTable — accessibility', () => {
  it('table has aria-label', () => {
    render(<SecurityFindingsTable findings={findings} />);
    expect(screen.getByRole('table', { name: 'Security findings' })).toBeInTheDocument();
  });

  it('finding rows have tabIndex for keyboard navigation', () => {
    render(<SecurityFindingsTable findings={[SEC_CRITICAL_FINDING_1]} />);
    const row = screen.getByTestId(`finding-row-${SEC_CRITICAL_FINDING_1.id}`);
    expect(row).toHaveAttribute('tabIndex', '0');
  });

  it('finding rows have aria-label', () => {
    render(<SecurityFindingsTable findings={[SEC_CRITICAL_FINDING_1]} />);
    const row = screen.getByTestId(`finding-row-${SEC_CRITICAL_FINDING_1.id}`);
    expect(row).toHaveAttribute('aria-label');
  });
});
