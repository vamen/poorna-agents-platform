import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { workflowsApi } from '../api/workflows'
import { sessionsApi, type AgentMessage, type Session } from '../api/sessions'
import { MessageTimeline } from '../components/MessageTimeline'
import { Activity, Play } from 'lucide-react'
import { useSessionStore } from '../store/sessionStore'

const API_URL = import.meta.env.VITE_API_URL || ''

function SessionStream({ sessionId }: { sessionId: string }) {
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [status, setStatus] = useState('running')
  const esRef = useRef<EventSource | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const url = `${API_URL}/api/sessions/${sessionId}/stream`
    const es = new EventSource(url)
    esRef.current = es

    es.addEventListener('agent_message', (e) => {
      const data = JSON.parse(e.data)
      setMessages((prev) => [...prev, data])
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    })

    es.addEventListener('session_status', (e) => {
      const data = JSON.parse(e.data)
      setStatus(data.status)
      es.close()
    })

    es.addEventListener('error', () => es.close())

    return () => es.close()
  }, [sessionId])

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${status === 'running' ? 'bg-green-400 animate-pulse' : 'bg-gray-400'}`} />
        <span className="text-xs text-gray-500 capitalize">{status}</span>
        <span className="text-xs text-gray-400 ml-auto font-mono">{sessionId.slice(0, 12)}…</span>
      </div>
      <MessageTimeline messages={messages} />
      <div ref={bottomRef} />
    </div>
  )
}

export function SessionMonitor() {
  const { data: workflows = [] } = useQuery({
    queryKey: ['workflows'],
    queryFn: workflowsApi.list,
  })

  const [selectedWorkflow, setSelectedWorkflow] = useState<string>('')
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [showCreateSession, setShowCreateSession] = useState(false)

  useEffect(() => {
    if (!selectedWorkflow) return
    workflowsApi.listSessions(selectedWorkflow).then(setSessions)
  }, [selectedWorkflow])

  const createSession = async () => {
    if (!selectedWorkflow) return
    const session = await sessionsApi.create({
      workflow_id: selectedWorkflow,
      trigger_event: 'email.received',
      trigger_payload: { subject: 'Test', sender: 'test@example.com', body: 'Test body', thread_id: 'T001' },
    })
    setSessions((prev) => [session, ...prev])
    setActiveSessionId(session.id)
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Session Monitor</h1>
            <p className="text-sm text-gray-500 mt-1">Live SSE feed from workflow executions</p>
          </div>
        </div>

        <div className="flex gap-4 mb-6">
          <select
            value={selectedWorkflow}
            onChange={(e) => { setSelectedWorkflow(e.target.value); setActiveSessionId(null) }}
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">Select workflow…</option>
            {workflows.map((wf) => (
              <option key={wf.id} value={wf.id}>{wf.name}</option>
            ))}
          </select>

          {selectedWorkflow && (
            <button
              onClick={createSession}
              className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700"
            >
              <Play className="w-4 h-4" />
              Trigger Mock Session
            </button>
          )}
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-1 border border-gray-200 rounded-xl overflow-hidden">
            <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 text-sm font-medium text-gray-700">Sessions</div>
            {sessions.length === 0 ? (
              <div className="p-4 text-sm text-gray-400 text-center">No sessions</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {sessions.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setActiveSessionId(s.id)}
                    className={`w-full text-left px-4 py-3 hover:bg-gray-50 transition-colors ${activeSessionId === s.id ? 'bg-blue-50' : ''}`}
                  >
                    <div className="text-xs font-mono text-gray-500">{s.id.slice(0, 12)}…</div>
                    <div className="text-xs text-gray-600 mt-0.5">{s.trigger_event}</div>
                    <div className={`text-xs mt-0.5 ${s.status === 'running' ? 'text-green-600' : s.status === 'failed' ? 'text-red-500' : 'text-gray-400'}`}>
                      {s.status}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="col-span-2 border border-gray-200 rounded-xl overflow-hidden">
            <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center gap-2 text-sm font-medium text-gray-700">
              <Activity className="w-4 h-4" />
              Event Stream
            </div>
            <div className="p-4">
              {activeSessionId ? (
                <SessionStream sessionId={activeSessionId} />
              ) : (
                <div className="text-center py-8 text-sm text-gray-400">
                  Select a session to watch events
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
