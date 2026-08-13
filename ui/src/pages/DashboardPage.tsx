/**
 * DashboardPage — thin wrapper that renders DeveloperDashboard (WO-072).
 *
 * The actual implementation lives in DeveloperDashboard.tsx so it can be
 * lazy-loaded independently from the router and tested in isolation.
 */
import { type JSX } from 'react';
import { DeveloperDashboard } from './DeveloperDashboard';

export function DashboardPage(): JSX.Element {
  return <DeveloperDashboard />;
}
