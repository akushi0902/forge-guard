/**
 * Unit tests for AssessmentMetadata component (WO-075).
 */

import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { render } from '@/test-utils';
import { AssessmentMetadata } from '@/components/releases/AssessmentMetadata';

const BASE_PROPS = {
  id: 'rel-001',
  serviceId: 'svc-001',
  commitSha: 'abc123def456abc123def456abc123def456abc1',
  prReference: null,
  status: 'completed',
  createdAt: '2026-08-11T10:00:00Z',
  completedAt: '2026-08-11T10:05:00Z',
};

describe('AssessmentMetadata', () => {
  it('renders assessment details card', () => {
    render(<AssessmentMetadata {...BASE_PROPS} />);
    expect(screen.getByTestId('assessment-metadata')).toBeInTheDocument();
    expect(screen.getByText('Assessment Details')).toBeInTheDocument();
  });

  it('shows truncated commit SHA', () => {
    render(<AssessmentMetadata {...BASE_PROPS} />);
    const shaEl = screen.getByTestId('commit-sha');
    // Should show first 12 chars
    expect(shaEl.textContent).toBe('abc123def456');
  });

  it('renders copy SHA button', () => {
    render(<AssessmentMetadata {...BASE_PROPS} />);
    expect(screen.getByTestId('copy-sha-btn')).toBeInTheDocument();
  });

  it('renders PR reference as a link when it is a URL', () => {
    render(
      <AssessmentMetadata
        {...BASE_PROPS}
        prReference="https://github.com/acme/repo/pull/42"
      />,
    );
    expect(screen.getByTestId('pr-reference-link')).toBeInTheDocument();
    expect(screen.getByTestId('pr-reference-link')).toHaveAttribute(
      'href',
      'https://github.com/acme/repo/pull/42',
    );
  });

  it('renders PR reference as plain text when it is not a URL', () => {
    render(<AssessmentMetadata {...BASE_PROPS} prReference="PR-42" />);
    expect(screen.getByTestId('pr-reference-text')).toBeInTheDocument();
    expect(screen.queryByTestId('pr-reference-link')).not.toBeInTheDocument();
  });

  it('does not render PR reference row when prReference is null', () => {
    render(<AssessmentMetadata {...BASE_PROPS} prReference={null} />);
    expect(screen.queryByTestId('pr-reference-link')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pr-reference-text')).not.toBeInTheDocument();
  });

  it('shows service link', () => {
    render(<AssessmentMetadata {...BASE_PROPS} />);
    expect(screen.getByTestId('service-link')).toBeInTheDocument();
  });

  it('shows service name when provided', () => {
    render(<AssessmentMetadata {...BASE_PROPS} serviceName="payment-api" />);
    expect(screen.getByText('payment-api')).toBeInTheDocument();
  });

  it('shows completed at timestamp', () => {
    render(<AssessmentMetadata {...BASE_PROPS} />);
    expect(screen.getByTestId('completed-at')).toBeInTheDocument();
  });

  it('shows status badge', () => {
    render(<AssessmentMetadata {...BASE_PROPS} />);
    // Status should be visible
    expect(screen.getByText('completed')).toBeInTheDocument();
  });

  it('does not render completed-at row when completedAt is null', () => {
    render(<AssessmentMetadata {...BASE_PROPS} completedAt={null} />);
    expect(screen.queryByTestId('completed-at')).not.toBeInTheDocument();
  });
});
