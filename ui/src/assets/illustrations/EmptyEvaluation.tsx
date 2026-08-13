import { type JSX } from 'react';
import { useMantineTheme } from '@mantine/core';

/** Clipboard with a checkmark — represents a completed evaluation. */
export function EmptyEvaluation(): JSX.Element {
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
      {/* Clipboard body */}
      <rect x="20" y="16" width="56" height="68" rx="6" fill={muted} />
      {/* Clipboard header */}
      <rect x="32" y="10" width="32" height="14" rx="4" fill={primary} opacity="0.7" />
      {/* Lines representing evaluation rows */}
      <rect x="30" y="38" width="36" height="4" rx="2" fill={primary} opacity="0.4" />
      <rect x="30" y="48" width="28" height="4" rx="2" fill={primary} opacity="0.3" />
      <rect x="30" y="58" width="32" height="4" rx="2" fill={primary} opacity="0.2" />
      {/* Circle overlay (empty indicator) */}
      <circle cx="72" cy="72" r="16" fill="white" stroke={muted} strokeWidth="2" />
      {/* Question mark */}
      <text x="72" y="77" textAnchor="middle" fontSize="16" fill={primary} fontWeight="700">?</text>
    </svg>
  );
}
