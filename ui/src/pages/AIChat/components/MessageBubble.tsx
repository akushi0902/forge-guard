import { Box, Text, Badge } from '@mantine/core';

import type { ChatMessage, ContextReference } from '@/types/api';

interface ContextualCardProps {
  ctxRef: ContextReference;
}

function ContextualCard({ ctxRef }: ContextualCardProps) {
  const meta = ctxRef.metadata ?? {};

  return (
    <Box
      data-testid="contextual-card"
      mt="xs"
      p="xs"
      style={{
        border: '1px solid var(--mantine-color-gray-3)',
        borderRadius: 'var(--mantine-radius-sm)',
        background: 'var(--mantine-color-gray-0)',
        display: 'inline-block',
        maxWidth: 260,
      }}
    >
      <Text size="xs" fw={600} c="dimmed" tt="uppercase" lts={0.5}>
        {ctxRef.type}
      </Text>
      <Text size="sm" fw={500}>
        {ctxRef.title}
      </Text>
      {ctxRef.type === 'service' && typeof meta.health_score === 'number' && (
        <Text size="xs" c="dimmed">
          Health: {meta.health_score}/100
        </Text>
      )}
      {ctxRef.type === 'finding' && typeof meta.severity === 'string' && (
        <Badge size="xs" color="red" variant="light" mt={2}>
          {meta.severity}
        </Badge>
      )}
    </Box>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const refs = message.context_refs ?? [];

  return (
    <Box
      data-testid={isUser ? 'user-message-bubble' : 'agent-message-bubble'}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: isUser ? 'flex-end' : 'flex-start',
        marginBottom: '0.75rem',
      }}
    >
      <Box
        style={{
          maxWidth: '75%',
          background: isUser
            ? 'var(--mantine-color-blue-6)'
            : 'var(--mantine-color-gray-1)',
          color: isUser ? 'white' : 'inherit',
          borderRadius: 'var(--mantine-radius-md)',
          padding: '0.5rem 0.75rem',
        }}
      >
        <Text
          size="sm"
          style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
          data-testid="message-text"
        >
          {message.text}
        </Text>
        {message.is_template_fallback && (
          <Badge
            size="xs"
            color="yellow"
            variant="light"
            mt="xs"
            data-testid="fallback-badge"
          >
            Limited mode
          </Badge>
        )}
      </Box>
      {refs.length > 0 && (
        <Box
          mt="xs"
          style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', maxWidth: '75%' }}
        >
          {refs.map((r) => (
            <ContextualCard key={r.id} ctxRef={r} />
          ))}
        </Box>
      )}
      <Text size="xs" c="dimmed" mt={2}>
        {new Date(message.timestamp).toLocaleTimeString()}
      </Text>
    </Box>
  );
}
