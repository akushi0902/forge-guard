/**
 * Unit tests for piiMask utilities (WO-080).
 */

import { describe, expect, it } from 'vitest';
import { maskEmail } from '@/utils/piiMask';

describe('maskEmail', () => {
  it('masks standard email: first char + *** + @domain', () => {
    expect(maskEmail('john@example.com')).toBe('j***@example.com');
  });

  it('masks email with subdomain', () => {
    expect(maskEmail('alice@forgeguard.io')).toBe('a***@forgeguard.io');
  });

  it('masks email with dots in local part', () => {
    expect(maskEmail('bob.martinez@forgeguard.io')).toBe('b***@forgeguard.io');
  });

  it('returns empty string for empty input', () => {
    expect(maskEmail('')).toBe('');
  });

  it('handles string with no @ sign', () => {
    expect(maskEmail('noemail')).toBe('n***');
  });

  it('handles single character before @', () => {
    expect(maskEmail('a@b.com')).toBe('a***@b.com');
  });

  it('handles long local part', () => {
    expect(maskEmail('verylongemail@example.com')).toBe('v***@example.com');
  });
});
