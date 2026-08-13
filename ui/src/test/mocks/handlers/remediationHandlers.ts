/**
 * MSW handlers for the RemediationDetail page (WO-082).
 *
 * Covers:
 *   GET  /api/v1/findings/:findingId          — finding detail
 *   GET  /api/v1/findings/:findingId/recommendation — AI recommendation
 *   POST /api/v1/findings/:findingId/re-evaluate   — re-evaluation
 *   POST /api/v1/findings/:findingId/exception     — exception request
 */

import { http, HttpResponse } from 'msw';

import {
  CRITICAL_FINDING_DETAIL,
  HIGH_CONFIDENCE_DETAIL_RECOMMENDATION,
  IMPROVED_REEVALUATION,
} from '@/test/fixtures/remediationData';

// ---------------------------------------------------------------------------
// Default handlers — use happy-path fixtures
// ---------------------------------------------------------------------------

export const remediationHandlers = [
  /** GET /api/v1/findings/:findingId — return finding detail */
  http.get('/api/v1/findings/:findingId', ({ params }) => {
    const { findingId } = params as { findingId: string };
    // Return 404 for the sentinel "not-found" ID used in tests
    if (findingId === 'not-found') {
      return HttpResponse.json(
        { detail: 'Finding not found', error_code: 'FINDING_NOT_FOUND' },
        { status: 404 },
      );
    }
    return HttpResponse.json({
      ...CRITICAL_FINDING_DETAIL,
      id: findingId,
    });
  }),

  /** GET /api/v1/findings/:findingId/recommendation — return recommendation */
  http.get('/api/v1/findings/:findingId/recommendation', ({ params }) => {
    const { findingId } = params as { findingId: string };
    // Return 404 for the sentinel "no-rec" ID used in tests
    if (findingId === 'no-rec') {
      return HttpResponse.json(
        {
          detail: 'Recommendation not yet available',
          error_code: 'RECOMMENDATION_NOT_FOUND',
        },
        { status: 404 },
      );
    }
    return HttpResponse.json({
      ...HIGH_CONFIDENCE_DETAIL_RECOMMENDATION,
      finding_id: findingId,
    });
  }),

  /** POST /api/v1/findings/:findingId/re-evaluate — return before/after result */
  http.post('/api/v1/findings/:findingId/re-evaluate', ({ params }) => {
    const { findingId } = params as { findingId: string };
    return HttpResponse.json({
      ...IMPROVED_REEVALUATION,
      finding_id: findingId,
    });
  }),

  /** POST /api/v1/findings/:findingId/exception — return created exception */
  http.post('/api/v1/findings/:findingId/exception', ({ params }) => {
    const { findingId } = params as { findingId: string };
    return HttpResponse.json(
      {
        id: 'exc-detail-001',
        finding_id: findingId,
        justification: 'Exception requested via remediation detail page.',
        status: 'pending',
        expires_at: null,
      },
      { status: 201 },
    );
  }),
];
