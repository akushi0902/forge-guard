/**
 * useDemoContext — convenience re-export of the hook from DemoIndicatorContext.
 *
 * Returns { isDemo, serviceName }. Defaults to isDemo=false when no
 * DemoIndicatorProvider is present in the tree, so it is safe to call
 * from any component without a required ancestor provider.
 */

export {
  useDemoContext,
  type DemoIndicatorContextType,
} from '@/contexts/DemoIndicatorContext';
