/**
 * Unit tests for permission-interceptor (WO-086).
 *
 * Covers: structured 403 triggering notification, malformed body fallback,
 * deduplication via notification ID, and no-op for non-403 errors.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock @mantine/notifications before importing the interceptor
const mockNotificationsShow = vi.fn();
vi.mock('@mantine/notifications', () => ({
  notifications: { show: mockNotificationsShow },
}));

import { showPermissionDeniedNotification } from '@/lib/permission-interceptor';
import type { PermissionDeniedResponse } from '@/types/api-errors';

const VALID_403_BODY: PermissionDeniedResponse = {
  error: 'forbidden',
  permission: 'release.approve',
  required_role: ['Tech Lead', 'Platform Admin'],
  message: "This action requires the 'release.approve' permission.",
  action: 'Contact your Platform Admin for access.',
};

beforeEach(() => {
  mockNotificationsShow.mockClear();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('showPermissionDeniedNotification — structured body', () => {
  it('calls notifications.show when given a valid PermissionDeniedResponse', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    expect(mockNotificationsShow).toHaveBeenCalledOnce();
  });

  it('sets the notification color to "red"', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    expect(mockNotificationsShow).toHaveBeenCalledWith(
      expect.objectContaining({ color: 'red' }),
    );
  });

  it('sets the notification title to "Permission Denied"', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    expect(mockNotificationsShow).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Permission Denied' }),
    );
  });

  it('includes the human-readable permission label in the message', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    const call = mockNotificationsShow.mock.calls[0][0] as { message: string };
    expect(call.message).toContain('Approve Release');
  });

  it('includes role names in the message', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    const call = mockNotificationsShow.mock.calls[0][0] as { message: string };
    expect(call.message).toContain('Tech Lead');
    expect(call.message).toContain('Platform Admin');
  });

  it('includes action guidance in the message', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    const call = mockNotificationsShow.mock.calls[0][0] as { message: string };
    expect(call.message).toContain('Contact your Platform Admin');
  });

  it('uses permission slug as notification id for deduplication', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    expect(mockNotificationsShow).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'permission-denied:release.approve' }),
    );
  });

  it('sets autoClose to 10 000 ms', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    expect(mockNotificationsShow).toHaveBeenCalledWith(
      expect.objectContaining({ autoClose: 10_000 }),
    );
  });

  it('sets withCloseButton to true', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    expect(mockNotificationsShow).toHaveBeenCalledWith(
      expect.objectContaining({ withCloseButton: true }),
    );
  });
});

describe('showPermissionDeniedNotification — different permissions', () => {
  it('shows policy.manage permission correctly', () => {
    showPermissionDeniedNotification({
      ...VALID_403_BODY,
      permission: 'policy.manage',
      required_role: 'Platform Admin',
    });
    const call = mockNotificationsShow.mock.calls[0][0] as { message: string; id: string };
    expect(call.message).toContain('Manage Policies');
    expect(call.id).toBe('permission-denied:policy.manage');
  });

  it('shows health.monitor permission correctly', () => {
    showPermissionDeniedNotification({
      ...VALID_403_BODY,
      permission: 'health.monitor',
      required_role: ['Operator', 'Platform Admin'],
    });
    const call = mockNotificationsShow.mock.calls[0][0] as { message: string };
    expect(call.message).toContain('Monitor Platform Health');
    expect(call.message).toContain('Operator');
  });
});

describe('showPermissionDeniedNotification — malformed body fallback', () => {
  it('shows a fallback notification for null body', () => {
    showPermissionDeniedNotification(null);
    expect(mockNotificationsShow).toHaveBeenCalledOnce();
    const call = mockNotificationsShow.mock.calls[0][0] as { id: string; message: string };
    expect(call.id).toBe('permission-denied:unknown');
    expect(call.message).toContain('Contact your Platform Admin');
  });

  it('shows a fallback notification for an empty object', () => {
    showPermissionDeniedNotification({});
    expect(mockNotificationsShow).toHaveBeenCalledOnce();
    const call = mockNotificationsShow.mock.calls[0][0] as { id: string };
    expect(call.id).toBe('permission-denied:unknown');
  });

  it('shows a fallback notification when permission field is missing', () => {
    showPermissionDeniedNotification({
      error: 'forbidden',
      required_role: 'Admin',
      // missing: permission, message, action
    });
    const call = mockNotificationsShow.mock.calls[0][0] as { id: string };
    expect(call.id).toBe('permission-denied:unknown');
  });

  it('shows a fallback notification for a plain string body', () => {
    showPermissionDeniedNotification('Forbidden');
    expect(mockNotificationsShow).toHaveBeenCalledOnce();
    const call = mockNotificationsShow.mock.calls[0][0] as { id: string };
    expect(call.id).toBe('permission-denied:unknown');
  });
});

describe('showPermissionDeniedNotification — deduplication', () => {
  it('uses different ids for different permissions (allowing stacking)', () => {
    showPermissionDeniedNotification(VALID_403_BODY);
    showPermissionDeniedNotification({
      ...VALID_403_BODY,
      permission: 'policy.manage',
      required_role: 'Platform Admin',
    });
    expect(mockNotificationsShow).toHaveBeenCalledTimes(2);
    const ids = mockNotificationsShow.mock.calls.map(
      (c: [{ id: string }]) => c[0].id,
    );
    expect(ids[0]).toBe('permission-denied:release.approve');
    expect(ids[1]).toBe('permission-denied:policy.manage');
  });
});
