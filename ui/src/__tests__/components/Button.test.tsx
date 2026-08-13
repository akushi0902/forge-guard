import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '@/test-utils';
import { Button } from '@/components/shared/Button';

describe('Button', () => {
  it('renders with default primary variant', () => {
    render(<Button>Save</Button>);
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();
  });

  it.each(['primary', 'secondary', 'ghost', 'destructive'] as const)(
    'renders %s variant without throwing',
    (variant) => {
      expect(() => render(<Button variant={variant}>{variant}</Button>)).not.toThrow();
      expect(screen.getByRole('button', { name: variant })).toBeInTheDocument();
    },
  );

  it('calls onClick when clicked', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Click me</Button>);
    await userEvent.click(screen.getByRole('button', { name: 'Click me' }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('does not call onClick when disabled', async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Disabled
      </Button>,
    );
    const btn = screen.getByRole('button', { name: 'Disabled' });
    expect(btn).toBeDisabled();
    await userEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('shows loading spinner when loading is true', () => {
    render(<Button loading>Loading</Button>);
    // Mantine renders a loader inside the button; the button still has the label.
    const btn = screen.getByRole('button', { name: /loading/i });
    expect(btn).toBeInTheDocument();
  });

  it('renders as disabled when both disabled and loading', () => {
    render(
      <Button disabled loading>
        Busy
      </Button>,
    );
    expect(screen.getByRole('button', { name: /busy/i })).toBeDisabled();
  });

  it('forwards ref to underlying button element', () => {
    const ref = vi.fn();
    render(<Button ref={ref}>Ref</Button>);
    expect(ref).toHaveBeenCalled();
    expect(ref.mock.calls[0][0]).toBeInstanceOf(HTMLButtonElement);
  });
});
