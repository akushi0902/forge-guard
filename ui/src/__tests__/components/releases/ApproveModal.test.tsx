/**
 * Unit tests for ApproveModal component (WO-075).
 */

import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { render } from '@/test-utils';
import { ApproveModal } from '@/components/releases/ApproveModal';

const DEFAULT_PROPS = {
  opened: true,
  onClose: vi.fn(),
  onConfirm: vi.fn(),
  riskScore: 25,
  findingCounts: { critical: 0, high: 1, medium: 2, low: 3 },
  rationale: 'All critical issues resolved. Safe to release.',
};

describe('ApproveModal', () => {
  it('renders with title "Confirm Release Approval"', () => {
    render(<ApproveModal {...DEFAULT_PROPS} />);
    expect(screen.getByText('Confirm Release Approval')).toBeInTheDocument();
  });

  it('displays the risk score', () => {
    render(<ApproveModal {...DEFAULT_PROPS} />);
    expect(screen.getByTestId('approve-modal-risk-score')).toBeInTheDocument();
    expect(screen.getByTestId('approve-modal-risk-score')).toHaveTextContent('25');
  });

  it('shows finding count badges', () => {
    render(<ApproveModal {...DEFAULT_PROPS} />);
    expect(screen.getByText('1 High')).toBeInTheDocument();
    expect(screen.getByText('2 Medium')).toBeInTheDocument();
    expect(screen.getByText('3 Low')).toBeInTheDocument();
  });

  it('displays rationale preview', () => {
    render(<ApproveModal {...DEFAULT_PROPS} />);
    expect(screen.getByTestId('approve-modal-rationale')).toBeInTheDocument();
    expect(screen.getByTestId('approve-modal-rationale')).toHaveTextContent(
      'All critical issues resolved. Safe to release.',
    );
  });

  it('calls onConfirm when Confirm Approval button is clicked', async () => {
    const onConfirm = vi.fn();
    render(<ApproveModal {...DEFAULT_PROPS} onConfirm={onConfirm} />);
    await userEvent.click(screen.getByTestId('approve-modal-confirm'));
    expect(onConfirm).toHaveBeenCalled();
  });

  it('calls onClose when Cancel button is clicked', async () => {
    const onClose = vi.fn();
    render(<ApproveModal {...DEFAULT_PROPS} onClose={onClose} />);
    await userEvent.click(screen.getByTestId('approve-modal-cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('shows "No findings" when all counts are zero', () => {
    render(
      <ApproveModal
        {...DEFAULT_PROPS}
        findingCounts={{ critical: 0, high: 0, medium: 0, low: 0 }}
      />,
    );
    expect(screen.getByText('No findings')).toBeInTheDocument();
  });

  it('shows dash when risk score is null', () => {
    render(<ApproveModal {...DEFAULT_PROPS} riskScore={null} />);
    expect(screen.getByTestId('approve-modal-risk-score')).toHaveTextContent('—');
  });

  it('does not render when opened=false', () => {
    render(<ApproveModal {...DEFAULT_PROPS} opened={false} />);
    expect(screen.queryByTestId('approve-modal')).not.toBeInTheDocument();
  });

  it('shows loading state when confirmLoading=true', () => {
    render(<ApproveModal {...DEFAULT_PROPS} confirmLoading />);
    const confirmBtn = screen.getByTestId('approve-modal-confirm');
    // When loading, button should be disabled
    expect(confirmBtn).toBeDisabled();
  });
});
