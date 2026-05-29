/**
 * RunsMonitor — Temporal-style live view of workflow runs and agent message logs.
 *
 * Layout:
 *   Left  — runs list for the selected workflow (auto-refreshes every 5 s)
 *   Right — live SSE message log for the selected run
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { workflowsApi } from '../api/workflows'
import { sessionsApi, type AgentMessage, type Session } from '../api/sessions'
import {
  Activity,
  ChevronRight,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  ArrowRight,
  RefreshCw,
  Radio,
} from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

// ── helpers ──────────────────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ago`
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'running') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        running
      </span>
    )
  }
  if (status === 'completed') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5">
        <CheckCircle2 className="w-3 h-3" />
        completed
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-full px-2 py-0.5">
        <XCircle className="w-3 h-3" />
        failed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-500 bg-gray-100 border border-gray-200 rounded-full px-2 py-0.5">
      {status}
    </span>
  )
}

// ── AgentLabel ────────────────────────────────────────────────────────────────

function AgentLabel({ type, refId, name }: { type: string; refId: string; name: string }) {
  const label = name || refId.slice(0, 8)
  const isAgent = type === 'agent'
  return (
    <span
      className={`inline-block font-mono text-xs rounded px-1.5 py-0.5 border truncate max-w-[110px] ${
        isAgent
          ? 'bg-violet-50 border-violet-200 text-violet-700'
          : 'bg-amber-50 border-amber-200 text-amber-700'
      }`}
      title={`${type}:${refId}`}
    >
      {label}
    </span>
  )
}

// ── MessageRow ────────────────────────────────────────────────────────────────

function MessageRow({ msg, index }: { msg: AgentMessage; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const hasPayload = msg.payload && Object.keys(msg.payload).length > 0

  return (
    <div
      className={`border-l-2 pl-3 py-1.5 ${
        msg.status === 'failed'
          ? 'border-red-400'
          : msg.status === 'delivered'
          ? 'border-emerald-400'
          : 'border-blue-300'
      }`}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      {/* header row */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* sender → recipient */}
        <AgentLabel type={msg.sender_type} refId={msg.sender_ref_id} name={msg.sender_name} />
        <ArrowRight className="w-3 h-3 text-gray-400 flex-shrink-0" />
        <AgentLabel type={msg.recipient_type} refId={msg.recipient_ref_id} name={msg.recipient_name} />

        {/* event badge */}
        <span className="ml-1 bg-indigo-100 text-indigo-700 text-[11px] font-medium rounded px-2 py-0.5 border border-indigo-200">
          {msg.event_name}
        </span>

        <span className="ml-auto text-[10px] text-gray-400 whitespace-nowrap">
          {new Date(msg.created_at).toLocaleTimeString()}
        </span>

        {hasPayload && (
          <button
            onClick={() => setExpanded(v => !v)}
            className="text-[10px] text-gray-400 hover:text-gray-600 ml-1"
          >
            {expanded ? '▲ hide' : '▼ payload'}
          </button>
        )}
      </div>

      {/* payload */}
      {expanded && hasPayload && (
        <pre className="mt-1.5 text-[11px] font-mono text-gray-600 bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto max-h-48 whitespace-pre-wrap">
          {JSON.stringify(msg.payload, null, 2)}
        </pre>
      )}
    </div>
  )
}

// ── LiveStream ────────────────────────────────────────────────────────────────

function LiveStream({ session }: { session: Session }) {
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [liveStatus, setLiveStatus] = useState(session.status)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Load existing messages first, then open SSE
    sessionsApi.listMessages(session.id).then(setMessages).catch(() => {})

    const url = `${API_URL}/api/sessions/${session.id}/stream`
    const es = new EventSource(url)

    es.addEventListener('agent_message', (e) => {
      const data = JSON.parse(e.data) as AgentMessage
      setMessages(prev => {
        if (prev.find(m => m.id === data.id)) return prev
        return [...prev, data]
      })
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
    })

    es.addEventListener('session_status', (e) => {
      const data = JSON.parse(e.data)
      setLiveStatus(data.status)
      es.close()
    })

    es.addEventListener('error', () => es.close())
    return () => es.close()
  }, [session.id])

  return (
    <div className="flex flex-col h-full">
      {/* run header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 bg-gray-50/60">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-mono text-gray-500">{session.id.slice(0, 16)}…</span>
            <StatusBadge status={liveStatus} />
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-xs text-gray-500">trigger:</span>
            <span className="text-xs font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded px-1.5 py-0.5">
              {session.trigger_event}
            </span>
            <span className="text-xs text-gray-400 ml-auto">
              {timeAgo(session.started_at)}
            </span>
          </div>
        </div>
      </div>

      {/* trigger payload */}
      {session.trigger_payload && Object.keys(session.trigger_payload).length > 0 && (
        <details className="border-b border-gray-100">
          <summary className="px-4 py-2 text-xs text-gray-500 cursor-pointer hover:bg-gray-50 select-none">
            Trigger payload ▸
          </summary>
          <pre className="px-4 pb-3 text-[11px] font-mono text-gray-600 whitespace-pre-wrap overflow-x-auto max-h-32">
            {JSON.stringify(session.trigger_payload, null, 2)}
          </pre>
        </details>
      )}

      {/* messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <Radio className="w-8 h-8 mb-2 opacity-40" />
            <p className="text-sm">Waiting for agent messages…</p>
          </div>
        ) : (
          messages.map((m, i) => <MessageRow key={m.id} msg={m} index={i} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

// ── SessionMonitor (main) ──────────────────────────────────────────────────────

export function SessionMonitor() {
  const { data: workflows = [] } = useQuery({
    queryKey: ['workflows'],
    queryFn: workflowsApi.list,
    refetchInterval: 10_000,
  })

  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [selectedSession, setSelectedSession] = useState<Session | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const selectedWorkflow = workflows.find(w => w.id === selectedWorkflowId)

  // Auto-select first workflow
  useEffect(() => {
    if (!selectedWorkflowId && workflows.length > 0) {
      setSelectedWorkflowId(workflows[0].id)
    }
  }, [workflows, selectedWorkflowId])

  const fetchSessions = useCallback(async (wfId: string) => {
    if (!wfId) return
    const data = await workflowsApi.listSessions(wfId)
    setSessions(data)
    // Auto-select the most recent session if none selected
    setSelectedSession(prev => prev ?? (data[0] ?? null))
  }, [])

  // Fetch on workflow change, then poll every 5 s
  useEffect(() => {
    if (!selectedWorkflowId) return
    setSessions([])
    setSelectedSession(null)
    fetchSessions(selectedWorkflowId)
    const iv = setInterval(() => fetchSessions(selectedWorkflowId), 5000)
    return () => clearInterval(iv)
  }, [selectedWorkflowId, fetchSessions])

  const handleRefresh = async () => {
    setRefreshing(true)
    await fetchSessions(selectedWorkflowId)
    setRefreshing(false)
  }

  return (
    <div className="flex flex-col h-full bg-white">
      {/* top bar */}
      <div className="flex items-center gap-4 px-6 py-3 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-600" />
          <h1 className="text-base font-semibold text-gray-900">Runs Monitor</h1>
        </div>

        {/* workflow picker */}
        <select
          value={selectedWorkflowId}
          onChange={e => setSelectedWorkflowId(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
        >
          {workflows.map(wf => (
            <option key={wf.id} value={wf.id}>{wf.name}</option>
          ))}
        </select>

        {/* temporal status */}
        {selectedWorkflow && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-gray-500">Temporal:</span>
            <StatusBadge status={selectedWorkflow.status} />
          </div>
        )}

        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="ml-auto flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* body */}
      <div className="flex flex-1 min-h-0">
        {/* left — runs list */}
        <div className="w-72 flex-shrink-0 border-r border-gray-200 flex flex-col">
          <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Runs</span>
            <span className="text-xs text-gray-400">{sessions.length}</span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-gray-100">
            {sessions.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-gray-400">
                {selectedWorkflowId ? 'No runs yet' : 'Select a workflow'}
              </div>
            ) : (
              sessions.map(s => (
                <button
                  key={s.id}
                  onClick={() => setSelectedSession(s)}
                  className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${
                    selectedSession?.id === s.id ? 'bg-indigo-50 border-r-2 border-indigo-500' : ''
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <StatusBadge status={s.status} />
                    <span className="text-[10px] text-gray-400 flex items-center gap-0.5">
                      <Clock className="w-3 h-3" />
                      {timeAgo(s.started_at)}
                    </span>
                  </div>
                  <div className="text-xs text-gray-600 truncate font-mono">{s.trigger_event}</div>
                  <div className="text-[10px] text-gray-400 font-mono mt-0.5">{s.id.slice(0, 16)}…</div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* right — live log */}
        <div className="flex-1 min-w-0 flex flex-col">
          {selectedSession ? (
            <LiveStream key={selectedSession.id} session={selectedSession} />
          ) : (
            <div className="flex flex-col items-center justify-center flex-1 text-gray-400 gap-2">
              <ChevronRight className="w-8 h-8 opacity-30" />
              <p className="text-sm">Select a run to see the log</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
