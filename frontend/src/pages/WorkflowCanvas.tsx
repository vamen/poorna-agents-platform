import { useCallback, useEffect, useRef, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  applyNodeChanges,
  applyEdgeChanges,
  type Connection,
  type Node,
  type NodeChange,
  type EdgeChange,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { workflowsApi, type WorkflowTemplate, type ValidationResult } from '../api/workflows'
import { agentsApi, type Agent, type AgentTemplate } from '../api/agents'
import { AgentNode } from '../components/AgentNode'
import { EdgeEventSelector } from '../components/EdgeEventSelector'
import { AgentConfigPanel } from '../components/AgentConfigPanel'
import { TemplateGallery } from '../components/TemplateGallery'
import { CreateAgentModal } from '../components/CreateAgentModal'
import { useWorkflowStore } from '../store/workflowStore'
import { Save, Play, Pause, Layers, ArrowLeft, Plus, Zap, CheckCircle, AlertCircle, ShieldCheck, Loader2 } from 'lucide-react'

const nodeTypes = { agentNode: AgentNode }
const edgeTypes = { eventEdge: EdgeEventSelector }

export function WorkflowCanvas() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  // ── Single source of truth: Zustand store ──────────────────────────────────
  const { nodes, edges, isDirty, loadCanvas, setNodes, setEdges, setIsDirty, resetCanvas } =
    useWorkflowStore()

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [showTemplates, setShowTemplates] = useState(false)
  const [showCreateAgent, setShowCreateAgent] = useState(false)
  const [workflowName, setWorkflowName] = useState('Untitled Workflow')
  const [workflowStatus, setWorkflowStatus] = useState('draft')
  // null = never validated; object = last result (reset when canvas turns dirty)
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null)

  // Track which workflow ID is currently painted on the canvas so we only
  // reset+reload when the *workflow* changes, not on background refetches.
  const loadedWorkflowId = useRef<string | null>(null)

  // ── Data ───────────────────────────────────────────────────────────────────
  // Agents for the sidebar palette — scoped to this workflow (NULL = global/legacy)
  const workflowId = id !== 'new' ? id : undefined
  const { data: agents = [] } = useQuery<Agent[]>({
    queryKey: ['agents', workflowId],
    queryFn: () => agentsApi.list(workflowId),
  })

  // Templates still needed for isLongRunning lookup when adding a node
  const { data: templates = [] } = useQuery<AgentTemplate[]>({
    queryKey: ['agentTemplates'],
    queryFn: agentsApi.listTemplates,
  })

  const { data: workflow } = useQuery({
    queryKey: ['workflow', id],
    queryFn: () => workflowsApi.get(id!),
    enabled: !!id && id !== 'new',
  })

  // Load canvas when the workflow data matches the current URL id.
  //
  // Why both [id, workflow] as deps:
  //   - `id` must be listed so the effect re-runs when you navigate between
  //     workflows even when React Query returns the *same cached object
  //     reference* for a recently-visited workflow (staleTime: 30 s).
  //   - `workflow` must be listed so the effect runs when data first arrives
  //     after a navigation to an uncached workflow.
  //
  // The ref guard (`loadedWorkflowId`) prevents re-clearing/re-loading on
  // background refetches — if the ref already holds this workflow's id we
  // know the canvas is already correct and we skip.
  useEffect(() => {
    if (!workflow || workflow.id !== id) return          // data not for current id yet
    if (loadedWorkflowId.current === workflow.id) return // already loaded — skip refetch

    loadedWorkflowId.current = workflow.id
    setValidationResult(null)
    setWorkflowName(workflow.name)
    setWorkflowStatus(workflow.status)
    loadCanvas({
      nodes: (workflow.graph_definition.nodes ?? []).map((n) => ({
        ...n,
        type: 'agentNode',
      })),
      edges: (workflow.graph_definition.edges ?? []).map((e) => ({
        ...e,
        type: 'eventEdge',
      })),
    })
  }, [id, workflow])   // eslint-disable-line react-hooks/exhaustive-deps

  // When navigating away, clear the canvas and reset the ref so the next
  // workflow (even a cached one) triggers a fresh load.
  useEffect(() => {
    return () => {
      resetCanvas()
      loadedWorkflowId.current = null
    }
  }, [id])   // eslint-disable-line react-hooks/exhaustive-deps

  // Reset validation whenever the canvas has unsaved changes
  useEffect(() => {
    if (isDirty) setValidationResult(null)
  }, [isDirty])

  // ── ReactFlow change handlers ──────────────────────────────────────────────
  // Apply ReactFlow's incremental changes (drag, resize, delete…) into the store.

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const next = applyNodeChanges(changes, useWorkflowStore.getState().nodes)
      setNodes(next)
    },
    [setNodes]
  )

  const onEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const next = applyEdgeChanges(changes, useWorkflowStore.getState().edges)
      setEdges(next)
    },
    [setEdges]
  )

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges(addEdge({ ...connection, type: 'eventEdge', data: {} }, useWorkflowStore.getState().edges))
    },
    [setEdges]
  )

  // ── Mutations ──────────────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: async () => {
      // Read directly from the store at call time so we always have the latest nodes
      const { nodes: currentNodes, edges: currentEdges } = useWorkflowStore.getState()
      const graphDef = { nodes: currentNodes, edges: currentEdges }
      if (id && id !== 'new') {
        return workflowsApi.update(id, { name: workflowName, graph_definition: graphDef })
      }
      return workflowsApi.create({ name: workflowName, graph_definition: graphDef })
    },
    onSuccess: (data) => {
      setIsDirty(false)
      setValidationResult(null)   // saved but not yet re-validated
      qc.invalidateQueries({ queryKey: ['workflows'] })
      qc.invalidateQueries({ queryKey: ['workflow', data.id] })
      qc.invalidateQueries({ queryKey: ['agents', data.id] })
      if (id === 'new') {
        loadedWorkflowId.current = null  // allow the arriving query to reload the canvas
        navigate(`/workspace/canvas/${data.id}`, { replace: true })
      }
    },
  })

  /** Save (if dirty) then validate. */
  const validateMutation = useMutation({
    mutationFn: async () => {
      // Ensure the workflow is persisted before validating
      let workflowId = id
      if (id === 'new' || isDirty) {
        const saved = await saveMutation.mutateAsync()
        workflowId = saved.id
      }
      return workflowsApi.validate(workflowId!)
    },
    onSuccess: (result) => {
      setValidationResult(result)
    },
  })

  const deployMutation = useMutation({
    mutationFn: () => workflowsApi.deploy(id!),
    onSuccess: (data) => {
      setWorkflowStatus(data.status)
      qc.invalidateQueries({ queryKey: ['workflow', id] })
    },
  })

  const pauseMutation = useMutation({
    mutationFn: () => workflowsApi.pause(id!),
    onSuccess: (data) => setWorkflowStatus(data.status),
  })

  // ── Node helpers ───────────────────────────────────────────────────────────

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const addNodeFromAgent = useCallback((agent: Agent) => {
    const tmpl = templates.find((t) => t.name === agent.type)
    const nodeId = `node-${Date.now()}`
    const newNode: Node = {
      id: nodeId,
      type: 'agentNode',
      position: { x: Math.random() * 400 + 100, y: Math.random() * 200 + 100 },
      data: {
        label: agent.name,
        agentType: agent.type,
        agentId: agent.id,
        agentName: agent.name,
        isLongRunning: tmpl?.is_long_running ?? false,
      },
    }
    setNodes([...useWorkflowStore.getState().nodes, newNode])
    // Auto-open the config panel for the newly added node
    setSelectedNodeId(nodeId)
  }, [templates, setNodes])

  const applyTemplate = (tmpl: WorkflowTemplate) => {
    setWorkflowName(tmpl.name)
    loadCanvas({
      nodes: tmpl.graph_definition.nodes.map((n) => ({ ...n, type: 'agentNode' })),
      edges: tmpl.graph_definition.edges.map((e) => ({ ...e, type: 'eventEdge' })),
    })
    setIsDirty(true)
  }

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id)
  }, [])

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null)
  }, [])

  // ── Derived ────────────────────────────────────────────────────────────────

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) ?? null
  const isDeployable = validationResult?.valid === true && !isDirty

  const STATUS_COLORS: Record<string, string> = {
    draft: 'bg-gray-100 text-gray-600',
    active: 'bg-green-100 text-green-700',
    paused: 'bg-amber-100 text-amber-700',
    failed: 'bg-red-100 text-red-700',
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full">
      {/* Left palette — agents list */}
      <div className="w-52 flex-shrink-0 border-r border-gray-200 bg-gray-50 flex flex-col">
        <div className="px-3 py-2.5 border-b border-gray-200 flex items-center justify-between">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Agents</p>
          <button
            onClick={() => setShowCreateAgent(true)}
            title="Create new agent"
            className="w-5 h-5 rounded flex items-center justify-center text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {agents.length === 0 ? (
            <div className="px-3 py-6 text-center">
              <Zap className="w-6 h-6 text-gray-300 mx-auto mb-2" />
              <p className="text-xs text-gray-400">No agents yet</p>
              <button
                onClick={() => setShowCreateAgent(true)}
                className="mt-2 text-xs text-blue-600 hover:underline"
              >
                Create one
              </button>
            </div>
          ) : (
            agents.map((agent) => {
              const tmpl = templates.find((t) => t.name === agent.type)
              return (
                <button
                  key={agent.id}
                  onClick={() => addNodeFromAgent(agent)}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-white hover:shadow-sm border border-transparent hover:border-gray-200 transition-all group"
                >
                  <div className="font-medium text-gray-800 text-xs truncate">{agent.name}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className={`text-[10px] px-1 py-0.5 rounded font-medium ${
                      tmpl?.is_long_running
                        ? 'bg-violet-100 text-violet-600'
                        : 'bg-sky-100 text-sky-600'
                    }`}>
                      {tmpl?.display_name ?? agent.type}
                    </span>
                  </div>
                </button>
              )
            })
          )}
        </div>

        <div className="p-2 border-t border-gray-200">
          <button
            onClick={() => setShowTemplates(true)}
            className="w-full flex items-center gap-2 px-3 py-2 text-xs text-blue-600 hover:bg-blue-50 rounded-lg"
          >
            <Layers className="w-3 h-3" />
            Load Template
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="border-b border-gray-200 bg-white">
          <div className="flex items-center gap-3 px-4 py-2">
            <button
              onClick={() => navigate('/workspace')}
              className="text-gray-400 hover:text-gray-600 p-1 rounded"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>

            <input
              value={workflowName}
              onChange={(e) => { setWorkflowName(e.target.value); setIsDirty(true) }}
              className="text-sm font-medium text-gray-900 bg-transparent border-0 outline-none focus:bg-gray-50 rounded px-2 py-1 min-w-[160px]"
            />

            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[workflowStatus] ?? STATUS_COLORS.draft}`}>
              {workflowStatus}
            </span>

            {isDirty && <span className="text-xs text-amber-500">Unsaved changes</span>}

            <div className="ml-auto flex items-center gap-2">
              {/* Save — always available, saves as draft */}
              <button
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                {saveMutation.isPending
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Save className="w-3.5 h-3.5" />}
                {saveMutation.isPending ? 'Saving…' : 'Save'}
              </button>

              {/* Validate — auto-saves first if dirty */}
              <button
                onClick={() => validateMutation.mutate()}
                disabled={validateMutation.isPending}
                className={[
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm disabled:opacity-50',
                  validationResult?.valid
                    ? 'bg-green-50 border border-green-300 text-green-700 hover:bg-green-100'
                    : 'border border-gray-300 text-gray-700 hover:bg-gray-50',
                ].join(' ')}
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                {validateMutation.isPending ? 'Validating…' : 'Validate'}
              </button>

              {workflowStatus === 'active' ? (
                <button
                  onClick={() => pauseMutation.mutate()}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500 text-white rounded-lg text-sm hover:bg-amber-600"
                >
                  <Pause className="w-3.5 h-3.5" />
                  Pause
                </button>
              ) : (
                <button
                  onClick={() => deployMutation.mutate()}
                  disabled={!isDeployable || deployMutation.isPending}
                  title={!isDeployable ? 'Validate the workflow before deploying' : undefined}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Play className="w-3.5 h-3.5" />
                  {deployMutation.isPending ? 'Deploying…' : 'Deploy'}
                </button>
              )}
            </div>
          </div>

          {/* Validation feedback bar */}
          {validationResult && !isDirty && (
            <div className={[
              'px-4 py-2 text-xs flex items-start gap-2 border-t',
              validationResult.valid
                ? 'bg-green-50 border-green-100 text-green-700'
                : 'bg-red-50 border-red-100 text-red-700',
            ].join(' ')}>
              {validationResult.valid ? (
                <>
                  <CheckCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  <span>Workflow is valid — ready to deploy.</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  <ul className="space-y-0.5">
                    {validationResult.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-1 min-h-0">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            fitView
            className="flex-1"
          >
            <Background />
            <Controls />
            <MiniMap />
          </ReactFlow>

          {selectedNode && (
            <AgentConfigPanel
              key={selectedNode.id}    // remount when different node selected
              nodeId={selectedNode.id}
              agentType={selectedNode.data.agentType as string}
              agentId={selectedNode.data.agentId as string | undefined}
              workflowId={workflowId}
              onClose={() => setSelectedNodeId(null)}
            />
          )}
        </div>
      </div>

      {showTemplates && (
        <TemplateGallery
          onSelect={applyTemplate}
          onClose={() => setShowTemplates(false)}
        />
      )}

      {showCreateAgent && (
        <CreateAgentModal
          workflowId={workflowId}
          onCreated={(agent) => {
            setShowCreateAgent(false)
            addNodeFromAgent(agent)
          }}
          onClose={() => setShowCreateAgent(false)}
        />
      )}
    </div>
  )
}
