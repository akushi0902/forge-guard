import { useState } from 'react';
import { ActionIcon, Tooltip } from '@mantine/core';

import { AIChatPanel } from './AIChatPanel';

export function AIChatFAB() {
  const [opened, setOpened] = useState(false);

  return (
    <>
      <Tooltip label="AI Agent Chat" position="left">
        <ActionIcon
          data-testid="ai-chat-fab"
          size="xl"
          radius="xl"
          variant="filled"
          color="blue"
          onClick={() => setOpened(true)}
          style={{
            position: 'fixed',
            bottom: '1.5rem',
            right: '1.5rem',
            zIndex: 1000,
            boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
          }}
          aria-label="Open AI Agent Chat"
        >
          🤖
        </ActionIcon>
      </Tooltip>

      <AIChatPanel opened={opened} onClose={() => setOpened(false)} />
    </>
  );
}
