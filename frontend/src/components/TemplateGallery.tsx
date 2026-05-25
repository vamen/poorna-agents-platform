import { useQuery } from '@tanstack/react-query'
import { workflowsApi, type WorkflowTemplate } from '../api/workflows'
import { Layers } from 'lucide-react'

interface Props {
  onSelect: (template: WorkflowTemplate) => void
  onClose: () => void
}

export function TemplateGallery({ onSelect, onClose }: Props) {
  const { data: templates = [] } = useQuery<WorkflowTemplate[]>({
    queryKey: ['workflowTemplates'],
    queryFn: workflowsApi.listTemplates,
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2 mb-4">
          <Layers className="w-5 h-5 text-blue-600" />
          <h2 className="text-lg font-semibold text-gray-900">Workflow Templates</h2>
        </div>
        <p className="text-sm text-gray-500 mb-5">Start from a pre-built workflow or build from scratch.</p>

        <div className="grid grid-cols-2 gap-4">
          {templates.map((tmpl) => (
            <button
              key={tmpl.slug}
              onClick={() => { onSelect(tmpl); onClose() }}
              className="text-left border border-gray-200 rounded-lg p-4 hover:border-blue-400 hover:bg-blue-50 transition-all"
            >
              <div className="font-medium text-sm text-gray-900 mb-1">{tmpl.name}</div>
              <div className="text-xs text-gray-500">{tmpl.description}</div>
              <div className="mt-2 text-xs text-blue-600">
                {tmpl.graph_definition.nodes.length} nodes · {tmpl.graph_definition.edges.length} edges
              </div>
            </button>
          ))}

          <button
            onClick={onClose}
            className="text-left border border-dashed border-gray-300 rounded-lg p-4 hover:border-gray-400 transition-all flex items-center justify-center"
          >
            <span className="text-sm text-gray-400">Start blank</span>
          </button>
        </div>
      </div>
    </div>
  )
}
