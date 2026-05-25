import { apiClient } from './client'

export interface TemplateEvent {
  name: string
  payload: {
    event_schema_type: 'json' | 'string'
    value?: Record<string, string> | string
  }
}

export interface AgentTemplate {
  name: string          // machine identifier
  display_name: string
  description: string
  is_long_running: boolean
  events: TemplateEvent[]
  tools: string[]
  mcp_servers: string[]
}

export interface Agent {
  id: string
  org_id: string
  workflow_id: string | null
  name: string
  type: string
  config: Record<string, unknown>
  is_active: boolean
  created_by: string
  created_at: string
  updated_at: string | null
}

export const agentsApi = {
  listTemplates: () => apiClient.get<AgentTemplate[]>('/api/agents/templates').then(r => r.data),
  getTemplate: (name: string) => apiClient.get<AgentTemplate>(`/api/agents/templates/${name}`).then(r => r.data),
  list: (workflowId?: string) => {
    const params = workflowId ? `?workflow_id=${workflowId}` : ''
    return apiClient.get<Agent[]>(`/api/agents${params}`).then(r => r.data)
  },
  get: (id: string) => apiClient.get<Agent>(`/api/agents/${id}`).then(r => r.data),
  create: (data: { id?: string; workflow_id?: string; name: string; type: string; config: Record<string, unknown> }) =>
    apiClient.post<Agent>('/api/agents', data).then(r => r.data),
  update: (id: string, data: { name?: string; config?: Record<string, unknown> }) =>
    apiClient.patch<Agent>(`/api/agents/${id}`, data).then(r => r.data),
  delete: (id: string) => apiClient.delete(`/api/agents/${id}`),
}
