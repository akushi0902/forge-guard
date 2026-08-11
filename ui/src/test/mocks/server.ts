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

import { findingHandlers } from './handlers/findings';
import { releaseHandlers } from './handlers/releases';
import { scoreHandlers } from './handlers/scores';
import { serviceHandlers } from './handlers/services';

export const server = setupServer(
  ...serviceHandlers,
  ...scoreHandlers,
  ...findingHandlers,
  ...releaseHandlers,
);
