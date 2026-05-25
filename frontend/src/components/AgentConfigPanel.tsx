/**
 * AgentConfigPanel — side panel opened from the workflow canvas.
 *
 * Single-step form: agent name + credential forms are shown together.
 * A UUID is pre-generated on mount so OAuth can fire without waiting
 * for a separate "create agent" step.
 *
 * Flow:
 *   1. Panel opens → pendingId = crypto.randomUUID()
 *   2. User fills in name (+ optional non-OAuth credentials)
 *   3a. "Connect [Service]" OAuth button → creates agent first if needed,
 *       then redirects to OAuth consent screen.
 *   3b. "Save Agent" → creates agent (if new) + saves non-OAuth creds
 *       → updates canvas node → closes panel.
 *
 * Re-opening a saved node skips creation and goes straight to credential
 * management (name field is hidden, showing the existing agent name instead).
 */

import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentsApi } from '../api/agents'
import { toolsApi } from '../api/toolConfigs'
import { useWorkflowStore } from '../store/workflowStore'
import { ToolConfigForm } from './ToolConfigForm'
import { X, Server, Wrench, CheckCircle } from 'lucide-react'

interface Props {
  nodeId: string
  agentType: string
  agentId?: string      // set if this node was previously saved
  workflowId?: string   // scope new agents to this workflow
  onClose: () => void
}

export function AgentConfigPanel({ nodeId, agentType, agentId: existingAgentId, workflowId, onClose }: Props) {
  const { updateNode } = useWorkflowStore()
  const queryClient = useQueryClient()

  // Pre-generate a stable ID so OAuth can reference it before the DB row exists.
  // If the node already has an agentId we reuse that.
  const [pendingId] = useState(() => existingAgentId ?? crypto.randomUUID())
  const [agentSaved, setAgentSaved] = useState(!!existingAgentId)
  const [agentName, setAgentName] = useState('')

  // ── Template ───────────────────────────────────────────────────────────────

  const { data: template, isLoading: templateLoading } = useQuery({
    queryKey: ['template', agentType],
    queryFn: () => agentsApi.getTemplate(agentType),
  })

  const { data: allToolMetas = [] } = useQuery({
    queryKey: ['tools'],
    queryFn: toolsApi.listTools,
  })

  const { data: existingConfigs = [] } = useQuery({
    queryKey: ['agent-tool-configs', pendingId],
    queryFn: () => toolsApi.listConfigs(pendingId),
    enabled: agentSaved,   // only fetch once the agent row exists
  })

  const declaredToolNames: string[] = [
    ...(template?.tools ?? []),
    ...(template?.mcp_servers ?? []),
  ]
  const declaredTools = allToolMetas.filter((t) => declaredToolNames.includes(t.name))
  const configsByName = Object.fromEntries(existingConfigs.map((c) => [c.name, c]))

  // ── Create agent mutation ──────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: () =>
      agentsApi.create({
        id: pendingId,
        name: agentName.trim(),
        type: agentType,
        config: {},
        ...(workflowId ? { workflow_id: workflowId } : {}),
      }),
    onSuccess: (agent) => {
      queryClient.invalidateQueries({ queryKey: ['agents', workflowId] })
      // Wire the node in the canvas store
      updateNode(nodeId, { agentId: agent.id, agentName: agent.name })
      setAgentSaved(true)
    },
  })

  /** Ensure the agent row exists before any credential operation. */
  const ensureAgentCreated = useCallback(async () => {
    if (agentSaved) return
    if (!agentName.trim()) throw new Error('Enter an agent name first')
    await createMutation.mutateAsync()
  }, [agentSaved, agentName, createMutation])

  // ── Save button handler ────────────────────────────────────────────────────

  const handleSave = async () => {
    if (!agentSaved) {
      try {
        await ensureAgentCreated()
      } catch {
        return  // validation error shown inline
      }
    }
    onClose()
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const displayName = template?.display_name ?? agentType

  return (
    <div className="w-80 bg-white border-l border-gray-200 flex flex-col h-full">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <div className="min-w-0">
          <h3 className="font-semibold text-sm text-gray-900 truncate">
            {agentSaved ? displayName : `Configure ${displayName}`}
          </h3>
          {template?.description && (
            <p className="text-xs text-gray-400 mt-0.5 truncate">{template.description}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 p-1 rounded flex-shrink-0 ml-2"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* ── Agent name (only for new agents) ──────────────────────────── */}
        {!agentSaved && (
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Agent Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
              placeholder={`My ${displayName}`}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoFocus
            />
            {createMutation.isError && (
              <p className="text-xs text-red-500 mt-1">
                {(createMutation.error as Error).message}
              </p>
            )}
          </div>
        )}

        {/* ── Credential / tool config forms ─────────────────────────────── */}
        {templateLoading ? (
          <div className="text-xs text-gray-400 text-center py-4">Loading…</div>
        ) : declaredTools.length > 0 ? (
          <div className="space-y-3">
            {declaredTools.map((tool) => {
              const isConfigured = !!configsByName[tool.name]
              return (
                <div
                  key={tool.name}
                  className="border border-gray-200 rounded-lg overflow-hidden"
                >
                  {/* Tool header */}
                  <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b border-gray-200">
                    {tool.kind === 'mcp_server'
                      ? <Server className="w-3.5 h-3.5 text-violet-500 flex-shrink-0" />
                      : <Wrench className="w-3.5 h-3.5 text-sky-500 flex-shrink-0" />
                    }
                    <span className="text-xs font-semibold text-gray-700 flex-1">{tool.display_name}</span>
                    {isConfigured && (
                      <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
                    )}
                  </div>

                  {/* Credential form */}
                  <div className="p-3">
                    <ToolConfigForm
                      agentId={pendingId}
                      toolName={tool.name}
                      existingConfig={configsByName[tool.name]}
                      onBeforeOAuth={ensureAgentCreated}
                      onSaved={() => {
                        // Mark agent as saved (in case OAuth came back and created it)
                        setAgentSaved(true)
                        queryClient.invalidateQueries({
                          queryKey: ['agent-tool-configs', pendingId],
                        })
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          /* No tools — show emitted events as a useful summary */
          template?.events && template.events.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-700 mb-1">Emits events:</p>
              <ul className="space-y-1">
                {template.events.map((ev) => (
                  <li
                    key={ev.name}
                    className="text-xs bg-gray-50 rounded px-2 py-1 text-gray-600 font-mono"
                  >
                    {ev.name}
                  </li>
                ))}
              </ul>
            </div>
          )
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-gray-200 space-y-2">
        {!agentSaved ? (
          <button
            onClick={handleSave}
            disabled={!agentName.trim() || createMutation.isPending}
            className="w-full bg-blue-600 text-white text-sm font-medium py-2 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {createMutation.isPending ? 'Creating…' : 'Save Agent'}
          </button>
        ) : (
          <button
            onClick={onClose}
            className="w-full bg-gray-900 text-white text-sm font-medium py-2 rounded hover:bg-gray-800"
          >
            Done
          </button>
        )}
      </div>
    </div>
  )
}
