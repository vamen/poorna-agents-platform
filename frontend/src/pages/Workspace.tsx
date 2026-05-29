import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { workflowsApi, type WorkflowSummary } from '../api/workflows'
import { Bot, GitBranch, Activity, Plus, LogOut, Zap, Cpu } from 'lucide-react'
import { cn } from '../lib/utils'

const STATUS_DOTS: Record<string, string> = {
  draft: 'bg-gray-400',
  active: 'bg-green-400',
  paused: 'bg-amber-400',
  failed: 'bg-red-400',
}

export function Workspace() {
  const navigate = useNavigate()
  const location = useLocation()

  const { data: workflows = [] } = useQuery<WorkflowSummary[]>({
    queryKey: ['workflows'],
    queryFn: workflowsApi.list,
    refetchInterval: 10000,
  })

  const logout = () => {
    localStorage.removeItem('auth_token')
    navigate('/login')
  }

  const navItems = [
    { to: '/workspace', label: 'Workflows', icon: GitBranch, exact: true },
    { to: '/workspace/agents', label: 'Agents', icon: Zap },
    { to: '/workspace/agent-definitions', label: 'Agent Types', icon: Cpu },
    { to: '/workspace/monitor', label: 'Runs', icon: Activity },
  ]

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <div className="w-56 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
        <div className="px-4 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <span className="font-bold text-sm text-gray-900">Agent Platform</span>
          </div>
        </div>

        <nav className="flex-1 px-3 py-3 space-y-0.5">
          {navItems.map(({ to, label, icon: Icon, exact }) => {
            const active = exact
              ? location.pathname === to
              : location.pathname === to || location.pathname.startsWith(to + '/')
            return (
              <Link
                key={to}
                to={to}
                className={cn(
                  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  active ? 'bg-blue-50 text-blue-700' : 'text-gray-600 hover:bg-gray-100'
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            )
          })}

          <div className="pt-3 pb-1">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide px-3 mb-1">
              Workflows
            </p>
          </div>

          {workflows.map((wf) => (
            <Link
              key={wf.id}
              to={`/workspace/canvas/${wf.id}`}
              className={cn(
                'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors group',
                location.pathname.includes(wf.id)
                  ? 'bg-gray-100 text-gray-900'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900'
              )}
            >
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOTS[wf.status] || 'bg-gray-400'}`} />
              <span className="truncate">{wf.name}</span>
            </Link>
          ))}

          <Link
            to="/workspace/canvas/new"
            className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-blue-600 hover:bg-blue-50 transition-colors"
          >
            <Plus className="w-4 h-4" />
            New Workflow
          </Link>
        </nav>

        <div className="px-3 py-3 border-t border-gray-200">
          <button
            onClick={logout}
            className="flex items-center gap-2.5 px-3 py-2 w-full rounded-lg text-sm text-gray-500 hover:bg-gray-100 transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        <Outlet />
      </div>
    </div>
  )
}

export function WorkflowList() {
  const navigate = useNavigate()
  const { data: workflows = [], isLoading } = useQuery<WorkflowSummary[]>({
    queryKey: ['workflows'],
    queryFn: workflowsApi.list,
  })

  const STATUS_COLORS: Record<string, string> = {
    draft: 'bg-gray-100 text-gray-600',
    active: 'bg-green-100 text-green-700',
    paused: 'bg-amber-100 text-amber-700',
    failed: 'bg-red-100 text-red-700',
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Workflows</h1>
            <p className="text-sm text-gray-500 mt-1">Orchestrate your agents into powerful automations</p>
          </div>
          <button
            onClick={() => navigate('/workspace/canvas/new')}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" />
            New Workflow
          </button>
        </div>

        {isLoading ? (
          <div className="text-center py-12 text-gray-400">Loading…</div>
        ) : workflows.length === 0 ? (
          <div className="text-center py-16 border-2 border-dashed border-gray-200 rounded-xl">
            <GitBranch className="w-10 h-10 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">No workflows yet</p>
            <p className="text-sm text-gray-400 mt-1">Create your first workflow or load a template</p>
            <button
              onClick={() => navigate('/workspace/canvas/new')}
              className="mt-4 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700"
            >
              Get Started
            </button>
          </div>
        ) : (
          <div className="grid gap-3">
            {workflows.map((wf) => (
              <div
                key={wf.id}
                onClick={() => navigate(`/workspace/canvas/${wf.id}`)}
                className="bg-white border border-gray-200 rounded-xl p-4 flex items-center gap-4 cursor-pointer hover:border-blue-300 hover:shadow-sm transition-all"
              >
                <div className={`px-2 py-1 rounded text-xs font-medium ${STATUS_COLORS[wf.status] || STATUS_COLORS.draft}`}>
                  {wf.status}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm text-gray-900">{wf.name}</div>
                  {wf.template_slug && (
                    <div className="text-xs text-gray-400 mt-0.5">Template: {wf.template_slug}</div>
                  )}
                </div>
                <div className="text-xs text-gray-400">
                  {new Date(wf.created_at).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
