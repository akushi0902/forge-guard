import { Drawer } from '@mantine/core';

import { useAgentQuery } from '@/hooks/api/useAgentQuery';
import { useConversations } from '@/hooks/api/useConversations';
import { useChatStore } from '@/stores/chatStore';
import { sanitizeCredentials } from '@/utils/credentialSanitizer';
import { ChatBody } from '@/pages/AIChat/components/ChatBody';
import { ChatHeader } from '@/pages/AIChat/components/ChatHeader';
import { ChatInputRow } from '@/pages/AIChat/components/ChatInputRow';

const FALLBACK_MESSAGE =
  "I'm currently operating in limited mode due to reduced AI availability. " +
  'Please check the dashboard directly for real-time service health and finding details.';

interface AIChatPanelProps {
  opened: boolean;
  onClose: () => void;
}

export function AIChatPanel({ opened, onClose }: AIChatPanelProps) {
  const { messages, conversationId, isPending, addUserMessage, addAgentResponse, setIsPending, clearConversation } =
    useChatStore();

  const agentQuery = useAgentQuery();

  useConversations(); // prefetch conversations list

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
          const fallbackResp = {
            answer:
              status === 503
                ? FALLBACK_MESSAGE
                : 'An error occurred. Please try again.',
            confidence: 0,
            context_refs: [],
            conversation_id: conversationId ?? 'unknown',
            is_template_fallback: status === 503,
            created_at: new Date().toISOString(),
          };
          addAgentResponse(fallbackResp);
        },
      },
    );
  }

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="md"
      title="AI Agent Chat"
      data-testid="ai-chat-panel"
      styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', height: '100%' } }}
    >
      <ChatHeader
        conversationId={conversationId}
        onNewConversation={clearConversation}
      />
      <ChatBody messages={messages} isPending={isPending} onSuggestedQuery={handleSubmit} />
      <ChatInputRow onSubmit={handleSubmit} isPending={isPending} />
    </Drawer>
  );
}
