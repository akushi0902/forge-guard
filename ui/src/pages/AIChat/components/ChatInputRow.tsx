import { useState, type KeyboardEvent } from 'react';
import { Box, TextInput, ActionIcon, Loader } from '@mantine/core';

interface ChatInputRowProps {
  onSubmit: (text: string) => void;
  isPending: boolean;
}

export function ChatInputRow({ onSubmit, isPending }: ChatInputRowProps) {
  const [value, setValue] = useState('');

  function handleSend() {
    const trimmed = value.trim();
    if (!trimmed || isPending) return;
    onSubmit(trimmed);
    setValue('');
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <Box
      data-testid="chat-input-row"
      style={{
        display: 'flex',
        gap: '0.5rem',
        padding: '0.75rem 1rem',
        borderTop: '1px solid var(--mantine-color-gray-2)',
      }}
    >
      <TextInput
        data-testid="chat-input"
        style={{ flex: 1 }}
        placeholder="Ask about your services, findings, or policies…"
        value={value}
        onChange={(e) => setValue(e.currentTarget.value)}
        onKeyDown={handleKeyDown}
        disabled={isPending}
        aria-label="Chat message input"
      />
      <ActionIcon
        data-testid="chat-send-button"
        size="input-sm"
        variant="filled"
        color="blue"
        onClick={handleSend}
        disabled={isPending || !value.trim()}
        aria-label="Send message"
      >
        {isPending ? <Loader size="xs" color="white" /> : '→'}
      </ActionIcon>
    </Box>
  );
}
