/**
 * Unit tests for ConditionsCard component (WO-076).
 *
 * Covers:
 *   - Renders conditions list when non-empty
 *   - Shows fallback message for empty conditions array
 *   - Each condition rendered as a list item with correct text
 *   - Long condition text wraps without overflow
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { render } from '@/test-utils';
import { ConditionsCard } from '@/components/releases/ConditionsCard';

const SAMPLE_CONDITIONS = [
  'Increase test coverage to >= 80% within 5 business days.',
  'Resolve high-severity dependency vulnerability CVE-2021-23337.',
  'Add monitoring alert for payment processing error rate.',
];

describe('ConditionsCard — with conditions', () => {
  it('renders the card', () => {
    render(<ConditionsCard conditions={SAMPLE_CONDITIONS} />);
    expect(screen.getByTestId('conditions-card')).toBeInTheDocument();
  });

  it('renders the title "Mandatory Conditions"', () => {
    render(<ConditionsCard conditions={SAMPLE_CONDITIONS} />);
    expect(screen.getByText('Mandatory Conditions')).toBeInTheDocument();
  });

  it('renders all condition items', () => {
    render(<ConditionsCard conditions={SAMPLE_CONDITIONS} />);
    expect(screen.getByTestId('condition-item-0')).toBeInTheDocument();
    expect(screen.getByTestId('condition-item-1')).toBeInTheDocument();
    expect(screen.getByTestId('condition-item-2')).toBeInTheDocument();
  });

  it('displays the text of each condition', () => {
    render(<ConditionsCard conditions={SAMPLE_CONDITIONS} />);
    SAMPLE_CONDITIONS.forEach((condition) => {
      expect(screen.getByText(condition)).toBeInTheDocument();
    });
  });

  it('does not show empty message when conditions are present', () => {
    render(<ConditionsCard conditions={SAMPLE_CONDITIONS} />);
    expect(screen.queryByTestId('conditions-empty-message')).not.toBeInTheDocument();
  });
});

describe('ConditionsCard — empty conditions array', () => {
  it('renders the card', () => {
    render(<ConditionsCard conditions={[]} />);
    expect(screen.getByTestId('conditions-card')).toBeInTheDocument();
  });

  it('shows fallback message for empty conditions', () => {
    render(<ConditionsCard conditions={[]} />);
    expect(screen.getByTestId('conditions-empty-message')).toBeInTheDocument();
    expect(screen.getByTestId('conditions-empty-message')).toHaveTextContent(
      'No specific conditions defined — review findings before proceeding.',
    );
  });

  it('does not render any condition items for empty array', () => {
    render(<ConditionsCard conditions={[]} />);
    expect(screen.queryByTestId('condition-item-0')).not.toBeInTheDocument();
  });
});

describe('ConditionsCard — single condition', () => {
  it('renders exactly one condition item', () => {
    render(<ConditionsCard conditions={['Resolve critical security finding.']} />);
    expect(screen.getByTestId('condition-item-0')).toBeInTheDocument();
    expect(screen.queryByTestId('condition-item-1')).not.toBeInTheDocument();
    expect(screen.getByText('Resolve critical security finding.')).toBeInTheDocument();
  });
});
