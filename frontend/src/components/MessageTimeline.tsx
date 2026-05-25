import type { AgentMessage } from '../api/sessions'
import { ArrowRight } from 'lucide-react'

interface Props {
  messages: AgentMessage[]
}

export function MessageTimeline({ messages }: Props) {
  if (messages.length === 0) {
    return (
      <div className="text-center py-8 text-sm text-gray-400">
        No messages yet. Start a session to see activity.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {messages.map((msg) => (
        <div key={msg.id} className="flex items-start gap-3 text-sm border border-gray-100 rounded-lg p-3 bg-gray-50">
          <div className="flex items-center gap-1 text-xs text-gray-500 min-w-[180px] flex-shrink-0">
            <span className="font-mono bg-white border border-gray-200 rounded px-1.5 py-0.5 truncate max-w-[80px]">
              {msg.from_agent_id.slice(0, 8)}
            </span>
            <ArrowRight className="w-3 h-3 flex-shrink-0" />
            <span className="font-mono bg-white border border-gray-200 rounded px-1.5 py-0.5 truncate max-w-[80px]">
              {msg.to_agent_id.slice(0, 8)}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <span className="inline-block bg-blue-100 text-blue-700 text-xs rounded px-2 py-0.5 mb-1">
              {msg.event_name}
            </span>
            {msg.payload && (
              <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono overflow-hidden max-h-24">
                {JSON.stringify(msg.payload, null, 2)}
              </pre>
            )}
          </div>
          <div className="text-xs text-gray-400 flex-shrink-0 whitespace-nowrap">
            {new Date(msg.created_at).toLocaleTimeString()}
          </div>
        </div>
      ))}
    </div>
  )
}
