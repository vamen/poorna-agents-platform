import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  agentDefinitionsApi,
  type AgentDefinitionResponse,
} from '../api/agentDefinitions'
import { Plus, Trash2, Edit2, Bot, KeyRound } from 'lucide-react'

const PROVIDER_BADGE: Record<string, string> = {
  openai:    'bg-teal-50 text-teal-700',
  anthropic: 'bg-orange-50 text-orange-700',
  google:    'bg-blue-50 text-blue-700',
  azure:     'bg-sky-50 text-sky-700',
  ollama:    'bg-gray-100 text-gray-600',
}

function ConfirmDeleteModal({
  name,
  onConfirm,
  onCancel,
}: {
  name: string
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onCancel}>
      <div
        className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold text-gray-900 mb-2">Delete agent definition?</h2>
        <p className="text-sm text-gray-500 mb-5">
          <span className="font-medium text-gray-700">{name}</span> will be permanently removed and
          any workflows using it will fail to compile.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 bg-red-600 text-white rounded-lg py-2 text-sm hover:bg-red-700"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  )
}

export function AgentDefinitions() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [deleteTarget, setDeleteTarget] = useState<AgentDefinitionResponse | null>(null)

  const { data: definitions = [], isLoading } = useQuery<AgentDefinitionResponse[]>({
    queryKey: ['agentDefinitions'],
    queryFn: agentDefinitionsApi.list,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => agentDefinitionsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agentDefinitions'] })
      qc.invalidateQueries({ queryKey: ['agentTemplates'] })
      setDeleteTarget(null)
    },
  })

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto">
        {/* header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Custom Agent Types</h1>
            <p className="text-sm text-gray-500 mt-1">
              Define reusable AI agent types that appear in your workflow canvas
            </p>
          </div>
          <button
            onClick={() => navigate('/workspace/agent-definitions/new')}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" />
            Define Agent
          </button>
        </div>

        {/* list */}
        {isLoading ? (
          <div className="text-center py-12 text-gray-400">Loading…</div>
        ) : definitions.length === 0 ? (
          <div className="text-center py-16 border-2 border-dashed border-gray-200 rounded-xl">
            <Bot className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No custom agent types yet</p>
            <p className="text-sm text-gray-400 mt-1">
              Click <span className="font-medium">Define Agent</span> to create one
            </p>
          </div>
        ) : (
          <div className="grid gap-3">
            {definitions.map((defn) => {
              const primaryModel = defn.reasoning.model[0]
              const provColor = PROVIDER_BADGE[primaryModel?.provider] || PROVIDER_BADGE.ollama
              const anyKeyStored = defn.reasoning.model.some(m => m.has_api_key)
              return (
                <div
                  key={defn.id}
                  className="bg-white border border-gray-200 rounded-xl p-4 flex items-start gap-4 hover:shadow-sm transition-shadow"
                >
                  {/* long-running badge */}
                  <span className={`mt-0.5 px-2 py-1 rounded text-xs font-medium border flex-shrink-0 ${
                    defn.is_long_running
                      ? 'bg-violet-50 text-violet-700 border-violet-200'
                      : 'bg-sky-50 text-sky-700 border-sky-200'
                  }`}>
                    {defn.is_long_running ? 'long-running' : 'single-shot'}
                  </span>

                  {/* info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm text-gray-900">{defn.display_name}</span>
                      <span className="text-xs font-mono text-gray-400">{defn.name}</span>
                    </div>
                    {defn.description && (
                      <p className="text-xs text-gray-500 mt-0.5 truncate">{defn.description}</p>
                    )}
                    <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${provColor}`}>
                        {primaryModel?.provider}
                      </span>
                      <span className="text-xs text-gray-400 font-mono">{primaryModel?.name}</span>
                      {defn.reasoning.model.length > 1 && (
                        <span className="text-xs text-gray-400">+{defn.reasoning.model.length - 1} fallback</span>
                      )}
                      <span className="text-xs text-gray-400">·</span>
                      <span className="text-xs text-gray-400">{defn.reasoning.strategy.toUpperCase()}</span>
                      {anyKeyStored && (
                        <>
                          <span className="text-xs text-gray-400">·</span>
                          <span className="flex items-center gap-0.5 text-xs text-green-600">
                            <KeyRound className="w-3 h-3" /> key stored
                          </span>
                        </>
                      )}
                      {defn.events.length > 0 && (
                        <>
                          <span className="text-xs text-gray-400">·</span>
                          <span className="text-xs text-gray-400">
                            {defn.events.length} event{defn.events.length !== 1 ? 's' : ''}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* actions */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => navigate(`/workspace/agent-definitions/${defn.id}`)}
                      className="p-1.5 text-gray-400 hover:text-blue-600 rounded hover:bg-blue-50"
                      title="Edit"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => setDeleteTarget(defn)}
                      className="p-1.5 text-gray-400 hover:text-red-500 rounded hover:bg-red-50"
                      title="Delete"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {deleteTarget && (
        <ConfirmDeleteModal
          name={deleteTarget.display_name}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </div>
  )
}
