/**
 * AgentDetail — shows an agent instance with its configured tool credentials.
 *
 * URL: /workspace/agents/:id
 *
 * Shows only the tools / MCP servers that the agent's type actually declares
 * (from template.tools + template.mcp_servers), plus any already-configured
 * tools the agent has. Auto-expands the first declared tool so the form is
 * visible without extra clicks.
 *
 * Handles OAuth return: ?connected=gmail → success banner + auto-expand.
 * Handles OAuth error:  ?oauth_error=...  → error banner.
 */

import { useState, useEffect } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentsApi } from '../api/agents'
import { toolsApi, type ToolConfigResponse } from '../api/toolConfigs'
import { ToolConfigForm } from '../components/ToolConfigForm'
import {
  ArrowLeft, Zap, Wrench, Server,
  CheckCircle, AlertCircle, ChevronDown, ChevronUp,
} from 'lucide-react'

export function AgentDetail() {
  const { id } = useParams<{ id: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const connected = searchParams.get('connected')
  const oauthError = searchParams.get('oauth_error')

  // Auto-clear query params after banner shows
  useEffect(() => {
    if (connected || oauthError) {
      const t = setTimeout(() => setSearchParams({}), 5000)
      return () => clearTimeout(t)
    }
  }, [connected, oauthError, setSearchParams])

  // ── Data fetching ───────────────────────────────────────────────────────────

  const { data: agent, isLoading: agentLoading } = useQuery({
    queryKey: ['agent', id],
    queryFn: () => agentsApi.get(id!),
    enabled: !!id,
  })

  // Template gives us the tools/mcp_servers this agent type declares
  const { data: template } = useQuery({
    queryKey: ['agentTemplate', agent?.type],
    queryFn: () => agentsApi.getTemplate(agent!.type),
    enabled: !!agent,
  })

  // All available tool/mcp_server templates (meta only)
  const { data: allToolMetas = [] } = useQuery({
    queryKey: ['tools'],
    queryFn: toolsApi.listTools,
  })

  // Existing per-agent credentials
  const { data: existingConfigs = [], isLoading: configsLoading } = useQuery({
    queryKey: ['agent-tool-configs', id],
    queryFn: () => toolsApi.listConfigs(id!),
    enabled: !!id,
  })

  // ── Derive which tools to show ──────────────────────────────────────────────
  // Priority:
  //  1. Tools/MCP servers declared by the agent's type (template.tools + template.mcp_servers)
  //  2. Plus any already-configured tools (in case the definition changed)
  //  3. Fallback: show all available tools if the template declares nothing

  const declaredNames: Set<string> = new Set([
    ...(template?.tools ?? []),
    ...(template?.mcp_servers ?? []),
    ...existingConfigs.map(c => c.name),   // always show things already configured
  ])

  const toolsToShow = declaredNames.size > 0
    ? allToolMetas.filter(t => declaredNames.has(t.name))
    : allToolMetas   // fallback: show all if agent type declares nothing

  const configsByName: Record<string, ToolConfigResponse> = {}
  for (const c of existingConfigs) configsByName[c.name] = c

  // ── Auto-expand logic ───────────────────────────────────────────────────────
  // - If OAuth just returned (?connected=X), expand that tool
  // - Otherwise auto-expand the first declared tool so the form is immediately visible
  const firstTool = toolsToShow[0]?.name ?? null
  const [expandedTool, setExpandedTool] = useState<string | null>(
    connected ?? firstTool
  )

  // Once toolsToShow resolves (async), set initial expansion if not already set
  useEffect(() => {
    if (!connected && expandedTool === null && firstTool) {
      setExpandedTool(firstTool)
    }
  }, [firstTool, connected, expandedTool])

  const deleteConfigMutation = useMutation({
    mutationFn: (name: string) => toolsApi.deleteConfig(id!, name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agent-tool-configs', id] }),
  })

  // ── Render ──────────────────────────────────────────────────────────────────

  if (agentLoading) {
    return <div className="flex-1 flex items-center justify-center text-gray-400">Loading…</div>
  }
  if (!agent) {
    return <div className="flex-1 flex items-center justify-center text-gray-400">Agent not found.</div>
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">

        {/* Back */}
        <button
          onClick={() => navigate('/workspace/agents')}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700 mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Agents
        </button>

        {/* OAuth banners */}
        {connected && (
          <div className="flex items-center gap-2 bg-green-50 border border-green-200 text-green-800 text-sm rounded-lg px-4 py-3 mb-4">
            <CheckCircle className="w-4 h-4 flex-shrink-0" />
            <span><strong>{connected}</strong> connected successfully!</span>
          </div>
        )}
        {oauthError && (
          <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-800 text-sm rounded-lg px-4 py-3 mb-4">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>OAuth error: {oauthError.replace(/_/g, ' ')}</span>
          </div>
        )}

        {/* Agent header */}
        <div className="bg-white border border-gray-200 rounded-xl p-5 mb-6">
          <div className="flex items-start gap-4">
            <div className={`p-2 rounded-lg ${template?.is_long_running ? 'bg-violet-50' : 'bg-sky-50'}`}>
              <Zap className={`w-6 h-6 ${template?.is_long_running ? 'text-violet-400' : 'text-sky-400'}`} />
            </div>
            <div className="flex-1">
              <h1 className="text-xl font-bold text-gray-900">{agent.name}</h1>
              <div className="flex items-center gap-3 mt-1 flex-wrap">
                <span className="text-sm text-gray-400 font-mono">{agent.type}</span>
                {template && (
                  <span className={`text-xs px-2 py-0.5 rounded font-medium border ${
                    template.is_long_running
                      ? 'bg-violet-50 text-violet-700 border-violet-200'
                      : 'bg-sky-50 text-sky-700 border-sky-200'
                  }`}>
                    {template.is_long_running ? 'long-running' : 'single-shot'}
                  </span>
                )}
                <span className={`text-xs ${agent.is_active ? 'text-green-600' : 'text-gray-400'}`}>
                  {agent.is_active ? '● Active' : '○ Inactive'}
                </span>
              </div>
              {template?.description && (
                <p className="text-sm text-gray-500 mt-1.5">{template.description}</p>
              )}
            </div>
          </div>
        </div>

        {/* Tool connections */}
        <div>
          <h2 className="text-base font-semibold text-gray-900 mb-1">
            Connections
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            {toolsToShow.length === 0
              ? 'This agent type has no tool or service connections.'
              : 'Provide credentials for the tools and services this agent uses.'}
          </p>

          {configsLoading ? (
            <div className="text-sm text-gray-400 py-6 text-center">Loading…</div>
          ) : toolsToShow.length === 0 ? (
            <div className="text-center py-10 border-2 border-dashed border-gray-200 rounded-xl">
              <Wrench className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-400">No connections needed for this agent type.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {toolsToShow.map(tool => {
                const isConfigured = !!configsByName[tool.name]
                const isExpanded = expandedTool === tool.name

                return (
                  <div
                    key={tool.name}
                    className={`bg-white rounded-xl overflow-hidden border transition-colors ${
                      isExpanded ? 'border-blue-200 shadow-sm' : 'border-gray-200'
                    }`}
                  >
                    {/* Header row — always visible */}
                    <button
                      onClick={() => setExpandedTool(isExpanded ? null : tool.name)}
                      className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-gray-50 transition-colors"
                    >
                      {tool.kind === 'mcp_server'
                        ? <Server className="w-4 h-4 text-violet-500 flex-shrink-0" />
                        : <Wrench className="w-4 h-4 text-sky-500 flex-shrink-0" />
                      }

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-sm text-gray-900">{tool.display_name}</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                            tool.kind === 'mcp_server'
                              ? 'bg-violet-50 text-violet-700'
                              : 'bg-sky-50 text-sky-700'
                          }`}>
                            {tool.kind === 'mcp_server' ? 'MCP' : 'Tool'}
                          </span>
                        </div>
                        {tool.description && (
                          <p className="text-xs text-gray-400 mt-0.5 truncate">{tool.description}</p>
                        )}
                      </div>

                      <div className="flex items-center gap-2 flex-shrink-0">
                        {isConfigured ? (
                          <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                            <CheckCircle className="w-3.5 h-3.5" />
                            Connected
                          </span>
                        ) : (
                          <span className="text-xs text-amber-600 font-medium">Not connected</span>
                        )}
                        {isExpanded
                          ? <ChevronUp className="w-4 h-4 text-gray-400" />
                          : <ChevronDown className="w-4 h-4 text-gray-400" />
                        }
                      </div>
                    </button>

                    {/* Expanded credential form */}
                    {isExpanded && (
                      <div className="border-t border-gray-100 px-4 py-5">
                        <ToolConfigForm
                          agentId={id!}
                          toolName={tool.name}
                          existingConfig={configsByName[tool.name]}
                          onSaved={() =>
                            qc.invalidateQueries({ queryKey: ['agent-tool-configs', id] })
                          }
                        />

                        {isConfigured && (
                          <div className="mt-4 pt-3 border-t border-gray-100">
                            <button
                              onClick={() => deleteConfigMutation.mutate(tool.name)}
                              disabled={deleteConfigMutation.isPending}
                              className="text-xs text-red-400 hover:text-red-600 disabled:opacity-50"
                            >
                              {deleteConfigMutation.isPending ? 'Removing…' : 'Disconnect'}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
