/**
 * Unit tests for RiskFactorsCard component (WO-076).
 *
 * Covers:
 *   - Renders 4 risk factor rows with correct names
 *   - Displays values from change_analysis correctly
 *   - Shows 'Data unavailable' for missing dimensions
 *   - Shows 'Data unavailable' for all factors when changeAnalysis is null
 *   - Severity badges reflect dimension severity
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { render } from '@/test-utils';
import { RiskFactorsCard } from '@/components/releases/RiskFactorsCard';

const FULL_CHANGE_ANALYSIS = {
  code_complexity: { score: 28, delta: 5, severity: 'medium' },
  test_coverage_delta: { current: 71, previous: 80, delta: -9, severity: 'high' },
  dependency_changes: { added: 3, removed: 0, updated: 5, severity: 'medium' },
  security_implications: { count: 1, max_severity: 'medium', severity: 'medium' },
};

describe('RiskFactorsCard — full change_analysis', () => {
  it('renders the card with title', () => {
    render(<RiskFactorsCard changeAnalysis={FULL_CHANGE_ANALYSIS} />);
    expect(screen.getByTestId('risk-factors-card')).toBeInTheDocument();
    expect(screen.getByText('Risk Factors')).toBeInTheDocument();
  });

  it('renders all 4 risk factor rows', () => {
    render(<RiskFactorsCard changeAnalysis={FULL_CHANGE_ANALYSIS} />);
    expect(screen.getByTestId('risk-factor-code-complexity')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-test-coverage')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-dependency-changes')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-security-implications')).toBeInTheDocument();
  });

  it('displays correct factor names', () => {
    render(<RiskFactorsCard changeAnalysis={FULL_CHANGE_ANALYSIS} />);
    expect(screen.getByText('Code Complexity')).toBeInTheDocument();
    expect(screen.getByText('Test Coverage Delta')).toBeInTheDocument();
    expect(screen.getByText('Dependency Changes')).toBeInTheDocument();
    expect(screen.getByText('Security Implications')).toBeInTheDocument();
  });

  it('displays code_complexity score and delta', () => {
    render(<RiskFactorsCard changeAnalysis={FULL_CHANGE_ANALYSIS} />);
    const row = screen.getByTestId('risk-factor-code-complexity');
    expect(row.textContent).toContain('28');
    expect(row.textContent).toContain('+5');
  });

  it('displays test_coverage_delta with delta and current', () => {
    render(<RiskFactorsCard changeAnalysis={FULL_CHANGE_ANALYSIS} />);
    const row = screen.getByTestId('risk-factor-test-coverage');
    expect(row.textContent).toContain('-9%');
    expect(row.textContent).toContain('71%');
  });

  it('displays dependency_changes counts', () => {
    render(<RiskFactorsCard changeAnalysis={FULL_CHANGE_ANALYSIS} />);
    const row = screen.getByTestId('risk-factor-dependency-changes');
    expect(row.textContent).toContain('+3');
    expect(row.textContent).toContain('5');
  });

  it('displays security_implications count and max severity', () => {
    render(<RiskFactorsCard changeAnalysis={FULL_CHANGE_ANALYSIS} />);
    const row = screen.getByTestId('risk-factor-security-implications');
    expect(row.textContent).toContain('1 finding');
    expect(row.textContent).toContain('medium');
  });
});

describe('RiskFactorsCard — null change_analysis', () => {
  it('renders 4 rows all showing "Data unavailable"', () => {
    render(<RiskFactorsCard changeAnalysis={null} />);
    const rows = [
      screen.getByTestId('risk-factor-code-complexity'),
      screen.getByTestId('risk-factor-test-coverage'),
      screen.getByTestId('risk-factor-dependency-changes'),
      screen.getByTestId('risk-factor-security-implications'),
    ];
    rows.forEach((row) => {
      expect(row.textContent).toContain('Data unavailable');
    });
  });
});

describe('RiskFactorsCard — partial change_analysis', () => {
  const PARTIAL = {
    code_complexity: { score: 20, delta: 0, severity: 'low' },
    // test_coverage_delta: missing
    // dependency_changes: missing
    // security_implications: missing
  };

  it('shows value for present dimension and "Data unavailable" for absent ones', () => {
    render(<RiskFactorsCard changeAnalysis={PARTIAL} />);
    // code_complexity should have data
    const cc = screen.getByTestId('risk-factor-code-complexity');
    expect(cc.textContent).toContain('20');
    // missing dimensions show fallback
    expect(screen.getByTestId('risk-factor-test-coverage').textContent).toContain('Data unavailable');
    expect(screen.getByTestId('risk-factor-dependency-changes').textContent).toContain('Data unavailable');
    expect(screen.getByTestId('risk-factor-security-implications').textContent).toContain('Data unavailable');
  });
});

describe('RiskFactorsCard — severity badges', () => {
  it('renders severity badges for each factor', () => {
    render(<RiskFactorsCard changeAnalysis={FULL_CHANGE_ANALYSIS} />);
    expect(screen.getByTestId('risk-factor-code-complexity-badge')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-test-coverage-badge')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-dependency-changes-badge')).toBeInTheDocument();
    expect(screen.getByTestId('risk-factor-security-implications-badge')).toBeInTheDocument();
  });

  it('shows n/a badge when severity is missing', () => {
    render(<RiskFactorsCard changeAnalysis={null} />);
    const badges = screen.getAllByTestId(/risk-factor-.*-badge/);
    badges.forEach((badge) => {
      expect(badge.textContent).toContain('n/a');
    });
  });
});
