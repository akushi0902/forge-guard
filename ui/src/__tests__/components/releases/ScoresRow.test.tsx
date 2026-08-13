/**
 * Unit tests for ScoresRow component (WO-076).
 *
 * Covers:
 *   - Renders 3 ScoreBox cards in a row
 *   - Passes correct values to each ScoreBox
 *   - APPROVE scores: health green, risk green, decision success
 *   - CONDITIONAL scores: health/risk amber, decision warning
 *   - BLOCK scores: health/risk red, decision danger
 *   - null scores show 'Score unavailable'
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { render } from '@/test-utils';
import { ScoresRow } from '@/components/releases/ScoresRow';

describe('ScoresRow', () => {
  it('renders 3 score boxes', () => {
    render(<ScoresRow healthScore={85} riskScore={20} decision="APPROVE" />);
    expect(screen.getByTestId('scores-row')).toBeInTheDocument();
    expect(screen.getByTestId('score-box-health-score')).toBeInTheDocument();
    expect(screen.getByTestId('score-box-risk-score')).toBeInTheDocument();
    expect(screen.getByTestId('score-box-combined-decision')).toBeInTheDocument();
  });

  it('APPROVE scenario: health 85 green, risk 20 green, decision success', () => {
    render(<ScoresRow healthScore={85} riskScore={20} decision="APPROVE" />);

    expect(screen.getByTestId('score-box-health-score')).toHaveAttribute('data-color', 'success');
    expect(screen.getByTestId('score-box-risk-score')).toHaveAttribute('data-color', 'success');
    expect(screen.getByTestId('score-box-combined-decision')).toHaveAttribute('data-color', 'success');
  });

  it('APPROVE scenario: displays correct scores', () => {
    render(<ScoresRow healthScore={85} riskScore={20} decision="APPROVE" />);
    const values = screen.getAllByTestId('score-box-value');
    const texts = values.map((el) => el.textContent);
    expect(texts).toContain('85');
    expect(texts).toContain('20');
    expect(texts).toContain('APPROVE');
  });

  it('CONDITIONAL_APPROVE scenario: health 60 warning, risk 45 warning, decision warning', () => {
    render(<ScoresRow healthScore={60} riskScore={45} decision="CONDITIONAL_APPROVE" />);

    expect(screen.getByTestId('score-box-health-score')).toHaveAttribute('data-color', 'warning');
    expect(screen.getByTestId('score-box-risk-score')).toHaveAttribute('data-color', 'warning');
    expect(screen.getByTestId('score-box-combined-decision')).toHaveAttribute('data-color', 'warning');
  });

  it('BLOCK scenario: health 40 danger, risk 75 danger, decision danger', () => {
    render(<ScoresRow healthScore={40} riskScore={75} decision="BLOCK" />);

    expect(screen.getByTestId('score-box-health-score')).toHaveAttribute('data-color', 'danger');
    expect(screen.getByTestId('score-box-risk-score')).toHaveAttribute('data-color', 'danger');
    expect(screen.getByTestId('score-box-combined-decision')).toHaveAttribute('data-color', 'danger');
  });

  it('null scores show "Score unavailable"', () => {
    render(<ScoresRow healthScore={null} riskScore={null} decision={null} />);
    const values = screen.getAllByTestId('score-box-value');
    const texts = values.map((el) => el.textContent);
    // Health and risk boxes show 'Score unavailable', decision shows 'Pending Review'
    expect(texts.filter((t) => t === 'Score unavailable').length).toBe(2);
    expect(texts).toContain('Pending Review');
  });

  it('null decision shows "Pending Review" in neutral color', () => {
    render(<ScoresRow healthScore={70} riskScore={30} decision={null} />);
    const decisionBox = screen.getByTestId('score-box-combined-decision');
    expect(decisionBox).toHaveAttribute('data-color', 'neutral');
    const values = screen.getAllByTestId('score-box-value');
    const decisionValue = values.find((el) => el.textContent === 'Pending Review');
    expect(decisionValue).toBeInTheDocument();
  });

  it('renders labels for all three boxes', () => {
    render(<ScoresRow healthScore={80} riskScore={25} decision="APPROVE" />);
    expect(screen.getByText('Health Score')).toBeInTheDocument();
    expect(screen.getByText('Risk Score')).toBeInTheDocument();
    expect(screen.getByText('Combined Decision')).toBeInTheDocument();
  });
});
