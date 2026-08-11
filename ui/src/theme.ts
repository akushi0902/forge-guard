import { createTheme, type MantineColorsTuple } from '@mantine/core';

/**
 * ForgeGuard enterprise theme for Mantine 7.
 *
 * Color palette:
 *   - brand (blue)  — primary interactive elements, CTA buttons, links
 *   - neutral (gray) — backgrounds, borders, muted text
 *   - success (green) — APPROVE decisions, healthy scores, resolved findings
 *   - warning (amber) — CONDITIONAL decisions, medium-risk scores
 *   - danger  (red)   — BLOCK decisions, critical findings, errors
 *   - info    (cyan)  — informational badges, help text
 */

const brandBlue: MantineColorsTuple = [
  '#e8f0fe',
  '#c5d8fc',
  '#9bbef9',
  '#6fa3f6',
  '#4d8df4',
  '#2563eb', // index 5 — primary brand
  '#1d55d4',
  '#1747ba',
  '#123a9e',
  '#0c2d7f',
];

const neutralGray: MantineColorsTuple = [
  '#f8fafc',
  '#f1f5f9',
  '#e2e8f0',
  '#cbd5e1',
  '#94a3b8',
  '#64748b', // index 5 — base neutral
  '#475569',
  '#334155',
  '#1e293b',
  '#0f172a',
];

const successGreen: MantineColorsTuple = [
  '#f0fdf4',
  '#dcfce7',
  '#bbf7d0',
  '#86efac',
  '#4ade80',
  '#16a34a', // index 5
  '#15803d',
  '#166534',
  '#14532d',
  '#052e16',
];

const warningAmber: MantineColorsTuple = [
  '#fffbeb',
  '#fef3c7',
  '#fde68a',
  '#fcd34d',
  '#fbbf24',
  '#d97706', // index 5
  '#b45309',
  '#92400e',
  '#78350f',
  '#451a03',
];

const dangerRed: MantineColorsTuple = [
  '#fef2f2',
  '#fee2e2',
  '#fecaca',
  '#fca5a5',
  '#f87171',
  '#dc2626', // index 5
  '#b91c1c',
  '#991b1b',
  '#7f1d1d',
  '#450a0a',
];

const infoCyan: MantineColorsTuple = [
  '#ecfeff',
  '#cffafe',
  '#a5f3fc',
  '#67e8f9',
  '#22d3ee',
  '#0891b2', // index 5
  '#0e7490',
  '#155e75',
  '#164e63',
  '#083344',
];

export const theme = createTheme({
  colors: {
    brand: brandBlue,
    neutral: neutralGray,
    success: successGreen,
    warning: warningAmber,
    danger: dangerRed,
    info: infoCyan,
  },
  primaryColor: 'brand',
  primaryShade: { light: 5, dark: 4 },

  fontFamily:
    'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  fontFamilyMonospace:
    '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',

  headings: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    fontWeight: '600',
  },

  radius: {
    xs: '2px',
    sm: '4px',
    md: '6px',
    lg: '8px',
    xl: '12px',
  },

  spacing: {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px',
  },

  defaultRadius: 'md',

  components: {
    Button: {
      defaultProps: {
        radius: 'md',
      },
    },
    Card: {
      defaultProps: {
        radius: 'md',
        shadow: 'sm',
        withBorder: true,
      },
    },
    Badge: {
      defaultProps: {
        radius: 'sm',
      },
    },
  },
});
