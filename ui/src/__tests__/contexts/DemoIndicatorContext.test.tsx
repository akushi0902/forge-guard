import { describe, expect, it } from 'vitest';
import { render, screen } from '@/test-utils';
import { DemoIndicatorProvider, useDemoContext } from '@/contexts/DemoIndicatorContext';

function DemoConsumer() {
  const { isDemo, serviceName } = useDemoContext();
  return (
    <div>
      <span data-testid="is-demo">{String(isDemo)}</span>
      <span data-testid="service-name">{serviceName ?? 'null'}</span>
    </div>
  );
}

describe('DemoIndicatorProvider', () => {
  it('provides isDemo=true when wrapped with a demo provider (AC-4)', () => {
    render(
      <DemoIndicatorProvider isDemo={true} serviceName="Payment Service">
        <DemoConsumer />
      </DemoIndicatorProvider>,
    );
    expect(screen.getByTestId('is-demo')).toHaveTextContent('true');
  });

  it('provides isDemo=false when wrapped with a non-demo provider (AC-7)', () => {
    render(
      <DemoIndicatorProvider isDemo={false}>
        <DemoConsumer />
      </DemoIndicatorProvider>,
    );
    expect(screen.getByTestId('is-demo')).toHaveTextContent('false');
  });

  it('provides serviceName when specified', () => {
    render(
      <DemoIndicatorProvider isDemo={true} serviceName="Payment Service">
        <DemoConsumer />
      </DemoIndicatorProvider>,
    );
    expect(screen.getByTestId('service-name')).toHaveTextContent('Payment Service');
  });

  it('provides serviceName=null when not specified', () => {
    render(
      <DemoIndicatorProvider isDemo={true}>
        <DemoConsumer />
      </DemoIndicatorProvider>,
    );
    expect(screen.getByTestId('service-name')).toHaveTextContent('null');
  });

  it('defaults to isDemo=false when no provider is present (safe default, AC-4 edge case)', () => {
    render(<DemoConsumer />);
    expect(screen.getByTestId('is-demo')).toHaveTextContent('false');
  });

  it('defaults to serviceName=null when no provider is present', () => {
    render(<DemoConsumer />);
    expect(screen.getByTestId('service-name')).toHaveTextContent('null');
  });

  it('treats missing is_demo field as false (AC-4 edge case)', () => {
    // Simulate API response with no is_demo field: undefined coerced to false
    const isDemo = (undefined as unknown as boolean | undefined) ?? false;
    render(
      <DemoIndicatorProvider isDemo={isDemo}>
        <DemoConsumer />
      </DemoIndicatorProvider>,
    );
    expect(screen.getByTestId('is-demo')).toHaveTextContent('false');
  });

  it('updates context when isDemo prop changes via parent re-render', () => {
    const { rerender } = render(
      <DemoIndicatorProvider isDemo={false}>
        <DemoConsumer />
      </DemoIndicatorProvider>,
    );
    expect(screen.getByTestId('is-demo')).toHaveTextContent('false');

    rerender(
      <DemoIndicatorProvider isDemo={true}>
        <DemoConsumer />
      </DemoIndicatorProvider>,
    );
    expect(screen.getByTestId('is-demo')).toHaveTextContent('true');
  });
});

describe('useDemoContext hook', () => {
  it('returns { isDemo: false, serviceName: null } when no provider is present', () => {
    render(<DemoConsumer />);
    expect(screen.getByTestId('is-demo')).toHaveTextContent('false');
    expect(screen.getByTestId('service-name')).toHaveTextContent('null');
  });

  it('returns isDemo from the nearest DemoIndicatorProvider', () => {
    render(
      <DemoIndicatorProvider isDemo={true} serviceName="Demo Svc">
        <DemoConsumer />
      </DemoIndicatorProvider>,
    );
    expect(screen.getByTestId('is-demo')).toHaveTextContent('true');
    expect(screen.getByTestId('service-name')).toHaveTextContent('Demo Svc');
  });
});
