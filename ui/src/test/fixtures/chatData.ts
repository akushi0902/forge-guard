import type { ChatMessage, ConversationSummary } from '@/types/api';

export const CHAT_CONVERSATION_ID = 'conv-fixture-001';

/** Conversation with a service health query + response. */
export const CHAT_MESSAGES_HEALTH: ChatMessage[] = [
  {
    id: 'msg-u-001',
    role: 'user',
    text: 'What is the health score for payments-service?',
    timestamp: '2026-08-13T08:00:00Z',
  },
  {
    id: 'msg-a-001',
    role: 'agent',
    text: 'The payments-service currently has a health score of **72/100**. There are 3 critical findings that need immediate attention.',
    context_refs: [
      {
        type: 'service',
        id: 'svc-payments-001',
        title: 'payments-service',
        metadata: { health_score: 72 },
      },
    ],
    is_template_fallback: false,
    timestamp: '2026-08-13T08:00:03Z',
  },
];

/** Conversation where agent references a finding. */
export const CHAT_MESSAGES_FINDING: ChatMessage[] = [
  {
    id: 'msg-u-002',
    role: 'user',
    text: 'Show me critical findings',
    timestamp: '2026-08-13T08:01:00Z',
  },
  {
    id: 'msg-a-002',
    role: 'agent',
    text: 'I found a critical SQL injection vulnerability in the query builder.',
    context_refs: [
      {
        type: 'finding',
        id: 'fnd-001',
        title: 'SQL injection vulnerability in query builder',
        metadata: { severity: 'critical' },
      },
    ],
    is_template_fallback: false,
    timestamp: '2026-08-13T08:01:04Z',
  },
];

/** Agent response in fallback / template mode. */
export const CHAT_MESSAGES_FALLBACK: ChatMessage[] = [
  {
    id: 'msg-u-003',
    role: 'user',
    text: 'What policies does my service violate?',
    timestamp: '2026-08-13T08:02:00Z',
  },
  {
    id: 'msg-a-003',
    role: 'agent',
    text: "I'm currently operating in limited mode due to reduced AI availability. Please check the dashboard directly for real-time service health and finding details.",
    context_refs: [],
    is_template_fallback: true,
    timestamp: '2026-08-13T08:02:05Z',
  },
];

/** Agent response containing credential-like strings for sanitization tests. */
export const RAW_CREDENTIAL_RESPONSES = [
  {
    label: 'Bearer token',
    input: 'Your auth header should be: Bearer eyJhbGciOiJIUzI1NiJ9.test.sig',
    expectedPattern: '[REDACTED]',
  },
  {
    label: 'OpenAI sk- key',
    input: 'Use the API key sk-ABCDEFGHIJKLMNOPQRSTUVWX to authenticate.',
    expectedPattern: '[REDACTED]',
  },
  {
    label: 'password= pattern',
    input: 'Connection: host=db.internal password=hunter2 port=5432',
    expectedPattern: '[REDACTED]',
  },
  {
    label: 'Postgres connection string',
    input: 'DATABASE_URL=postgresql://admin:supersecret@db.prod/forgeguard',
    expectedPattern: '[REDACTED]',
  },
];

export const CONVERSATION_SUMMARIES: ConversationSummary[] = [
  {
    id: CHAT_CONVERSATION_ID,
    preview: 'What is the health score for payments-service?',
    message_count: 2,
    created_at: '2026-08-13T08:00:00Z',
    updated_at: '2026-08-13T08:00:03Z',
  },
  {
    id: 'conv-fixture-002',
    preview: 'Show me critical findings',
    message_count: 2,
    created_at: '2026-08-12T14:00:00Z',
    updated_at: '2026-08-12T14:00:04Z',
  },
];
