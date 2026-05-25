import { create } from 'zustand'
import type { Node, Edge } from 'reactflow'

interface WorkflowStore {
  nodes: Node[]
  edges: Edge[]
  isDirty: boolean
  // Load from server — does NOT mark dirty
  loadCanvas: (data: { nodes: Node[]; edges: Edge[] }) => void
  // Mutations — all mark dirty
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  updateNode: (nodeId: string, patch: Partial<Node['data']>) => void
  setIsDirty: (dirty: boolean) => void
  resetCanvas: () => void
}

export const useWorkflowStore = create<WorkflowStore>((set) => ({
  nodes: [],
  edges: [],
  isDirty: false,

  loadCanvas: ({ nodes, edges }) =>
    set({ nodes, edges, isDirty: false }),

  setNodes: (nodes) => set({ nodes, isDirty: true }),
  setEdges: (edges) => set({ edges, isDirty: true }),

  /** Merge a data patch into one node without replacing the whole array. */
  updateNode: (nodeId, patch) =>
    set((state) => ({
      isDirty: true,
      nodes: state.nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n
      ),
    })),

  setIsDirty: (dirty) => set({ isDirty: dirty }),
  resetCanvas: () => set({ nodes: [], edges: [], isDirty: false }),
}))
