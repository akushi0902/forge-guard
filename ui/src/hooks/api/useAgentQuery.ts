import { useMutation } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { type AgentQueryResponse } from '@/types/api';

export interface AgentQueryBody {
  query: string;
  conversation_id?: string;
  service_id?: string;
}

export const agentQueryKeys = {
  all: ['agent'] as const,
};

export function useAgentQuery() {
  return useMutation({
    mutationFn: (body: AgentQueryBody) =>
      apiClient<AgentQueryResponse>('/api/v1/agent/query', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  });
}
