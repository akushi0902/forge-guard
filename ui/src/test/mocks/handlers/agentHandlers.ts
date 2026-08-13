import { http, HttpResponse } from 'msw';

import type {
  AgentQueryResponse,
  ConversationListResponse,
  ConversationSummary,
} from '@/types/api';

export const CONVERSATION_ID = 'conv-001';
export const CONVERSATION_ID_2 = 'conv-002';

export const MOCK_CONVERSATION_LIST: ConversationListResponse = {
  items: [
    {
      id: CONVERSATION_ID,
      preview: 'What is the health score for my service?',
      message_count: 4,
      created_at: '2026-08-12T10:00:00Z',
      updated_at: '2026-08-12T10:05:00Z',
    },
    {
      id: CONVERSATION_ID_2,
      preview: 'Show me critical findings for payments-service',
      message_count: 2,
      created_at: '2026-08-11T09:00:00Z',
      updated_at: '2026-08-11T09:03:00Z',
    },
  ],
  next_cursor: null,
};

export const MOCK_AGENT_RESPONSE: AgentQueryResponse = {
  answer:
    'The payments-service currently has a health score of 72/100. There are 3 critical findings that need immediate attention.',
  confidence: 0.91,
  context_refs: [
    {
      type: 'service',
      id: 'svc-payments-001',
      title: 'payments-service',
      metadata: { health_score: 72 },
    },
  ],
  conversation_id: CONVERSATION_ID,
  is_template_fallback: false,
  created_at: '2026-08-13T08:00:00Z',
};

export const MOCK_AGENT_RESPONSE_WITH_FINDING: AgentQueryResponse = {
  answer:
    'I found a critical SQL injection vulnerability in the query builder. You should prioritize fixing this immediately.',
  confidence: 0.88,
  context_refs: [
    {
      type: 'finding',
      id: 'fnd-001',
      title: 'SQL injection vulnerability in query builder',
      metadata: { severity: 'critical' },
    },
  ],
  conversation_id: CONVERSATION_ID,
  is_template_fallback: false,
  created_at: '2026-08-13T08:01:00Z',
};

export const MOCK_AGENT_FALLBACK_RESPONSE: AgentQueryResponse = {
  answer:
    'I'm currently operating in limited mode due to reduced AI availability. Please check the dashboard directly for real-time service health and finding details.',
  confidence: 0.0,
  context_refs: [],
  conversation_id: CONVERSATION_ID,
  is_template_fallback: true,
  created_at: '2026-08-13T08:02:00Z',
};

export const agentHandlers = [
  http.post('/api/v1/agent/query', () => HttpResponse.json(MOCK_AGENT_RESPONSE)),

  http.get('/api/v1/agent/conversations', () =>
    HttpResponse.json(MOCK_CONVERSATION_LIST),
  ),

  http.get('/api/v1/agent/conversations/:id', ({ params }) => {
    const item =
      MOCK_CONVERSATION_LIST.items.find((c) => c.id === params.id) ??
      MOCK_CONVERSATION_LIST.items[0];
    return HttpResponse.json(item);
  }),
];

/** Override handler — POST returns 503 LLM unavailable. */
export const agentLlmUnavailableHandler = http.post(
  '/api/v1/agent/query',
  () => new HttpResponse(null, { status: 503 }),
);

/** Override handler — POST returns 500 server error. */
export const agentServerErrorHandler = http.post(
  '/api/v1/agent/query',
  () => new HttpResponse(null, { status: 500 }),
);
