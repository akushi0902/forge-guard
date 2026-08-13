/**
 * Mock data fixtures for Security Review page tests (WO-077).
 *
 * Covers varied severity levels, statuses, service names, and edge cases
 * (long descriptions, missing optional fields) for comprehensive testing.
 */

import { type PaginatedResponse } from '@/types/api';
import {
  type SecurityFinding,
  type EscalatedRelease,
  type PendingException,
} from '@/hooks/api/useSecurityFindings';

// ---------------------------------------------------------------------------
// Individual security findings
// ---------------------------------------------------------------------------

export const SEC_CRITICAL_FINDING_1: SecurityFinding = {
  id: 'sec-fnd-crit-001',
  service_id: 'svc-payment-001',
  service_name: 'payment-service',
  dimension: 'security',
  severity: 'critical',
  title: 'Hardcoded AWS credentials in source code',
  description:
    'AWS access key found in src/config.py. This allows full account compromise if the repository is public or if an attacker gains read access.',
  status: 'open',
  created_at: '2026-08-10T08:00:00Z',
};

export const SEC_CRITICAL_FINDING_2: SecurityFinding = {
  id: 'sec-fnd-crit-002',
  service_id: 'svc-auth-002',
  service_name: 'auth-service',
  dimension: 'security',
  severity: 'critical',
  title: 'SQL injection vulnerability in login endpoint',
  description:
    'User-supplied input is interpolated directly into SQL query in /api/v1/auth/login without parameterisation.',
  status: 'open',
  created_at: '2026-08-11T09:30:00Z',
};

export const SEC_HIGH_FINDING_1: SecurityFinding = {
  id: 'sec-fnd-high-001',
  service_id: 'svc-payment-001',
  service_name: 'payment-service',
  dimension: 'security',
  severity: 'high',
  title: 'Outdated dependency with known CVE',
  description: 'lodash@4.17.20 — CVE-2021-23337 (prototype pollution, CVSS 7.2).',
  status: 'open',
  created_at: '2026-08-09T10:00:00Z',
};

export const SEC_HIGH_FINDING_2: SecurityFinding = {
  id: 'sec-fnd-high-002',
  service_id: 'svc-inventory-003',
  service_name: 'inventory-service',
  dimension: 'security',
  severity: 'high',
  title: 'Missing rate limiting on authentication endpoints',
  description:
    'POST /api/v1/auth/login does not apply rate limiting, enabling brute-force attacks.',
  status: 'in_progress',
  created_at: '2026-08-08T14:00:00Z',
};

export const SEC_RESOLVED_FINDING: SecurityFinding = {
  id: 'sec-fnd-res-001',
  service_id: 'svc-payment-001',
  service_name: 'payment-service',
  dimension: 'security',
  severity: 'high',
  title: 'Insecure cookie flags — previously resolved',
  description: 'Session cookie lacked HttpOnly and Secure flags.',
  status: 'resolved',
  created_at: '2026-08-05T08:00:00Z',
};

/** Finding with an unusually long description (edge case). */
export const SEC_LONG_DESCRIPTION_FINDING: SecurityFinding = {
  id: 'sec-fnd-long-001',
  service_id: 'svc-notification-004',
  service_name: 'notification-service',
  dimension: 'security',
  severity: 'high',
  title: 'Improper input validation on webhook payload',
  description:
    'The webhook receiver at POST /api/v1/webhooks/github does not validate the X-Hub-Signature-256 ' +
    'header before processing the payload. An attacker could forge arbitrary webhook events, ' +
    'triggering deployments of malicious code or exfiltrating environment configuration. ' +
    'The fix requires implementing HMAC-SHA256 signature validation using the shared webhook ' +
    'secret configured in the GitHub repository settings. This vulnerability has been present ' +
    'since the initial webhook integration in commit abc123def.',
  status: 'open',
  created_at: '2026-08-07T11:00:00Z',
};

// ---------------------------------------------------------------------------
// Paginated responses
// ---------------------------------------------------------------------------

/** Standard multi-severity response. */
export const SECURITY_FINDINGS_PAGINATED: PaginatedResponse<SecurityFinding> = {
  items: [
    SEC_CRITICAL_FINDING_1,
    SEC_CRITICAL_FINDING_2,
    SEC_HIGH_FINDING_1,
    SEC_HIGH_FINDING_2,
  ],
  cursor: null,
  total_count: 4,
};

/** Response with only critical findings. */
export const CRITICAL_SECURITY_FINDINGS_PAGINATED: PaginatedResponse<SecurityFinding> = {
  items: [SEC_CRITICAL_FINDING_1, SEC_CRITICAL_FINDING_2],
  cursor: null,
  total_count: 2,
};

/** Empty findings response — triggers empty state. */
export const EMPTY_SECURITY_FINDINGS_PAGINATED: PaginatedResponse<SecurityFinding> = {
  items: [],
  cursor: null,
  total_count: 0,
};

/** Response with a second page cursor. */
export const SECURITY_FINDINGS_PAGE_1: PaginatedResponse<SecurityFinding> = {
  items: [SEC_CRITICAL_FINDING_1, SEC_CRITICAL_FINDING_2],
  cursor: 'cursor-sec-page-2',
  total_count: 5,
};

// ---------------------------------------------------------------------------
// Escalated releases
// ---------------------------------------------------------------------------

export const ESCALATED_RELEASE_1: EscalatedRelease = {
  id: 'rel-esc-001',
  service_id: 'svc-payment-001',
  service_name: 'payment-service',
  commit_sha: 'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
  status: 'escalated',
  risk_score: 82,
  created_at: '2026-08-12T10:00:00Z',
  severity: 'critical',
  finding_title: 'Hardcoded AWS credentials in source code',
  finding_description:
    'AWS access key found in src/config.py. Immediate rotation required.',
};

export const ESCALATED_RELEASE_2: EscalatedRelease = {
  id: 'rel-esc-002',
  service_id: 'svc-auth-002',
  service_name: 'auth-service',
  commit_sha: 'b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3',
  status: 'escalated',
  risk_score: 75,
  created_at: '2026-08-11T14:30:00Z',
  severity: 'high',
  finding_title: 'Missing HMAC signature validation on webhook receiver',
  finding_description:
    'Webhook payload processed without verifying X-Hub-Signature-256 header.',
};

export const ESCALATIONS_PAGINATED: PaginatedResponse<EscalatedRelease> = {
  items: [ESCALATED_RELEASE_1, ESCALATED_RELEASE_2],
  cursor: null,
  total_count: 2,
};

export const EMPTY_ESCALATIONS_PAGINATED: PaginatedResponse<EscalatedRelease> = {
  items: [],
  cursor: null,
  total_count: 0,
};

// ---------------------------------------------------------------------------
// Pending exceptions
// ---------------------------------------------------------------------------

export const PENDING_EXCEPTION_1: PendingException = {
  id: 'exc-001',
  finding_id: 'sec-fnd-high-001',
  finding_title: 'Outdated dependency with known CVE',
  service_name: 'payment-service',
  severity: 'high',
  justification: 'Upgrade path blocked by breaking changes in 5.x API. Fix scheduled for next sprint.',
  status: 'pending',
  created_at: '2026-08-11T09:00:00Z',
  expires_at: '2026-09-11T09:00:00Z',
};

export const PENDING_EXCEPTION_2: PendingException = {
  id: 'exc-002',
  finding_id: 'sec-fnd-high-002',
  finding_title: 'Missing rate limiting on authentication endpoints',
  service_name: 'inventory-service',
  severity: 'high',
  justification: 'Rate limiting infrastructure being deployed next week. Temporary WAF rule applied.',
  status: 'pending',
  created_at: '2026-08-10T16:00:00Z',
  expires_at: '2026-08-20T16:00:00Z',
};

export const PENDING_EXCEPTIONS_PAGINATED: PaginatedResponse<PendingException> = {
  items: [PENDING_EXCEPTION_1, PENDING_EXCEPTION_2],
  cursor: null,
  total_count: 2,
};

export const EMPTY_EXCEPTIONS_PAGINATED: PaginatedResponse<PendingException> = {
  items: [],
  cursor: null,
  total_count: 0,
};

// ---------------------------------------------------------------------------
// Blocked release decision response
// ---------------------------------------------------------------------------

export const BLOCK_DECISION_RESPONSE = {
  id: 'dec-block-001',
  decision: 'BLOCK',
  decided_by: 'security-reviewer@forgeguard.io',
  decided_at: '2026-08-12T15:00:00Z',
  was_escalated: true,
};
