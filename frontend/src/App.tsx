import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Login } from './pages/Login'
import { Workspace, WorkflowList } from './pages/Workspace'
import { WorkflowCanvas } from './pages/WorkflowCanvas'
import { AgentList } from './pages/AgentList'
import { AgentDetail } from './pages/AgentDetail'
import { AgentDefinitions } from './pages/AgentDefinitions'
import { CustomAgentEditor } from './pages/CustomAgentEditor'
import { SessionMonitor } from './pages/SessionMonitor'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('auth_token')
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/workspace"
            element={
              <RequireAuth>
                <Workspace />
              </RequireAuth>
            }
          >
            <Route index element={<WorkflowList />} />
            <Route path="canvas/:id" element={<WorkflowCanvas />} />
            <Route path="agents" element={<AgentList />} />
            <Route path="agents/:id" element={<AgentDetail />} />
            <Route path="agent-definitions" element={<AgentDefinitions />} />
            <Route path="agent-definitions/new" element={<CustomAgentEditor />} />
            <Route path="agent-definitions/:id" element={<CustomAgentEditor />} />
            <Route path="monitor" element={<SessionMonitor />} />
          </Route>
          <Route path="*" element={<Navigate to="/workspace" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
