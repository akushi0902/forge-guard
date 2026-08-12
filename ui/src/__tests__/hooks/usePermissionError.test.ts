/**
 * Unit tests for usePermissionError hook (WO-086).
 *
 * Covers all 10 permissions, multi-role scenarios, unknown permission
 * fallback, and string vs array required_role handling.
 */

import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';

import { usePermissionError } from '@/hooks/usePermissionError';
import type { PermissionDeniedResponse } from '@/types/api-errors';

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

describe('usePermissionError', () => {
  it('returns permissionLabel for release.approve', () => {
    const { result } = renderHook(() => usePermissionError(makeError('release.approve')));
    expect(result.current.permissionLabel).toBe('Approve Release');
  });

  it('returns permissionLabel for policy.manage', () => {
    const { result } = renderHook(() => usePermissionError(makeError('policy.manage')));
    expect(result.current.permissionLabel).toBe('Manage Policies');
  });

  it('returns permissionLabel for rbac.manage', () => {
    const { result } = renderHook(() => usePermissionError(makeError('rbac.manage')));
    expect(result.current.permissionLabel).toBe('Manage Access Control');
  });

  it('returns permissionLabel for health.monitor', () => {
    const { result } = renderHook(() => usePermissionError(makeError('health.monitor')));
    expect(result.current.permissionLabel).toBe('Monitor Platform Health');
  });

  it('returns permissionLabel for trends.view', () => {
    const { result } = renderHook(() => usePermissionError(makeError('trends.view')));
    expect(result.current.permissionLabel).toBe('View Trends');
  });

  it('returns permissionLabel for exception.approve', () => {
    const { result } = renderHook(() => usePermissionError(makeError('exception.approve')));
    expect(result.current.permissionLabel).toBe('Approve Exception');
  });

  it('returns permissionLabel for exception.request', () => {
    const { result } = renderHook(() => usePermissionError(makeError('exception.request')));
    expect(result.current.permissionLabel).toBe('Request Exception');
  });

  it('returns permissionLabel for service.view', () => {
    const { result } = renderHook(() => usePermissionError(makeError('service.view')));
    expect(result.current.permissionLabel).toBe('View Services');
  });

  it('returns permissionLabel for assessment.request', () => {
    const { result } = renderHook(() => usePermissionError(makeError('assessment.request')));
    expect(result.current.permissionLabel).toBe('Request Assessment');
  });

  it('returns permissionLabel for release.block', () => {
    const { result } = renderHook(() => usePermissionError(makeError('release.block')));
    expect(result.current.permissionLabel).toBe('Block Release');
  });

  it('falls back to the raw slug for an unknown permission', () => {
    const { result } = renderHook(() => usePermissionError(makeError('some.unknown')));
    expect(result.current.permissionLabel).toBe('some.unknown');
  });

  it('returns comma-separated roles for multi-role permissions', () => {
    const { result } = renderHook(() => usePermissionError(makeError('release.approve')));
    expect(result.current.roleList).toContain('Tech Lead');
    expect(result.current.roleList).toContain('Platform Admin');
  });

  it('handles required_role as an array in the error payload', () => {
    const { result } = renderHook(() =>
      usePermissionError(
        makeError('unknown.perm', {
          required_role: ['Tech Lead', 'Platform Admin'],
        }),
      ),
    );
    expect(result.current.roleList).toContain('Tech Lead');
    expect(result.current.roleList).toContain('Platform Admin');
  });

  it('returns actionGuidance from the error payload', () => {
    const { result } = renderHook(() =>
      usePermissionError(makeError('policy.manage', { action: 'Ask your manager.' })),
    );
    expect(result.current.actionGuidance).toBe('Ask your manager.');
  });

  it('returns the permissionDescription', () => {
    const { result } = renderHook(() => usePermissionError(makeError('policy.manage')));
    expect(typeof result.current.permissionDescription).toBe('string');
    expect(result.current.permissionDescription.length).toBeGreaterThan(0);
  });
});
