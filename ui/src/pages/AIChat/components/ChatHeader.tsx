import { Box, Text, Button, Badge } from '@mantine/core';

interface ChatHeaderProps {
  conversationId: string | null;
  onNewConversation: () => void;
}

export function ChatHeader({ conversationId, onNewConversation }: ChatHeaderProps) {
  return (
    <Box
      data-testid="chat-header"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.75rem 1rem',
        borderBottom: '1px solid var(--mantine-color-gray-2)',
        background: 'var(--mantine-color-body)',
      }}
    >
      <Box style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Text fw={600} size="md">
          {conversationId ? `Conversation` : 'New Conversation'}
        </Text>
        <Badge size="xs" color="green" variant="dot" data-testid="online-badge">
          Online
        </Badge>
      </Box>
      <Button
        size="xs"
        variant="light"
        onClick={onNewConversation}
        data-testid="new-conversation-btn"
      >
        New Conversation
      </Button>
    </Box>
  );
}
