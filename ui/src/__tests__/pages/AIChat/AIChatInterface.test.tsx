/**
 * Tests for WO-084: AI Agent Natural Language Chat Interface.
 *
 * Covers:
 *   AC-1  Page layout — ConversationSidebar + ChatArea with ChatHeader, empty
 *          ChatBody (welcome + suggested chips), ChatInputRow
 *   AC-2  Message submission — user bubble appears immediately, agent bubble
 *          after API returns
 *   AC-3  ContextualCard — rendered when agent response includes entity refs
 *   AC-4  LLM fallback — template message on 503
 *   AC-5  AIChatFAB — toggle opens/closes AIChatPanel
 *   AC-6  New Conversation — clears chat body
 *   AC-7  Credential sanitization — regex patterns masked
 *   AC-8  Unit tests for sub-components
 *   AC-9  TanStack Query hooks integration via MSW
 *   AC-10 Fixture coverage
 */

import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { screen, waitFor, fireEvent, act } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import { render } from '@/test-utils';
import { server } from '@/test/mocks/server';
import { AIChatInterface } from '@/pages/AIChat/AIChatInterface';
import { MessageBubble } from '@/pages/AIChat/components/MessageBubble';
import { ChatBody } from '@/pages/AIChat/components/ChatBody';
import { ChatInputRow } from '@/pages/AIChat/components/ChatInputRow';
import { ChatHeader } from '@/pages/AIChat/components/ChatHeader';
import { ConversationSidebar } from '@/pages/AIChat/components/ConversationSidebar';
import { AIChatFAB } from '@/components/AIChatFAB/AIChatFAB';
import { sanitizeCredentials } from '@/utils/credentialSanitizer';
import {
  MOCK_AGENT_RESPONSE,
  MOCK_CONVERSATION_LIST,
  MOCK_AGENT_FALLBACK_RESPONSE,
  agentLlmUnavailableHandler,
  agentServerErrorHandler,
  MOCK_AGENT_RESPONSE_WITH_FINDING,
} from '@/test/mocks/handlers/agentHandlers';
import {
  CHAT_MESSAGES_HEALTH,
  CHAT_MESSAGES_FALLBACK,
  CONVERSATION_SUMMARIES,
  RAW_CREDENTIAL_RESPONSES,
} from '@/test/fixtures/chatData';
import type { ChatMessage } from '@/types/api';

// ---------------------------------------------------------------------------
// MSW lifecycle
// ---------------------------------------------------------------------------
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// ---------------------------------------------------------------------------
// Helper — reset Zustand chat store between tests
// ---------------------------------------------------------------------------
import { useChatStore } from '@/stores/chatStore';
afterEach(() => {
  useChatStore.getState().clearConversation();
});

// ==========================================================================
// AC-7 — Credential Sanitization (pure unit, no React needed)
// ==========================================================================
describe('sanitizeCredentials', () => {
  it('redacts Bearer tokens', () => {
    const result = sanitizeCredentials(
      'Auth: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig',
    );
    expect(result).toContain('[REDACTED]');
    expect(result).not.toContain('eyJhbGciOiJIUzI1NiJ9');
  });

  it('redacts sk- API keys', () => {
    const result = sanitizeCredentials('Use sk-ABCDEFGHIJKLMNOPQRSTUVWX to auth.');
    expect(result).toContain('[REDACTED]');
    expect(result).not.toContain('sk-ABCDEF');
  });

  it('redacts password= patterns', () => {
    const result = sanitizeCredentials('Connection: password=hunter2 host=localhost');
    expect(result).toContain('[REDACTED]');
    expect(result).not.toContain('hunter2');
  });

  it('redacts Postgres connection strings', () => {
    const result = sanitizeCredentials(
      'postgresql://admin:supersecret@db.prod/forgeguard',
    );
    expect(result).toContain('[REDACTED]');
    expect(result).not.toContain('supersecret');
  });

  it('leaves safe text unchanged', () => {
    const safe = 'The health score is 72/100. Three critical findings were found.';
    expect(sanitizeCredentials(safe)).toBe(safe);
  });

  it('handles all fixture credential patterns', () => {
    for (const { input, expectedPattern } of RAW_CREDENTIAL_RESPONSES) {
      const result = sanitizeCredentials(input);
      expect(result).toContain(expectedPattern);
    }
  });
});

// ==========================================================================
// AC-8 — MessageBubble unit tests
// ==========================================================================
describe('MessageBubble', () => {
  const userMsg: ChatMessage = {
    id: 'u1',
    role: 'user',
    text: 'Hello agent',
    timestamp: '2026-08-13T08:00:00Z',
  };
  const agentMsg: ChatMessage = {
    id: 'a1',
    role: 'agent',
    text: 'Hello user',
    timestamp: '2026-08-13T08:00:02Z',
  };

  it('renders user message bubble', () => {
    render(<MessageBubble message={userMsg} />);
    expect(screen.getByTestId('user-message-bubble')).toBeInTheDocument();
    expect(screen.getByTestId('message-text')).toHaveTextContent('Hello agent');
  });

  it('renders agent message bubble', () => {
    render(<MessageBubble message={agentMsg} />);
    expect(screen.getByTestId('agent-message-bubble')).toBeInTheDocument();
    expect(screen.getByTestId('message-text')).toHaveTextContent('Hello user');
  });

  it('shows fallback badge for template fallback messages', () => {
    const fallback: ChatMessage = {
      ...agentMsg,
      is_template_fallback: true,
    };
    render(<MessageBubble message={fallback} />);
    expect(screen.getByTestId('fallback-badge')).toBeInTheDocument();
  });

  it('renders contextual cards when context_refs present', () => {
    render(<MessageBubble message={CHAT_MESSAGES_HEALTH[1]} />);
    expect(screen.getAllByTestId('contextual-card').length).toBeGreaterThan(0);
  });

  it('shows service health score in contextual card', () => {
    render(<MessageBubble message={CHAT_MESSAGES_HEALTH[1]} />);
    expect(screen.getByText(/72\/100/i)).toBeInTheDocument();
  });
});

// ==========================================================================
// AC-8 — ChatInputRow unit tests
// ==========================================================================
describe('ChatInputRow', () => {
  it('renders input and send button', () => {
    render(<ChatInputRow onSubmit={() => {}} isPending={false} />);
    expect(screen.getByTestId('chat-input')).toBeInTheDocument();
    expect(screen.getByTestId('chat-send-button')).toBeInTheDocument();
  });

  it('disables input and send when isPending=true', () => {
    render(<ChatInputRow onSubmit={() => {}} isPending={true} />);
    const input = screen.getByTestId('chat-input').querySelector('input');
    expect(input).toBeDisabled();
    expect(screen.getByTestId('chat-send-button')).toBeDisabled();
  });

  it('calls onSubmit with trimmed text on click', () => {
    const onSubmit = vi.fn();
    render(<ChatInputRow onSubmit={onSubmit} isPending={false} />);
    const input = screen.getByTestId('chat-input').querySelector('input')!;
    fireEvent.change(input, { target: { value: '  hello  ' } });
    fireEvent.click(screen.getByTestId('chat-send-button'));
    expect(onSubmit).toHaveBeenCalledWith('hello');
  });

  it('calls onSubmit on Enter key', () => {
    const onSubmit = vi.fn();
    render(<ChatInputRow onSubmit={onSubmit} isPending={false} />);
    const input = screen.getByTestId('chat-input').querySelector('input')!;
    fireEvent.change(input, { target: { value: 'test query' } });
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' });
    expect(onSubmit).toHaveBeenCalledWith('test query');
  });

  it('does not submit empty string', () => {
    const onSubmit = vi.fn();
    render(<ChatInputRow onSubmit={onSubmit} isPending={false} />);
    fireEvent.click(screen.getByTestId('chat-send-button'));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

// ==========================================================================
// AC-8 — ChatBody unit tests
// ==========================================================================
describe('ChatBody', () => {
  it('shows welcome / empty state when no messages', () => {
    render(<ChatBody messages={[]} isPending={false} />);
    expect(screen.getByTestId('chat-body-empty')).toBeInTheDocument();
    expect(screen.getByText(/Welcome to ForgeGuard AI Agent/i)).toBeInTheDocument();
  });

  it('renders suggested query chips in empty state', () => {
    render(<ChatBody messages={[]} isPending={false} />);
    const chips = screen.getAllByTestId('suggested-query-chip');
    expect(chips.length).toBeGreaterThan(0);
  });

  it('calls onSuggestedQuery when chip clicked', () => {
    const onSuggestedQuery = vi.fn();
    render(<ChatBody messages={[]} isPending={false} onSuggestedQuery={onSuggestedQuery} />);
    const chip = screen.getAllByTestId('suggested-query-chip')[0];
    fireEvent.click(chip);
    expect(onSuggestedQuery).toHaveBeenCalledWith(expect.any(String));
  });

  it('renders messages when present', () => {
    render(<ChatBody messages={CHAT_MESSAGES_HEALTH} isPending={false} />);
    expect(screen.getByTestId('chat-body')).toBeInTheDocument();
    expect(screen.getAllByTestId(/message-bubble/i).length).toBe(2);
  });

  it('shows typing indicator when isPending=true', () => {
    render(<ChatBody messages={CHAT_MESSAGES_HEALTH} isPending={true} />);
    expect(screen.getByTestId('agent-typing-indicator')).toBeInTheDocument();
  });
});

// ==========================================================================
// AC-8 — ChatHeader unit tests
// ==========================================================================
describe('ChatHeader', () => {
  it('renders New Conversation button', () => {
    render(<ChatHeader conversationId={null} onNewConversation={() => {}} />);
    expect(screen.getByTestId('new-conversation-btn')).toBeInTheDocument();
  });

  it('calls onNewConversation when button clicked', () => {
    const onNew = vi.fn();
    render(<ChatHeader conversationId={null} onNewConversation={onNew} />);
    fireEvent.click(screen.getByTestId('new-conversation-btn'));
    expect(onNew).toHaveBeenCalledOnce();
  });

  it('shows online badge', () => {
    render(<ChatHeader conversationId={null} onNewConversation={() => {}} />);
    expect(screen.getByTestId('online-badge')).toBeInTheDocument();
  });
});

// ==========================================================================
// AC-8, AC-9 — ConversationSidebar
// ==========================================================================
describe('ConversationSidebar', () => {
  it('renders loading state', () => {
    render(
      <ConversationSidebar
        conversations={undefined}
        isLoading={true}
        isError={false}
        activeConversationId={null}
        onSelect={() => {}}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByTestId('conversations-loader')).toBeInTheDocument();
  });

  it('renders error state with retry', () => {
    const onRetry = vi.fn();
    render(
      <ConversationSidebar
        conversations={undefined}
        isLoading={false}
        isError={true}
        activeConversationId={null}
        onSelect={() => {}}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByTestId('conversations-error')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Retry'));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('renders empty state message', () => {
    render(
      <ConversationSidebar
        conversations={[]}
        isLoading={false}
        isError={false}
        activeConversationId={null}
        onSelect={() => {}}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByTestId('no-conversations')).toBeInTheDocument();
  });

  it('renders conversation list items', () => {
    render(
      <ConversationSidebar
        conversations={CONVERSATION_SUMMARIES}
        isLoading={false}
        isError={false}
        activeConversationId={null}
        onSelect={() => {}}
        onRetry={() => {}}
      />,
    );
    const items = screen.getAllByTestId('conversation-item');
    expect(items.length).toBe(CONVERSATION_SUMMARIES.length);
  });

  it('calls onSelect when conversation item clicked', () => {
    const onSelect = vi.fn();
    render(
      <ConversationSidebar
        conversations={CONVERSATION_SUMMARIES}
        isLoading={false}
        isError={false}
        activeConversationId={null}
        onSelect={onSelect}
        onRetry={() => {}}
      />,
    );
    fireEvent.click(screen.getAllByTestId('conversation-item')[0]);
    expect(onSelect).toHaveBeenCalledWith(CONVERSATION_SUMMARIES[0].id);
  });
});

// ==========================================================================
// AC-5 — AIChatFAB unit tests
// ==========================================================================
describe('AIChatFAB', () => {
  it('renders the FAB button', () => {
    render(<AIChatFAB />);
    expect(screen.getByTestId('ai-chat-fab')).toBeInTheDocument();
  });

  it('opens AIChatPanel when FAB clicked', async () => {
    render(<AIChatFAB />);
    fireEvent.click(screen.getByTestId('ai-chat-fab'));
    await waitFor(() => {
      expect(screen.getByTestId('ai-chat-panel')).toBeInTheDocument();
    });
  });
});

// ==========================================================================
// AC-1, AC-2, AC-3, AC-4, AC-6, AC-9, AC-10 — Full integration tests
// ==========================================================================
describe('AIChatInterface integration', () => {
  it('AC-1: renders layout — sidebar, header, empty body, input row', async () => {
    render(<AIChatInterface />);
    await waitFor(() => {
      expect(screen.getByTestId('conversation-sidebar')).toBeInTheDocument();
    });
    expect(screen.getByTestId('chat-header')).toBeInTheDocument();
    expect(screen.getByTestId('chat-body-empty')).toBeInTheDocument();
    expect(screen.getByTestId('chat-input-row')).toBeInTheDocument();
  });

  it('AC-9: loads conversation list from API', async () => {
    render(<AIChatInterface />);
    await waitFor(() => {
      const items = screen.getAllByTestId('conversation-item');
      expect(items.length).toBe(MOCK_CONVERSATION_LIST.items.length);
    });
  });

  it('AC-2: user message appears immediately; agent message after API returns', async () => {
    render(<AIChatInterface />);
    await waitFor(() => screen.getByTestId('chat-input-row'));

    const input = screen.getByTestId('chat-input').querySelector('input')!;
    fireEvent.change(input, { target: { value: 'What is my health score?' } });
    fireEvent.click(screen.getByTestId('chat-send-button'));

    // User bubble is optimistically rendered immediately
    expect(screen.getByTestId('user-message-bubble')).toBeInTheDocument();
    expect(screen.getByTestId('agent-typing-indicator')).toBeInTheDocument();

    // Agent bubble after API resolves
    await waitFor(() => {
      expect(screen.getByTestId('agent-message-bubble')).toBeInTheDocument();
    });
    expect(screen.getByText(MOCK_AGENT_RESPONSE.answer)).toBeInTheDocument();
  });

  it('AC-3: ContextualCard renders when agent references an entity', async () => {
    server.use(
      http.post('/api/v1/agent/query', () =>
        HttpResponse.json(MOCK_AGENT_RESPONSE_WITH_FINDING),
      ),
    );
    render(<AIChatInterface />);
    await waitFor(() => screen.getByTestId('chat-input-row'));

    const input = screen.getByTestId('chat-input').querySelector('input')!;
    fireEvent.change(input, { target: { value: 'Show critical findings' } });
    fireEvent.click(screen.getByTestId('chat-send-button'));

    await waitFor(() => {
      expect(screen.getByTestId('contextual-card')).toBeInTheDocument();
    });
  });

  it('AC-4: shows template fallback message when 503 returned', async () => {
    server.use(agentLlmUnavailableHandler);
    render(<AIChatInterface />);
    await waitFor(() => screen.getByTestId('chat-input-row'));

    const input = screen.getByTestId('chat-input').querySelector('input')!;
    fireEvent.change(input, { target: { value: 'Any question' } });
    fireEvent.click(screen.getByTestId('chat-send-button'));

    await waitFor(() => {
      expect(screen.getByTestId('agent-message-bubble')).toBeInTheDocument();
    });
    expect(screen.getByTestId('fallback-badge')).toBeInTheDocument();
    expect(screen.getByText(/limited mode/i)).toBeInTheDocument();
  });

  it('AC-6: New Conversation button clears chat body', async () => {
    render(<AIChatInterface />);
    await waitFor(() => screen.getByTestId('chat-input-row'));

    // Send a message first
    const input = screen.getByTestId('chat-input').querySelector('input')!;
    fireEvent.change(input, { target: { value: 'test' } });
    fireEvent.click(screen.getByTestId('chat-send-button'));
    await waitFor(() => screen.getByTestId('user-message-bubble'));

    // Click new conversation
    fireEvent.click(screen.getByTestId('new-conversation-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('chat-body-empty')).toBeInTheDocument();
    });
  });

  it('AC-7: credential sanitization applied to agent responses', async () => {
    server.use(
      http.post('/api/v1/agent/query', () =>
        HttpResponse.json({
          ...MOCK_AGENT_RESPONSE,
          answer: 'Use Bearer eyJhbGciOiJIUzI1NiJ9.test.sig to authenticate',
        }),
      ),
    );
    render(<AIChatInterface />);
    await waitFor(() => screen.getByTestId('chat-input-row'));

    const input = screen.getByTestId('chat-input').querySelector('input')!;
    fireEvent.change(input, { target: { value: 'auth help' } });
    fireEvent.click(screen.getByTestId('chat-send-button'));

    await waitFor(() => {
      expect(screen.getByTestId('agent-message-bubble')).toBeInTheDocument();
    });

    const messageText = screen.getByTestId('message-text');
    expect(messageText.textContent).toContain('[REDACTED]');
    expect(messageText.textContent).not.toContain('eyJhbGciOiJIUzI1NiJ9');
  });

  it('input is disabled while query is pending', async () => {
    // Use a handler that never resolves quickly (we check synchronous pending state)
    render(<AIChatInterface />);
    await waitFor(() => screen.getByTestId('chat-input-row'));

    const input = screen.getByTestId('chat-input').querySelector('input')!;
    fireEvent.change(input, { target: { value: 'test' } });
    fireEvent.click(screen.getByTestId('chat-send-button'));

    // Immediately after click, input should be disabled (isPending=true in store)
    expect(input).toBeDisabled();

    // Wait for resolution to restore
    await waitFor(() => expect(input).not.toBeDisabled());
  });
});
