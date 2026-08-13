/**
 * MSW handlers for Security Review page endpoints (WO-077).
 *
 * Endpoints covered:
 *   GET  /api/v1/findings?dimension=security   — security findings list
 *   GET  /api/v1/releases?status=escalated     — pending escalations
 *   GET  /api/v1/exceptions?status=pending     — pending exceptions
 *   POST /api/v1/exceptions/:id/decide         — exception approval/rejection
 *
 * NOTE: POST /api/v1/releases/:id/decide is already handled by releaseHandlers.
 * Tests that need security-specific block responses should use server.use() overrides.
 */

import { http, HttpResponse } from 'msw';

import {
  SECURITY_FINDINGS_PAGINATED,
  ESCALATIONS_PAGINATED,
  PENDING_EXCEPTIONS_PAGINATED,
} from '@/test/fixtures/securityFindings';

/** Default GET /api/v1/findings?dimension=security handler. */
const securityFindingsHandler = http.get('/api/v1/findings', ({ request }) => {
  const url = new URL(request.url);
  const dimension = url.searchParams.get('dimension');

  if (dimension === 'security') {
    return HttpResponse.json(SECURITY_FINDINGS_PAGINATED);
  }

  // Fall through to other handlers for non-security dimensions.
  return undefined;
});

/** GET /api/v1/releases?status=escalated */
const escalatedReleasesHandler = http.get('/api/v1/releases', ({ request }) => {
  const url = new URL(request.url);
  const status = url.searchParams.get('status');

  if (status === 'escalated') {
    return HttpResponse.json(ESCALATIONS_PAGINATED);
  }

  // Fall through for non-escalated release queries (handled by releaseHandlers).
  return undefined;
});

/** GET /api/v1/exceptions?status=pending */
const pendingExceptionsHandler = http.get('/api/v1/exceptions', ({ request }) => {
  const url = new URL(request.url);
  const status = url.searchParams.get('status');

  if (status === 'pending') {
    return HttpResponse.json(PENDING_EXCEPTIONS_PAGINATED);
  }

  return HttpResponse.json({ items: [], cursor: null, total_count: 0 });
});

/** POST /api/v1/exceptions/:id/decide — approve or reject an exception request. */
const exceptionDecideHandler = http.post(
  '/api/v1/exceptions/:id/decide',
  ({ params }) => {
    const id = params['id'] as string;
    return HttpResponse.json(
      {
        id,
        decision: 'approve',
        decided_at: '2026-08-12T16:00:00Z',
      },
      { status: 201 },
    );
  },
);

export const securityHandlers = [
  securityFindingsHandler,
  escalatedReleasesHandler,
  pendingExceptionsHandler,
  exceptionDecideHandler,
];
