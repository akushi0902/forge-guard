import { type JSX } from 'react';
import { useMantineTheme } from '@mantine/core';

/** Bar chart with a plus — represents an empty manager dashboard awaiting data. */
export function EmptyDashboard(): JSX.Element {
  const theme = useMantineTheme();
  const primary = theme.colors.brand?.[6] ?? '#3b82f6';
  const muted = theme.colors.gray?.[3] ?? '#d1d5db';

  return (
    <svg
      width="96"
      height="96"
      viewBox="0 0 96 96"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* Chart floor */}
      <rect x="14" y="76" width="68" height="4" rx="2" fill={muted} />
      {/* Bar 1 (short) */}
      <rect x="22" y="60" width="12" height="16" rx="2" fill={muted} />
      {/* Bar 2 (medium) */}
      <rect x="42" y="44" width="12" height="32" rx="2" fill={muted} />
      {/* Bar 3 (tall) */}
      <rect x="62" y="32" width="12" height="44" rx="2" fill={muted} />
      {/* Plus sign (add services) */}
      <circle cx="26" cy="28" r="14" fill={primary} opacity="0.15" />
      <rect x="22" y="26" width="8" height="4" rx="1" fill={primary} />
      <rect x="24" y="22" width="4" height="12" rx="1" fill={primary} />
    </svg>
  );
}
