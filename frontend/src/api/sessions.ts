import { apiClient } from './client'

export interface AgentMessage {
  id: string
  session_id: string
  sender_type: string
  sender_ref_id: string
  sender_name: string
  recipient_type: string
  recipient_ref_id: string
  recipient_name: string
  event_name: string
  payload: Record<string, unknown> | null
  status: string
  created_at: string
}

export interface Session {
  id: string
  workflow_id: string
  trigger_event: string
  trigger_payload: Record<string, unknown> | null
  status: string
  started_at: string
  ended_at: string | null
  messages?: AgentMessage[]
}

export const sessionsApi = {
  get: (id: string) => apiClient.get<Session>(`/api/sessions/${id}`).then(r => r.data),
  listMessages: (id: string) => apiClient.get<AgentMessage[]>(`/api/sessions/${id}/messages`).then(r => r.data),
  create: (data: { workflow_id: string; trigger_event: string; trigger_payload?: Record<string, unknown> }) =>
    apiClient.post<Session>('/api/sessions', data).then(r => r.data),
}
