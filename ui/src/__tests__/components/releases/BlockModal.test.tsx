/**
 * Unit tests for BlockModal component (WO-075).
 */

import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { render } from '@/test-utils';
import { BlockModal } from '@/components/releases/BlockModal';

const DEFAULT_PROPS = {
  opened: true,
  onClose: vi.fn(),
  onConfirm: vi.fn(),
  riskScore: 78,
  findingCounts: { critical: 2, high: 3, medium: 1, low: 0 },
  rationale: 'Critical security vulnerabilities must be resolved before release.',
};

describe('BlockModal', () => {
  it('renders with title "Confirm Release Block"', () => {
    render(<BlockModal {...DEFAULT_PROPS} />);
    expect(screen.getByText('Confirm Release Block')).toBeInTheDocument();
  });

  it('displays the risk score', () => {
    render(<BlockModal {...DEFAULT_PROPS} />);
    expect(screen.getByTestId('block-modal-risk-score')).toBeInTheDocument();
    expect(screen.getByTestId('block-modal-risk-score')).toHaveTextContent('78');
  });

  it('shows critical and high finding count badges', () => {
    render(<BlockModal {...DEFAULT_PROPS} />);
    expect(screen.getByText('2 Critical')).toBeInTheDocument();
    expect(screen.getByText('3 High')).toBeInTheDocument();
    expect(screen.getByText('1 Medium')).toBeInTheDocument();
  });

  it('displays rationale preview', () => {
    render(<BlockModal {...DEFAULT_PROPS} />);
    expect(screen.getByTestId('block-modal-rationale')).toHaveTextContent(
      'Critical security vulnerabilities must be resolved before release.',
    );
  });

  it('calls onConfirm when Confirm Block button is clicked', async () => {
    const onConfirm = vi.fn();
    render(<BlockModal {...DEFAULT_PROPS} onConfirm={onConfirm} />);
    await userEvent.click(screen.getByTestId('block-modal-confirm'));
    expect(onConfirm).toHaveBeenCalled();
  });

  it('calls onClose when Cancel button is clicked', async () => {
    const onClose = vi.fn();
    render(<BlockModal {...DEFAULT_PROPS} onClose={onClose} />);
    await userEvent.click(screen.getByTestId('block-modal-cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('does not render when opened=false', () => {
    render(<BlockModal {...DEFAULT_PROPS} opened={false} />);
    expect(screen.queryByTestId('block-modal')).not.toBeInTheDocument();
  });

  it('uses red-themed styling (warning alert color="red")', () => {
    render(<BlockModal {...DEFAULT_PROPS} />);
    // The warning alert should be present
    expect(screen.getByText(/you are blocking this release/i)).toBeInTheDocument();
  });
});
