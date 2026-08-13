/**
 * PII masking utilities for ForgeGuard (WO-080).
 *
 * Email addresses are masked in table displays per organisational policy.
 * Full email values are only shown in detail/confirmation views.
 */

/**
 * Mask an email address: keep the first character of the local part,
 * replace the rest with ***, and keep the domain unchanged.
 *
 * Examples:
 *   maskEmail('john@example.com')    → 'j***@example.com'
 *   maskEmail('alice@forgeguard.io') → 'a***@forgeguard.io'
 *   maskEmail('')                    → ''
 *   maskEmail('bad-email')           → 'b***'
 */
export function maskEmail(email: string): string {
  if (!email) return '';
  const atIdx = email.indexOf('@');
  if (atIdx <= 0) {
    // No @ or it's the first char — mask everything after first char
    return email.slice(0, 1) + '***';
  }
  const local = email.slice(0, atIdx);
  const domain = email.slice(atIdx);
  return local.slice(0, 1) + '***' + domain;
}
