import { type JSX } from 'react';
import { useMantineTheme } from '@mantine/core';

/** Rocket ship — represents a release waiting to launch. */
export function EmptyReleases(): JSX.Element {
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
      {/* Rocket body */}
      <path
        d="M48 10 C48 10 62 24 62 46 L62 64 L48 72 L34 64 L34 46 C34 24 48 10 48 10Z"
        fill={muted}
        stroke={primary}
        strokeWidth="2"
      />
      {/* Nose cone */}
      <path d="M48 10 C52 18 56 28 62 46 L34 46 C40 28 44 18 48 10Z" fill={primary} opacity="0.5" />
      {/* Window */}
      <circle cx="48" cy="44" r="6" fill="white" stroke={primary} strokeWidth="2" />
      {/* Flame */}
      <path
        d="M40 72 C40 80 44 84 48 86 C52 84 56 80 56 72 L48 76 Z"
        fill={primary}
        opacity="0.6"
      />
    </svg>
  );
}
