/**
 * ForgeGuard enterprise design tokens — Mantine 7 theme configuration.
 *
 * Design token groups:
 *   colors       — semantic palette (brand, success, warning, danger, info, neutral)
 *   typography   — font families, 7-level font-size scale
 *   spacing      — 8px base-unit scale (xs → xl)
 *   radius       — border-radius tokens (xs → xl)
 *   shadows      — 3-level elevation system (sm / md / lg)
 *   components   — default prop overrides for Mantine primitives
 */

import { createTheme, type MantineColorsTuple } from '@mantine/core';

// ---------------------------------------------------------------------------
// Color palettes (10-shade tuples, index 5 = primary shade)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Theme export
// ---------------------------------------------------------------------------

export const forgeguardTheme = createTheme({
  // ---- Colors ---------------------------------------------------------------
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

  // ---- Typography -----------------------------------------------------------
  fontFamily:
    'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  fontFamilyMonospace:
    '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',

  /** 7-level font-size scale (xs → xxl) */
  fontSizes: {
    xs: '11px',
    sm: '13px',
    md: '15px',
    lg: '17px',
    xl: '20px',
    '2xl': '24px',
    '3xl': '30px',
  },

  headings: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    fontWeight: '600',
  },

  // ---- Spacing (8px base unit) ----------------------------------------------
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px',
  },

  // ---- Border radius --------------------------------------------------------
  radius: {
    xs: '2px',
    sm: '4px',
    md: '6px',
    lg: '8px',
    xl: '12px',
  },
  defaultRadius: 'md',

  // ---- Shadows (3-level elevation) ------------------------------------------
  shadows: {
    sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
    lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
    xl: '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
    xxl: '0 25px 50px -12px rgb(0 0 0 / 0.25)',
  },

  // ---- Component default prop overrides -------------------------------------
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
    TextInput: {
      defaultProps: {
        radius: 'md',
      },
    },
    Select: {
      defaultProps: {
        radius: 'md',
      },
    },
    Textarea: {
      defaultProps: {
        radius: 'md',
      },
    },
    Modal: {
      defaultProps: {
        radius: 'md',
        centered: true,
      },
    },
  },
});
