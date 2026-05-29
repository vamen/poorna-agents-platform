import { apiClient } from './client'

export type Provider = 'openai' | 'anthropic' | 'google' | 'azure' | 'ollama'
export type Strategy = 'predict' | 'cot' | 'react'

export interface EventPayload {
  event_schema_type: 'json' | 'string'
  value?: Record<string, string> | string
}

export interface EventSchema {
  name: string
  payload: EventPayload
}

export interface ModelEntry {
  provider: Provider
  name: string
}

export interface ModelEntryResponse {
  provider: Provider
  name: string
}

export interface PromptSchema {
  system: string
  user: string
}

export interface ReasoningCreate {
  strategy: Strategy
  max_iterations?: number
  model: ModelEntry[]
  prompt: PromptSchema
  tools: string[]
  mcp_servers: string[]
  context_messages: number
}

export interface ReasoningResponse {
  strategy: Strategy
  max_iterations?: number
  model: ModelEntryResponse[]
  prompt: PromptSchema
  tools: string[]
  mcp_servers: string[]
  context_messages: number
}

export interface AgentDefinitionCreate {
  name: string
  display_name: string
  description?: string
  is_long_running: boolean
  reasoning: ReasoningCreate
  events: EventSchema[]
}

export interface AgentDefinitionUpdate {
  display_name?: string
  description?: string
  is_long_running?: boolean
  reasoning?: ReasoningCreate
  events?: EventSchema[]
}

export interface AgentDefinitionResponse {
  id: string
  org_id: string
  name: string
  display_name: string
  description: string | null
  is_long_running: boolean
  reasoning: ReasoningResponse
  events: EventSchema[]
  created_by: string
  updated_by: string | null
  created_at: string
  updated_at: string | null
}

export interface ToolDefinition {
  name: string
  description: string
  parameters: Record<string, unknown>
  phase2_only: boolean
}

export const agentDefinitionsApi = {
  getSchema: () =>
    apiClient.get<Record<string, unknown>>('/api/agent-definitions/schema').then(r => r.data),

  listTools: () =>
    apiClient.get<ToolDefinition[]>('/api/agent-definitions/tools').then(r => r.data),

  list: () =>
    apiClient.get<AgentDefinitionResponse[]>('/api/agent-definitions').then(r => r.data),

  get: (id: string) =>
    apiClient.get<AgentDefinitionResponse>(`/api/agent-definitions/${id}`).then(r => r.data),

  create: (data: AgentDefinitionCreate) =>
    apiClient.post<AgentDefinitionResponse>('/api/agent-definitions', data).then(r => r.data),

  update: (id: string, data: AgentDefinitionUpdate) =>
    apiClient.patch<AgentDefinitionResponse>(`/api/agent-definitions/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    apiClient.delete(`/api/agent-definitions/${id}`),
}

// Model name suggestions per provider
export const MODEL_OPTIONS: Record<Provider, string[]> = {
  openai:    ['gpt-4o', 'gpt-4-turbo', 'gpt-4o-mini', 'gpt-3.5-turbo'],
  anthropic: ['claude-3-5-sonnet-20241022', 'claude-3-haiku-20240307', 'claude-3-opus-20240229'],
  google:    ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-pro'],
  azure:     [],   // user enters their deployment name
  ollama:    ['llama3', 'mistral', 'gemma2', 'phi3'],
}
