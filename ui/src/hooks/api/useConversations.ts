import { useQuery } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type ConversationListResponse, type ConversationSummary } from '@/types/api';

export const conversationKeys = {
  all: ['agent', 'conversations'] as const,
  detail: (id: string) => ['agent', 'conversations', id] as const,
};

export function useConversations() {
  return useQuery({
    queryKey: conversationKeys.all,
    queryFn: () => apiClient<ConversationListResponse>('/api/v1/agent/conversations'),
  });
}

export function useConversation(id: string) {
  return useQuery({
    queryKey: conversationKeys.detail(id),
    queryFn: () => apiClient<ConversationSummary>(`/api/v1/agent/conversations/${id}`),
    enabled: Boolean(id),
  });
}
