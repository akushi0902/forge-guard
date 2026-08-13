import { useEffect, useRef } from 'react';
import { Box, Text, Button } from '@mantine/core';

import type { ChatMessage } from '@/types/api';
import { MessageBubble } from './MessageBubble';

const SUGGESTED_QUERIES = [
  'What is my service health score?',
  'Show me critical findings',
  'What policies does my service violate?',
  'How do I fix the SQL injection vulnerability?',
];

interface ChatBodyProps {
  messages: ChatMessage[];
  isPending: boolean;
  onSuggestedQuery?: (query: string) => void;
}

export function ChatBody({ messages, isPending, onSuggestedQuery }: ChatBodyProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isPending]);

  if (messages.length === 0 && !isPending) {
    return (
      <Box
        data-testid="chat-body-empty"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          gap: '1rem',
        }}
      >
        <Text fw={600} size="lg">
          Welcome to ForgeGuard AI Agent
        </Text>
        <Text size="sm" c="dimmed" ta="center">
          Ask anything about your services, findings, or remediation guidance.
        </Text>
        <Box style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', justifyContent: 'center' }}>
          {SUGGESTED_QUERIES.map((q) => (
            <Button
              key={q}
              size="xs"
              variant="light"
              onClick={() => onSuggestedQuery?.(q)}
              data-testid="suggested-query-chip"
            >
              {q}
            </Button>
          ))}
        </Box>
      </Box>
    );
  }

  return (
    <Box
      data-testid="chat-body"
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      {isPending && (
        <Box
          data-testid="agent-typing-indicator"
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 0' }}
        >
          <Box
            style={{
              background: 'var(--mantine-color-gray-1)',
              borderRadius: 'var(--mantine-radius-md)',
              padding: '0.5rem 0.75rem',
            }}
          >
            <Text size="sm" c="dimmed">
              Agent is thinking…
            </Text>
          </Box>
        </Box>
      )}
      <div ref={bottomRef} />
    </Box>
  );
}
