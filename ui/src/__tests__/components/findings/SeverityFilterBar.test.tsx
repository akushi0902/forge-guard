import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '@/test-utils';
import { SeverityFilterBar } from '@/components/findings/SeverityFilterBar';

describe('SeverityFilterBar', () => {
  it('renders 5 filter buttons', () => {
    render(
      <SeverityFilterBar value="all" onFilterChange={vi.fn()} />,
    );
    expect(screen.getByTestId('severity-filter-all')).toBeInTheDocument();
    expect(screen.getByTestId('severity-filter-critical')).toBeInTheDocument();
    expect(screen.getByTestId('severity-filter-high')).toBeInTheDocument();
    expect(screen.getByTestId('severity-filter-medium')).toBeInTheDocument();
    expect(screen.getByTestId('severity-filter-low')).toBeInTheDocument();
  });

  it('renders button labels', () => {
    render(<SeverityFilterBar value="all" onFilterChange={vi.fn()} />);
    expect(screen.getByText('All')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
    expect(screen.getByText('Medium')).toBeInTheDocument();
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('shows count badges when severityCounts are provided', () => {
    render(
      <SeverityFilterBar
        value="all"
        onFilterChange={vi.fn()}
        severityCounts={{ critical: 3, high: 5, medium: 2, low: 1 }}
      />,
    );
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('shows total count on All button when severityCounts are provided', () => {
    render(
      <SeverityFilterBar
        value="all"
        onFilterChange={vi.fn()}
        severityCounts={{ critical: 3, high: 5, medium: 2, low: 1 }}
      />,
    );
    // Total = 11
    expect(screen.getByText('11')).toBeInTheDocument();
  });

  it('marks active filter with aria-pressed=true', () => {
    render(
      <SeverityFilterBar value="critical" onFilterChange={vi.fn()} />,
    );
    expect(screen.getByTestId('severity-filter-critical')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('marks inactive filters with aria-pressed=false', () => {
    render(
      <SeverityFilterBar value="critical" onFilterChange={vi.fn()} />,
    );
    expect(screen.getByTestId('severity-filter-all')).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(screen.getByTestId('severity-filter-high')).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('calls onFilterChange with correct severity when a button is clicked', async () => {
    const onFilterChange = vi.fn();
    render(
      <SeverityFilterBar value="all" onFilterChange={onFilterChange} />,
    );
    await userEvent.click(screen.getByTestId('severity-filter-critical'));
    expect(onFilterChange).toHaveBeenCalledWith('critical');
  });

  it('calls onFilterChange with "all" when All button is clicked', async () => {
    const onFilterChange = vi.fn();
    render(
      <SeverityFilterBar value="critical" onFilterChange={onFilterChange} />,
    );
    await userEvent.click(screen.getByTestId('severity-filter-all'));
    expect(onFilterChange).toHaveBeenCalledWith('all');
  });

  it('calls onFilterChange with "high", "medium", "low" for respective buttons', async () => {
    const onFilterChange = vi.fn();
    render(
      <SeverityFilterBar value="all" onFilterChange={onFilterChange} />,
    );
    await userEvent.click(screen.getByTestId('severity-filter-high'));
    expect(onFilterChange).toHaveBeenCalledWith('high');

    await userEvent.click(screen.getByTestId('severity-filter-medium'));
    expect(onFilterChange).toHaveBeenCalledWith('medium');

    await userEvent.click(screen.getByTestId('severity-filter-low'));
    expect(onFilterChange).toHaveBeenCalledWith('low');
  });

  it('renders with zero counts and all buttons still clickable', async () => {
    const onFilterChange = vi.fn();
    render(
      <SeverityFilterBar
        value="all"
        onFilterChange={onFilterChange}
        severityCounts={{ critical: 0, high: 0, medium: 0, low: 0 }}
      />,
    );
    await userEvent.click(screen.getByTestId('severity-filter-critical'));
    expect(onFilterChange).toHaveBeenCalledWith('critical');
  });
});
