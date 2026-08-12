/**
 * Unit tests for permissionMap utility (WO-086).
 *
 * Covers: PERMISSION_MAP completeness, formatPermissionError for all 10
 * permissions, multi-role scenarios, and unknown permission fallback.
 */

import { describe, expect, it } from 'vitest';

import {
  PERMISSION_MAP,
  formatPermissionError,
  FALLBACK_PERMISSION_MESSAGE,
} from '@/utils/permissionMap';
import type { PermissionDeniedResponse } from '@/types/api-errors';

// ---------------------------------------------------------------------------
// The 10 canonical RBAC permission slugs
// ---------------------------------------------------------------------------

const EXPECTED_PERMISSIONS = [
  'service.view',
  'assessment.request',
  'release.approve',
  'release.block',
  'exception.request',
  'exception.approve',
  'policy.manage',
  'rbac.manage',
  'health.monitor',
  'trends.view',
] as const;

// ---------------------------------------------------------------------------
// PERMISSION_MAP completeness
// ---------------------------------------------------------------------------

describe('PERMISSION_MAP', () => {
  it('defines all 10 RBAC permissions', () => {
    for (const perm of EXPECTED_PERMISSIONS) {
      expect(PERMISSION_MAP).toHaveProperty(perm);
    }
  });

  it('has the correct shape for each entry', () => {
    for (const perm of EXPECTED_PERMISSIONS) {
      const entry = PERMISSION_MAP[perm];
      expect(typeof entry.humanLabel).toBe('string');
      expect(entry.humanLabel.length).toBeGreaterThan(0);
      expect(typeof entry.description).toBe('string');
      expect(entry.description.length).toBeGreaterThan(0);
      expect(Array.isArray(entry.roles)).toBe(true);
      expect(entry.roles.length).toBeGreaterThan(0);
    }
  });

  it('maps release.approve to Tech Lead and Platform Admin', () => {
    expect(PERMISSION_MAP['release.approve'].roles).toContain('Tech Lead');
    expect(PERMISSION_MAP['release.approve'].roles).toContain('Platform Admin');
  });

  it('maps policy.manage exclusively to Platform Admin', () => {
    expect(PERMISSION_MAP['policy.manage'].roles).toEqual(['Platform Admin']);
  });

  it('maps rbac.manage exclusively to Platform Admin', () => {
    expect(PERMISSION_MAP['rbac.manage'].roles).toEqual(['Platform Admin']);
  });

  it('maps health.monitor to Operator and Platform Admin', () => {
    expect(PERMISSION_MAP['health.monitor'].roles).toContain('Operator');
    expect(PERMISSION_MAP['health.monitor'].roles).toContain('Platform Admin');
  });

  it('maps exception.approve to Engineering Manager and Platform Admin', () => {
    expect(PERMISSION_MAP['exception.approve'].roles).toContain('Engineering Manager');
    expect(PERMISSION_MAP['exception.approve'].roles).toContain('Platform Admin');
  });
});

// ---------------------------------------------------------------------------
// formatPermissionError
// ---------------------------------------------------------------------------

function makeError(
  permission: string,
  overrides: Partial<PermissionDeniedResponse> = {},
): PermissionDeniedResponse {
  return {
    error: 'forbidden',
    permission,
    required_role: 'Platform Admin',
    message: `Requires ${permission}`,
    action: 'Contact your Platform Admin for access.',
    ...overrides,
  };
}

describe('formatPermissionError', () => {
  it('returns humanLabel from PERMISSION_MAP for a known permission', () => {
    const result = formatPermissionError(makeError('release.approve'));
    expect(result.permissionLabel).toBe('Approve Release');
  });

  it('returns permission slug as label for an unknown permission', () => {
    const result = formatPermissionError(makeError('unknown.permission'));
    expect(result.permissionLabel).toBe('unknown.permission');
  });

  it('returns description from PERMISSION_MAP for a known permission', () => {
    const result = formatPermissionError(makeError('policy.manage'));
    expect(result.permissionDescription).toContain('policy');
  });

  it('falls back to a generated description for unknown permissions', () => {
    const result = formatPermissionError(makeError('unknown.thing'));
    expect(result.permissionDescription).toContain("'unknown.thing'");
  });

  it('returns comma-separated role list from PERMISSION_MAP for known permission', () => {
    const result = formatPermissionError(makeError('release.approve'));
    expect(result.roleList).toContain('Tech Lead');
    expect(result.roleList).toContain('Platform Admin');
  });

  it('handles required_role as a string (single role)', () => {
    const result = formatPermissionError(
      makeError('unknown.perm', { required_role: 'Tech Lead' }),
    );
    expect(result.roleList).toContain('Tech Lead');
  });

  it('handles required_role as an array of strings', () => {
    const result = formatPermissionError(
      makeError('unknown.perm', { required_role: ['Tech Lead', 'Platform Admin'] }),
    );
    expect(result.roleList).toContain('Tech Lead');
    expect(result.roleList).toContain('Platform Admin');
  });

  it('includes the action guidance from the error response', () => {
    const result = formatPermissionError(
      makeError('policy.manage', { action: 'Ask your admin.' }),
    );
    expect(result.actionGuidance).toBe('Ask your admin.');
  });

  it('falls back to FALLBACK_PERMISSION_MESSAGE when action is empty string', () => {
    const result = formatPermissionError(makeError('policy.manage', { action: '' }));
    expect(result.actionGuidance).toBe(FALLBACK_PERMISSION_MESSAGE);
  });

  it('formats all 10 permissions without throwing', () => {
    for (const perm of EXPECTED_PERMISSIONS) {
      expect(() => formatPermissionError(makeError(perm))).not.toThrow();
    }
  });
});
