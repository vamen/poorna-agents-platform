import { apiClient } from './client'

export interface WorkflowNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: Record<string, unknown>
}

export interface WorkflowEdge {
  id: string
  source: string
  target: string
  data?: Record<string, unknown>
}

export interface GraphDefinition {
  nodes: WorkflowNode[]
  edges: WorkflowEdge[]
}

export interface WorkflowSummary {
  id: string
  name: string
  template_slug: string | null
  status: string
  created_at: string
}

export interface Workflow extends WorkflowSummary {
  org_id: string
  graph_definition: GraphDefinition
  compiled_graph: Record<string, unknown> | null
  temporal_workflow_id: string | null
  created_by: string
  updated_at: string | null
}

export interface WorkflowTemplate {
  slug: string
  name: string
  description: string
  graph_definition: GraphDefinition
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
}

export const workflowsApi = {
  listTemplates: () => apiClient.get<WorkflowTemplate[]>('/api/workflows/templates').then(r => r.data),
  getTemplate: (slug: string) => apiClient.get<WorkflowTemplate>(`/api/workflows/templates/${slug}`).then(r => r.data),
  list: () => apiClient.get<WorkflowSummary[]>('/api/workflows').then(r => r.data),
  get: (id: string) => apiClient.get<Workflow>(`/api/workflows/${id}`).then(r => r.data),
  create: (data: { name: string; template_slug?: string; graph_definition: GraphDefinition }) =>
    apiClient.post<Workflow>('/api/workflows', data).then(r => r.data),
  update: (id: string, data: { name?: string; graph_definition?: GraphDefinition }) =>
    apiClient.patch<Workflow>(`/api/workflows/${id}`, data).then(r => r.data),
  delete: (id: string) => apiClient.delete(`/api/workflows/${id}`),
  validate: (id: string) => apiClient.post<ValidationResult>(`/api/workflows/${id}/validate`).then(r => r.data),
  deploy: (id: string) => apiClient.post<{ status: string; temporal_workflow_id: string }>(`/api/workflows/${id}/deploy`).then(r => r.data),
  pause: (id: string) => apiClient.post<{ status: string }>(`/api/workflows/${id}/pause`).then(r => r.data),
  resume: (id: string) => apiClient.post<{ status: string }>(`/api/workflows/${id}/resume`).then(r => r.data),
  listSessions: (id: string) => apiClient.get(`/api/workflows/${id}/sessions`).then(r => r.data),
}
