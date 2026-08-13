/**
 * Unit tests for ScoreBox component (WO-076).
 *
 * Covers:
 *   - Renders correct score value for health/risk/decision schemes
 *   - Color coding: health (green ≥70, amber 50-69, red <50)
 *   - Color coding: risk (green ≤30, amber 31-60, red >60)
 *   - Color coding: decision (APPROVE/CONDITIONAL_APPROVE/BLOCK/null)
 *   - Handles null score gracefully
 *   - Boundary conditions (Health=70, Risk=30)
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { render } from '@/test-utils';
import { ScoreBox } from '@/components/releases/ScoreBox';

describe('ScoreBox — health colorScheme', () => {
  it('renders the label and score', () => {
    render(<ScoreBox label="Health Score" score={85} colorScheme="health" />);
    expect(screen.getByText('Health Score')).toBeInTheDocument();
    expect(screen.getByTestId('score-box-value')).toHaveTextContent('85');
  });

  it('uses success color for health score >= 70', () => {
    render(<ScoreBox label="Health Score" score={85} colorScheme="health" />);
    const card = screen.getByTestId('score-box-health-score');
    expect(card).toHaveAttribute('data-color', 'success');
  });

  it('uses warning color for health score 50-69', () => {
    render(<ScoreBox label="Health Score" score={60} colorScheme="health" />);
    const card = screen.getByTestId('score-box-health-score');
    expect(card).toHaveAttribute('data-color', 'warning');
  });

  it('uses danger color for health score < 50', () => {
    render(<ScoreBox label="Health Score" score={40} colorScheme="health" />);
    const card = screen.getByTestId('score-box-health-score');
    expect(card).toHaveAttribute('data-color', 'danger');
  });

  it('treats health score exactly 70 as success (boundary)', () => {
    render(<ScoreBox label="Health Score" score={70} colorScheme="health" />);
    const card = screen.getByTestId('score-box-health-score');
    expect(card).toHaveAttribute('data-color', 'success');
  });

  it('treats health score exactly 50 as warning (boundary)', () => {
    render(<ScoreBox label="Health Score" score={50} colorScheme="health" />);
    const card = screen.getByTestId('score-box-health-score');
    expect(card).toHaveAttribute('data-color', 'warning');
  });

  it('shows "Score unavailable" when score is null', () => {
    render(<ScoreBox label="Health Score" score={null} colorScheme="health" />);
    expect(screen.getByTestId('score-box-value')).toHaveTextContent('Score unavailable');
  });

  it('renders optional subtitle', () => {
    render(
      <ScoreBox
        label="Health Score"
        score={80}
        colorScheme="health"
        subtitle="Higher is better"
      />,
    );
    expect(screen.getByText('Higher is better')).toBeInTheDocument();
  });
});

describe('ScoreBox — risk colorScheme', () => {
  it('uses success color for risk score <= 30', () => {
    render(<ScoreBox label="Risk Score" score={20} colorScheme="risk" />);
    const card = screen.getByTestId('score-box-risk-score');
    expect(card).toHaveAttribute('data-color', 'success');
  });

  it('uses warning color for risk score 31-60', () => {
    render(<ScoreBox label="Risk Score" score={45} colorScheme="risk" />);
    const card = screen.getByTestId('score-box-risk-score');
    expect(card).toHaveAttribute('data-color', 'warning');
  });

  it('uses danger color for risk score > 60', () => {
    render(<ScoreBox label="Risk Score" score={75} colorScheme="risk" />);
    const card = screen.getByTestId('score-box-risk-score');
    expect(card).toHaveAttribute('data-color', 'danger');
  });

  it('treats risk score exactly 30 as success (boundary)', () => {
    render(<ScoreBox label="Risk Score" score={30} colorScheme="risk" />);
    const card = screen.getByTestId('score-box-risk-score');
    expect(card).toHaveAttribute('data-color', 'success');
  });

  it('treats risk score exactly 31 as warning (boundary)', () => {
    render(<ScoreBox label="Risk Score" score={31} colorScheme="risk" />);
    const card = screen.getByTestId('score-box-risk-score');
    expect(card).toHaveAttribute('data-color', 'warning');
  });

  it('treats risk score exactly 60 as warning', () => {
    render(<ScoreBox label="Risk Score" score={60} colorScheme="risk" />);
    const card = screen.getByTestId('score-box-risk-score');
    expect(card).toHaveAttribute('data-color', 'warning');
  });

  it('shows "Score unavailable" when score is null', () => {
    render(<ScoreBox label="Risk Score" score={null} colorScheme="risk" />);
    expect(screen.getByTestId('score-box-value')).toHaveTextContent('Score unavailable');
  });
});

describe('ScoreBox — decision colorScheme', () => {
  it('shows APPROVE text with success color', () => {
    render(
      <ScoreBox
        label="Combined Decision"
        score={null}
        colorScheme="decision"
        decision="APPROVE"
      />,
    );
    const card = screen.getByTestId('score-box-combined-decision');
    expect(card).toHaveAttribute('data-color', 'success');
    expect(screen.getByTestId('score-box-value')).toHaveTextContent('APPROVE');
  });

  it('shows CONDITIONAL text with warning color for CONDITIONAL_APPROVE', () => {
    render(
      <ScoreBox
        label="Combined Decision"
        score={null}
        colorScheme="decision"
        decision="CONDITIONAL_APPROVE"
      />,
    );
    const card = screen.getByTestId('score-box-combined-decision');
    expect(card).toHaveAttribute('data-color', 'warning');
    expect(screen.getByTestId('score-box-value')).toHaveTextContent('CONDITIONAL');
  });

  it('shows BLOCK text with danger color', () => {
    render(
      <ScoreBox
        label="Combined Decision"
        score={null}
        colorScheme="decision"
        decision="BLOCK"
      />,
    );
    const card = screen.getByTestId('score-box-combined-decision');
    expect(card).toHaveAttribute('data-color', 'danger');
    expect(screen.getByTestId('score-box-value')).toHaveTextContent('BLOCK');
  });

  it('shows "Pending Review" with neutral color when decision is null', () => {
    render(
      <ScoreBox
        label="Combined Decision"
        score={null}
        colorScheme="decision"
        decision={null}
      />,
    );
    const card = screen.getByTestId('score-box-combined-decision');
    expect(card).toHaveAttribute('data-color', 'neutral');
    expect(screen.getByTestId('score-box-value')).toHaveTextContent('Pending Review');
  });

  it('is case-insensitive for decision string', () => {
    render(
      <ScoreBox
        label="Combined Decision"
        score={null}
        colorScheme="decision"
        decision="approve"
      />,
    );
    const card = screen.getByTestId('score-box-combined-decision');
    expect(card).toHaveAttribute('data-color', 'success');
  });
});
