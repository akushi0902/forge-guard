import { Box, Text, UnstyledButton, Loader, Alert } from '@mantine/core';

import type { ConversationSummary } from '@/types/api';

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

interface ConversationSidebarProps {
  conversations: ConversationSummary[] | undefined;
  isLoading: boolean;
  isError: boolean;
  activeConversationId: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
}

export function ConversationSidebar({
  conversations,
  isLoading,
  isError,
  activeConversationId,
  onSelect,
  onRetry,
}: ConversationSidebarProps) {
  return (
    <Box
      data-testid="conversation-sidebar"
      style={{
        width: 240,
        borderRight: '1px solid var(--mantine-color-gray-2)',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
        background: 'var(--mantine-color-gray-0)',
      }}
    >
      <Box p="sm" style={{ borderBottom: '1px solid var(--mantine-color-gray-2)' }}>
        <Text fw={600} size="sm" c="dimmed" tt="uppercase" lts={0.5}>
          History
        </Text>
      </Box>

      {isLoading && (
        <Box p="md" style={{ display: 'flex', justifyContent: 'center' }}>
          <Loader size="sm" data-testid="conversations-loader" />
        </Box>
      )}

      {isError && (
        <Alert color="red" m="sm" data-testid="conversations-error">
          Failed to load conversations.{' '}
          <UnstyledButton onClick={onRetry} style={{ textDecoration: 'underline', color: 'inherit' }}>
            Retry
          </UnstyledButton>
        </Alert>
      )}

      {!isLoading && !isError && (!conversations || conversations.length === 0) && (
        <Text size="sm" c="dimmed" p="md" data-testid="no-conversations">
          No previous conversations.
        </Text>
      )}

      {conversations?.map((c) => (
        <UnstyledButton
          key={c.id}
          data-testid="conversation-item"
          onClick={() => onSelect(c.id)}
          style={{
            padding: '0.75rem 1rem',
            background:
              activeConversationId === c.id
                ? 'var(--mantine-color-blue-0)'
                : 'transparent',
            borderLeft:
              activeConversationId === c.id
                ? '3px solid var(--mantine-color-blue-5)'
                : '3px solid transparent',
          }}
        >
          <Text size="sm" lineClamp={2}>
            {c.preview}
          </Text>
          <Text size="xs" c="dimmed" mt={2}>
            {formatDate(c.updated_at)} · {c.message_count} msgs
          </Text>
        </UnstyledButton>
      ))}
    </Box>
  );
}
