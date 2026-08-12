/**
 * Unit tests for api-errors type guard (WO-086).
 *
 * Covers isPermissionDeniedResponse with valid, invalid, and partial inputs.
 */

import { describe, expect, it } from 'vitest';
import { isPermissionDeniedResponse } from '@/types/api-errors';

const VALID = {
  error: 'forbidden',
  permission: 'release.approve',
  required_role: 'Tech Lead',
  message: 'Requires release.approve.',
  action: 'Contact your Platform Admin.',
};

describe('isPermissionDeniedResponse', () => {
  it('returns true for a fully valid object (required_role as string)', () => {
    expect(isPermissionDeniedResponse(VALID)).toBe(true);
  });

  it('returns true when required_role is an array of strings', () => {
    expect(
      isPermissionDeniedResponse({ ...VALID, required_role: ['Tech Lead', 'Platform Admin'] }),
    ).toBe(true);
  });

  it('returns false for null', () => {
    expect(isPermissionDeniedResponse(null)).toBe(false);
  });

  it('returns false for a non-object (string)', () => {
    expect(isPermissionDeniedResponse('forbidden')).toBe(false);
  });

  it('returns false for a non-object (number)', () => {
    expect(isPermissionDeniedResponse(403)).toBe(false);
  });

  it('returns false when error field is missing', () => {
    const { error: _, ...rest } = VALID;
    expect(isPermissionDeniedResponse(rest)).toBe(false);
  });

  it('returns false when permission field is missing', () => {
    const { permission: _, ...rest } = VALID;
    expect(isPermissionDeniedResponse(rest)).toBe(false);
  });

  it('returns false when required_role field is missing', () => {
    const { required_role: _, ...rest } = VALID;
    expect(isPermissionDeniedResponse(rest)).toBe(false);
  });

  it('returns false when message field is missing', () => {
    const { message: _, ...rest } = VALID;
    expect(isPermissionDeniedResponse(rest)).toBe(false);
  });

  it('returns false when action field is missing', () => {
    const { action: _, ...rest } = VALID;
    expect(isPermissionDeniedResponse(rest)).toBe(false);
  });

  it('returns false when required_role is an array containing a non-string', () => {
    expect(
      isPermissionDeniedResponse({ ...VALID, required_role: ['Admin', 42] }),
    ).toBe(false);
  });

  it('returns false for an empty object', () => {
    expect(isPermissionDeniedResponse({})).toBe(false);
  });

  it('returns false when permission is a number (wrong type)', () => {
    expect(isPermissionDeniedResponse({ ...VALID, permission: 42 })).toBe(false);
  });
});
