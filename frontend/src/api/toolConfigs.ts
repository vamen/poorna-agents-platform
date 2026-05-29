import { apiClient } from './client'

// ── Tool template types ───────────────────────────────────────────────────────

export interface ToolMeta {
  name: string
  display_name: string
  description: string
  kind: 'tool' | 'mcp_server'
  phase: number
  icon?: string
  docs_url?: string
  oauth_provider?: string
}

export interface ToolUiField {
  path: string
  label: string
  widget: string            // text | email | url | password | select | textarea | key_value | oauth2_button
  placeholder?: string
  help?: string
  condition?: string        // e.g. "credential.credential_type == 'oauth2'"
  options?: { value: string; label: string }[]
  sensitive?: boolean
  // oauth2_button specific
  oauth2_provider?: string
  button_text?: string
  connected_text?: string
}

export interface ToolUiHints {
  order?: string[]
  fields: ToolUiField[]
}

// ── Agent tool config types ───────────────────────────────────────────────────

export interface ToolConfigResponse {
  id: string
  agent_id: string
  name: string
  kind: string
  config: Record<string, unknown>
  created_at: string
  updated_at: string | null
}

export interface ToolConfigUpsert {
  kind: string
  config: Record<string, unknown>
}

// ── API ───────────────────────────────────────────────────────────────────────

export const toolsApi = {
  /** List all available tool & MCP server templates (meta only). */
  listTools: () =>
    apiClient.get<ToolMeta[]>('/api/tools').then(r => r.data),

  /** Get the JSON Schema for a tool's config form (for validation). */
  getSchema: (name: string) =>
    apiClient.get<Record<string, unknown>>(`/api/tools/${name}/schema`).then(r => r.data),

  /** Get UI rendering hints for a tool's config form. */
  getUi: (name: string) =>
    apiClient.get<ToolUiHints>(`/api/tools/${name}/ui`).then(r => r.data),

  /** List all tool configs for an agent. */
  listConfigs: (agentId: string) =>
    apiClient.get<ToolConfigResponse[]>(`/api/agents/${agentId}/tool-configs`).then(r => r.data),

  /** Create or update a tool config for an agent. */
  upsertConfig: (agentId: string, name: string, data: ToolConfigUpsert) =>
    apiClient.put<ToolConfigResponse>(`/api/agents/${agentId}/tool-configs/${name}`, data).then(r => r.data),

  /** Delete a tool config from an agent. */
  deleteConfig: (agentId: string, name: string) =>
    apiClient.delete(`/api/agents/${agentId}/tool-configs/${name}`),

  /**
   * Get the OAuth authorize URL for an agent tool.
   * Uses the explicit oauthProvider when supplied (from meta.oauth_provider),
   * otherwise falls back to 'google'.
   */
  getOAuthUrl: (agentId: string, toolName: string, oauthProvider?: string) => {
    const provider = oauthProvider ?? 'google'
    return apiClient.get<{ auth_url: string }>(`/api/oauth/${provider}/authorize`, {
      params: { agent_id: agentId, tool_name: toolName },
    }).then(r => r.data)
  },
}
