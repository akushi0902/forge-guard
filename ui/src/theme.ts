/**
 * Backward-compatible re-export shim.
 *
 * The canonical theme definition lives in `@/theme/forgeguard-theme.ts`.
 * This file re-exports it under the legacy name `theme` so existing imports
 * of `@/theme` continue to work without modification.
 */
export { forgeguardTheme as theme } from '@/theme/forgeguard-theme';
