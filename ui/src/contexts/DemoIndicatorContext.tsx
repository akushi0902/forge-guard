/**
 * DemoIndicatorContext — provides demo-data awareness to any descendant component.
 *
 * Wrap a service-specific view with DemoIndicatorProvider and pass
 * isDemo from the API response. Child components call useDemoContext()
 * to conditionally render MockDataBadge / MockDataBanner.
 *
 * Default value is { isDemo: false, serviceName: null } so components are
 * safe to use outside a provider (they simply render no demo indicators).
 */

import {
  createContext,
  useContext,
  type JSX,
  type ReactNode,
} from 'react';

export interface DemoIndicatorContextType {
  /** True when the current service has is_demo: true in the API response. */
  isDemo: boolean;
  /** Display name of the demo service, or null for non-demo services. */
  serviceName: string | null;
}

const DEFAULT_CONTEXT: DemoIndicatorContextType = {
  isDemo: false,
  serviceName: null,
};

export const DemoIndicatorContext =
  createContext<DemoIndicatorContextType>(DEFAULT_CONTEXT);

DemoIndicatorContext.displayName = 'DemoIndicatorContext';

export interface DemoIndicatorProviderProps {
  /** Whether the active service is a demo service (from is_demo API field). */
  isDemo: boolean;
  /** Optional display name of the service for contextual messaging. */
  serviceName?: string | null;
  children: ReactNode;
}

/**
 * Wrap service detail views to propagate demo-data context to all descendants.
 *
 * @example
 * <DemoIndicatorProvider isDemo={service.is_demo ?? false} serviceName={service.name}>
 *   <HealthScoreCard score={score} />
 * </DemoIndicatorProvider>
 */
export function DemoIndicatorProvider({
  isDemo,
  serviceName = null,
  children,
}: DemoIndicatorProviderProps): JSX.Element {
  return (
    <DemoIndicatorContext.Provider value={{ isDemo, serviceName }}>
      {children}
    </DemoIndicatorContext.Provider>
  );
}

/** Consume the DemoIndicatorContext. Returns safe defaults if no provider is present. */
export function useDemoContext(): DemoIndicatorContextType {
  return useContext(DemoIndicatorContext);
}
