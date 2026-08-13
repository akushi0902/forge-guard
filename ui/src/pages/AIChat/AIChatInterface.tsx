import { Box, Text } from '@mantine/core';

import { useAgentQuery } from '@/hooks/api/useAgentQuery';
import { useConversations } from '@/hooks/api/useConversations';
import { useChatStore } from '@/stores/chatStore';
import { sanitizeCredentials } from '@/utils/credentialSanitizer';

import { ChatBody } from './components/ChatBody';
import { ChatHeader } from './components/ChatHeader';
import { ChatInputRow } from './components/ChatInputRow';
import { ConversationSidebar } from './components/ConversationSidebar';

const FALLBACK_MESSAGE =
  "I'm currently operating in limited mode due to reduced AI availability. " +
  'Please check the dashboard directly for real-time service health and finding details.';

export function AIChatInterface() {
  const { messages, conversationId, isPending, addUserMessage, addAgentResponse, setIsPending, clearConversation } =
    useChatStore();

  const { data: conversationsData, isLoading, isError, refetch } = useConversations();

  const agentQuery = useAgentQuery();

  function handleSubmit(text: string) {
    addUserMessage(text);
    setIsPending(true);

    agentQuery.mutate(
      { query: text, conversation_id: conversationId ?? undefined },
      {
        onSuccess: (resp) => {
          const sanitized = { ...resp, answer: sanitizeCredentials(resp.answer) };
          addAgentResponse(sanitized);
        },
        onError: (err: unknown) => {
          const status = (err as { status?: number }).status;
          const isLlmUnavailable = status === 503;
          const fallbackResp = {
            answer: isLlmUnavailable
              ? FALLBACK_MESSAGE
              : 'An error occurred while processing your request. Please try again.',
            confidence: 0,
            context_refs: [],
            conversation_id: conversationId ?? 'unknown',
            is_template_fallback: isLlmUnavailable,
            created_at: new Date().toISOString(),
          };
          addAgentResponse(fallbackResp);
        },
      },
    );
  }

  function handleNewConversation() {
    clearConversation();
  }

  function handleConversationSelect(id: string) {
    clearConversation();
    useChatStore.getState().setConversationId(id);
  }

  return (
    <Box
      data-testid="ai-chat-interface"
      style={{
        display: 'flex',
        height: 'calc(100vh - 60px)',
        overflow: 'hidden',
      }}
    >
      <ConversationSidebar
        conversations={conversationsData?.items}
        isLoading={isLoading}
        isError={isError}
        activeConversationId={conversationId}
        onSelect={handleConversationSelect}
        onRetry={() => void refetch()}
      />

      <Box
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <ChatHeader
          conversationId={conversationId}
          onNewConversation={handleNewConversation}
        />
        <ChatBody
          messages={messages}
          isPending={isPending}
          onSuggestedQuery={handleSubmit}
        />
        <ChatInputRow onSubmit={handleSubmit} isPending={isPending} />
      </Box>
    </Box>
  );
}
