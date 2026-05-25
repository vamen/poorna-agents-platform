import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentsApi, type Agent, type AgentTemplate } from '../api/agents'
import { CreateAgentModal } from '../components/CreateAgentModal'
import { Plus, Trash2, Zap, Settings2, Edit2, X } from 'lucide-react'

// ── Rename modal ──────────────────────────────────────────────────────────────

function RenameAgentModal({
  agent,
  onClose,
}: {
  agent: Agent
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [name, setName] = useState(agent.name)

  const mutation = useMutation({
    mutationFn: () => agentsApi.update(agent.id, { name: name.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] })
      onClose()
    },
  })

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-sm p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-900">Rename Agent</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-gray-700 block mb-1">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && name.trim() && mutation.mutate()}
              autoFocus
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {mutation.isError && (
            <p className="text-xs text-red-500">
              {(mutation.error as Error).message ?? 'Failed to rename'}
            </p>
          )}

          <div className="flex gap-3 pt-1">
            <button
              onClick={onClose}
              className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 text-sm hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              onClick={() => mutation.mutate()}
              disabled={!name.trim() || name.trim() === agent.name || mutation.isPending}
              className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {mutation.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function AgentList() {
  const [showCreate, setShowCreate] = useState(false)
  const [renameTarget, setRenameTarget] = useState<Agent | null>(null)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: agents = [], isLoading } = useQuery<Agent[]>({
    queryKey: ['agents'],
    queryFn: agentsApi.list,
  })

  const { data: templates = [] } = useQuery<AgentTemplate[]>({
    queryKey: ['agentTemplates'],
    queryFn: agentsApi.listTemplates,
  })

  const deleteMutation = useMutation({
    mutationFn: agentsApi.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  })

  const getIsLongRunning = (type: string) =>
    templates.find((t) => t.name === type)?.is_long_running ?? false

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Agents</h1>
            <p className="text-sm text-gray-500 mt-1">Reusable building blocks for your workflows</p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" />
            New Agent
          </button>
        </div>

        {isLoading ? (
          <div className="text-center py-12 text-gray-400">Loading…</div>
        ) : agents.length === 0 ? (
          <div className="text-center py-16 border-2 border-dashed border-gray-200 rounded-xl">
            <Zap className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No agents yet</p>
            <p className="text-sm text-gray-400 mt-1">Create your first agent to get started</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {agents.map((agent) => {
              const longRunning = getIsLongRunning(agent.type)
              return (
                <div key={agent.id} className="bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-4">
                  <div className={`px-2 py-1 rounded text-xs font-medium border flex-shrink-0 ${longRunning ? 'bg-violet-50 text-violet-700 border-violet-200' : 'bg-sky-50 text-sky-700 border-sky-200'}`}>
                    {longRunning ? 'long-running' : 'single-shot'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm text-gray-900">{agent.name}</div>
                    <div className="text-xs text-gray-500 mt-0.5 font-mono">{agent.type}</div>
                  </div>
                  <div className={`text-xs flex-shrink-0 ${agent.is_active ? 'text-green-600' : 'text-gray-400'}`}>
                    {agent.is_active ? 'Active' : 'Inactive'}
                  </div>
                  <button
                    onClick={() => setRenameTarget(agent)}
                    className="p-1.5 text-gray-400 hover:text-blue-600 rounded hover:bg-blue-50"
                    title="Rename agent"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => navigate(`/workspace/agents/${agent.id}`)}
                    className="p-1.5 text-gray-400 hover:text-blue-600 rounded hover:bg-blue-50"
                    title="Configure connections"
                  >
                    <Settings2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => deleteMutation.mutate(agent.id)}
                    className="p-1.5 text-gray-400 hover:text-red-500 rounded hover:bg-red-50"
                    title="Delete agent"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showCreate && (
        <CreateAgentModal onClose={() => setShowCreate(false)} />
      )}

      {renameTarget && (
        <RenameAgentModal
          agent={renameTarget}
          onClose={() => setRenameTarget(null)}
        />
      )}
    </div>
  )
}
