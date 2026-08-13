import { create } from 'zustand';

import type { AgentQueryResponse, ChatMessage } from '@/types/api';

function newId(): string {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

interface ChatState {
  messages: ChatMessage[];
  conversationId: string | null;
  isPending: boolean;
}

interface ChatActions {
  addUserMessage: (text: string) => string;
  addAgentResponse: (response: AgentQueryResponse) => void;
  setConversationId: (id: string) => void;
  setIsPending: (pending: boolean) => void;
  clearConversation: () => void;
}

type ChatStore = ChatState & ChatActions;

const initialState: ChatState = {
  messages: [],
  conversationId: null,
  isPending: false,
};

export const useChatStore = create<ChatStore>()((set) => ({
  ...initialState,

  addUserMessage: (text) => {
    const id = newId();
    const msg: ChatMessage = {
      id,
      role: 'user',
      text,
      timestamp: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, msg] }));
    return id;
  },

  addAgentResponse: (response) => {
    const msg: ChatMessage = {
      id: newId(),
      role: 'agent',
      text: response.answer,
      context_refs: response.context_refs,
      is_template_fallback: response.is_template_fallback,
      timestamp: response.created_at,
    };
    set((s) => ({
      messages: [...s.messages, msg],
      conversationId: response.conversation_id,
      isPending: false,
    }));
  },

  setConversationId: (id) => set({ conversationId: id }),
  setIsPending: (pending) => set({ isPending: pending }),

  clearConversation: () => set({ ...initialState }),
}));
