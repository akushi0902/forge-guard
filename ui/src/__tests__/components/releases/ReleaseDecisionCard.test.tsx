/**
 * Unit tests for ReleaseDecisionCard component (WO-075).
 *
 * Tests:
 *   - Button visibility per permission set
 *   - Rationale validation (disabled until ≥10 chars)
 *   - Read-only state for users without permissions
 */

import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { render } from '@/test-utils';
import { ReleaseDecisionCard } from '@/components/releases/ReleaseDecisionCard';

const TECH_LEAD_PERMISSIONS    = ['service.view', 'release.approve', 'release.block'];
const DEVELOPER_PERMISSIONS    = ['service.view', 'assessment.request'];
const APPROVE_ONLY_PERMISSIONS = ['service.view', 'release.approve'];
const BLOCK_ONLY_PERMISSIONS   = ['service.view', 'release.block'];

describe('ReleaseDecisionCard — button visibility', () => {
  it('shows both Approve and Block buttons for Tech Lead', () => {
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    expect(screen.getByTestId('approve-btn')).toBeInTheDocument();
    expect(screen.getByTestId('block-btn')).toBeInTheDocument();
  });

  it('shows only Approve button for approve-only permission', () => {
    render(
      <ReleaseDecisionCard
        permissions={APPROVE_ONLY_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    expect(screen.getByTestId('approve-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('block-btn')).not.toBeInTheDocument();
  });

  it('shows only Block button for block-only permission', () => {
    render(
      <ReleaseDecisionCard
        permissions={BLOCK_ONLY_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('approve-btn')).not.toBeInTheDocument();
    expect(screen.getByTestId('block-btn')).toBeInTheDocument();
  });

  it('shows read-only message for users without decision permissions', () => {
    render(
      <ReleaseDecisionCard
        permissions={DEVELOPER_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    expect(screen.getByTestId('no-permission-message')).toBeInTheDocument();
    expect(screen.getByText(/you do not have permission to make release decisions/i)).toBeInTheDocument();
    expect(screen.queryByTestId('approve-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('block-btn')).not.toBeInTheDocument();
  });
});

describe('ReleaseDecisionCard — rationale validation', () => {
  it('buttons are disabled with empty rationale', () => {
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    expect(screen.getByTestId('approve-btn')).toBeDisabled();
    expect(screen.getByTestId('block-btn')).toBeDisabled();
  });

  it('buttons are disabled with rationale shorter than 10 chars', async () => {
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    await userEvent.type(screen.getByTestId('rationale-textarea'), 'too short');
    expect(screen.getByTestId('approve-btn')).toBeDisabled();
    expect(screen.getByTestId('block-btn')).toBeDisabled();
  });

  it('buttons are enabled with rationale of 10+ characters', async () => {
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    await userEvent.type(screen.getByTestId('rationale-textarea'), 'Long enough rationale text here');
    expect(screen.getByTestId('approve-btn')).not.toBeDisabled();
    expect(screen.getByTestId('block-btn')).not.toBeDisabled();
  });

  it('shows validation error when rationale is too short', async () => {
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    await userEvent.type(screen.getByTestId('rationale-textarea'), 'short');
    await waitFor(() => {
      expect(screen.getByText(/rationale must be at least 10 characters/i)).toBeInTheDocument();
    });
  });

  it('shows character counter', () => {
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
      />,
    );
    // Initial counter shows 0 / 2000
    expect(screen.getAllByText(/0 \/ 2000/i).length).toBeGreaterThan(0);
  });
});

describe('ReleaseDecisionCard — callbacks', () => {
  it('calls onApprove with rationale and comment when Approve is clicked', async () => {
    const onApprove = vi.fn();
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={onApprove}
        onBlock={vi.fn()}
      />,
    );
    await userEvent.type(screen.getByTestId('rationale-textarea'), 'Detailed approval rationale here');
    await userEvent.type(screen.getByTestId('comment-textarea'), 'Optional comment');
    await userEvent.click(screen.getByTestId('approve-btn'));
    expect(onApprove).toHaveBeenCalledWith('Detailed approval rationale here', 'Optional comment');
  });

  it('calls onBlock with rationale when Block is clicked', async () => {
    const onBlock = vi.fn();
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={onBlock}
      />,
    );
    await userEvent.type(screen.getByTestId('rationale-textarea'), 'Blocking due to critical issues');
    await userEvent.click(screen.getByTestId('block-btn'));
    expect(onBlock).toHaveBeenCalledWith('Blocking due to critical issues', '');
  });

  it('buttons are disabled when isSubmitting=true', () => {
    render(
      <ReleaseDecisionCard
        permissions={TECH_LEAD_PERMISSIONS}
        onApprove={vi.fn()}
        onBlock={vi.fn()}
        isSubmitting
      />,
    );
    // Buttons should be disabled
    expect(screen.getByTestId('approve-btn')).toBeDisabled();
    expect(screen.getByTestId('block-btn')).toBeDisabled();
  });
});
