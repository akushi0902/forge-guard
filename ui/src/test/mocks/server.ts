/**
 * MSW server for Vitest unit tests.
 *
 * Usage in test files:
 *   import { server } from '@/test/mocks/server';
 *   beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
 *   afterEach(() => server.resetHandlers());
 *   afterAll(() => server.close());
 */

import { setupServer } from 'msw/node';

import { authHandlers } from './handlers/auth';
import { findingHandlers } from './handlers/findings';
import { healthHandlers } from './handlers/health';
import { policyHandlers } from './handlers/policyHandlers';
import { rbacHandlers } from './handlers/rbacHandlers';
import { releaseHandlers } from './handlers/releases';
import { scoreHandlers } from './handlers/scores';
import { serviceHandlers } from './handlers/services';

export const server = setupServer(
  ...authHandlers,
  ...serviceHandlers,
  ...scoreHandlers,
  ...findingHandlers,
  ...releaseHandlers,
  ...healthHandlers,
  ...policyHandlers,
  ...rbacHandlers,
);
