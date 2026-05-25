import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { agentsApi, type Agent, type AgentTemplate } from '../api/agents'
import { X } from 'lucide-react'

interface Props {
  /** Pre-selected agent type — skips the type dropdown. */
  preselectedType?: string
  /** When provided the new agent is scoped to this workflow. */
  workflowId?: string
  onCreated?: (agent: Agent) => void
  onClose: () => void
}

export function CreateAgentModal({ preselectedType, workflowId, onCreated, onClose }: Props) {
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [selectedType, setSelectedType] = useState(preselectedType ?? '')

  const { data: templates = [] } = useQuery<AgentTemplate[]>({
    queryKey: ['agentTemplates'],
    queryFn: agentsApi.listTemplates,
  })

  const mutation = useMutation({
    mutationFn: () => agentsApi.create({
      name: name.trim(),
      type: selectedType,
      config: {},
      ...(workflowId ? { workflow_id: workflowId } : {}),
    }),
    onSuccess: (agent) => {
      qc.invalidateQueries({ queryKey: ['agents', workflowId] })
      onCreated?.(agent)
      onClose()
    },
  })

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-900">Create Agent</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-gray-700 block mb-1">Name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && name.trim() && selectedType && mutation.mutate()}
              placeholder="My Agent"
              autoFocus
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {!preselectedType && (
            <div>
              <label className="text-xs font-medium text-gray-700 block mb-1">Type</label>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
              >
                <option value="">Select type…</option>
                {templates.map((t) => (
                  <option key={t.name} value={t.name}>{t.display_name}</option>
                ))}
              </select>
            </div>
          )}

          {mutation.isError && (
            <p className="text-xs text-red-500">
              {(mutation.error as Error).message ?? 'Failed to create agent'}
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
              disabled={!name.trim() || !selectedType || mutation.isPending}
              className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {mutation.isPending ? 'Creating…' : 'Create'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
