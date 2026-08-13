/**
 * Unit tests for ThresholdInfoSection component (WO-076).
 *
 * Covers:
 *   - Renders the collapsible accordion
 *   - Shows 3 threshold rules when expanded
 *   - Each rule contains correct decision and threshold text
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { render } from '@/test-utils';
import { ThresholdInfoSection } from '@/components/releases/ThresholdInfoSection';

describe('ThresholdInfoSection', () => {
  it('renders the accordion', () => {
    render(<ThresholdInfoSection />);
    expect(screen.getByTestId('threshold-info-section')).toBeInTheDocument();
  });

  it('renders the header text', () => {
    render(<ThresholdInfoSection />);
    expect(screen.getByText(/Decision Threshold Rules/i)).toBeInTheDocument();
  });

  it('expands to show 3 threshold rules when clicked', async () => {
    render(<ThresholdInfoSection />);
    const trigger = screen.getByText(/Decision Threshold Rules/i);
    await userEvent.click(trigger);

    expect(screen.getByTestId('threshold-rules')).toBeInTheDocument();
    expect(screen.getByTestId('threshold-rule-approve')).toBeInTheDocument();
    expect(screen.getByTestId('threshold-rule-conditional')).toBeInTheDocument();
    expect(screen.getByTestId('threshold-rule-block')).toBeInTheDocument();
  });

  it('shows APPROVE rule text with correct thresholds', async () => {
    render(<ThresholdInfoSection />);
    await userEvent.click(screen.getByText(/Decision Threshold Rules/i));

    const approveRule = screen.getByTestId('threshold-rule-approve');
    expect(approveRule.textContent).toContain('APPROVE');
    expect(approveRule.textContent).toContain('70');
    expect(approveRule.textContent).toContain('30');
  });

  it('shows CONDITIONAL rule text with correct thresholds', async () => {
    render(<ThresholdInfoSection />);
    await userEvent.click(screen.getByText(/Decision Threshold Rules/i));

    const conditionalRule = screen.getByTestId('threshold-rule-conditional');
    expect(conditionalRule.textContent).toContain('CONDITIONAL');
    expect(conditionalRule.textContent).toContain('50');
    expect(conditionalRule.textContent).toContain('60');
  });

  it('shows BLOCK rule text', async () => {
    render(<ThresholdInfoSection />);
    await userEvent.click(screen.getByText(/Decision Threshold Rules/i));

    const blockRule = screen.getByTestId('threshold-rule-block');
    expect(blockRule.textContent).toContain('BLOCK');
    expect(blockRule.textContent).toContain('Otherwise');
  });
});
