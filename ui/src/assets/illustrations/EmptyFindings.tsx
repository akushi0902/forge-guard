import { type JSX } from 'react';
import { useMantineTheme } from '@mantine/core';

/** Magnifying glass over a shield — represents no findings / clean state. */
export function EmptyFindings(): JSX.Element {
  const theme = useMantineTheme();
  const success = theme.colors.green?.[6] ?? '#16a34a';
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
      {/* Shield body */}
      <path
        d="M48 12 L76 24 L76 52 C76 68 48 84 48 84 C48 84 20 68 20 52 L20 24 Z"
        fill={muted}
        stroke={success}
        strokeWidth="2"
      />
      {/* Checkmark inside shield */}
      <path
        d="M36 48 L44 56 L60 40"
        stroke={success}
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
