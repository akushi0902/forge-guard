import { type JSX } from 'react';
import { useMantineTheme } from '@mantine/core';

/** Wrench over a document — represents remediation work to be done. */
export function EmptyRemediation(): JSX.Element {
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
      {/* Document body */}
      <rect x="18" y="14" width="48" height="60" rx="4" fill={muted} />
      {/* Document lines */}
      <rect x="26" y="28" width="32" height="4" rx="2" fill={primary} opacity="0.3" />
      <rect x="26" y="38" width="24" height="4" rx="2" fill={primary} opacity="0.2" />
      <rect x="26" y="48" width="28" height="4" rx="2" fill={primary} opacity="0.2" />
      {/* Wrench */}
      <path
        d="M60 54 C56 50 56 44 60 40 C62 38 66 38 68 40 L62 46 L66 50 L72 44 C74 46 74 50 72 52 C68 56 62 58 58 62 L54 74 L60 76 L66 64 C70 62 72 58 60 54Z"
        fill={primary}
        opacity="0.8"
      />
    </svg>
  );
}
