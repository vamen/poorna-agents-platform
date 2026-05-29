import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  EdgeProps,
  getStraightPath,
  useNodes,
  useReactFlow,
} from 'reactflow'
import { useQuery } from '@tanstack/react-query'
import { agentsApi, type AgentTemplate } from '../api/agents'
import { ChevronDown, Filter, X } from 'lucide-react'

// ─── types ──────────────────────────────────────────────────────────────────

export interface EdgeData {
  /** Selected event name, e.g. "email.received" */
  event?: string
  /** Optional filter expression, e.g. "payload.confidence > 0.8" */
  filter?: string
}

// ─── helpers ────────────────────────────────────────────────────────────────

function useClickOutside(ref: React.RefObject<HTMLElement>, handler: () => void) {
  useEffect(() => {
    const listener = (e: MouseEvent) => {
      if (!ref.current || ref.current.contains(e.target as Node)) return
      handler()
    }
    document.addEventListener('mousedown', listener)
    return () => document.removeEventListener('mousedown', listener)
  }, [ref, handler])
}

// ─── component ──────────────────────────────────────────────────────────────

export function EdgeEventSelector({
  id,
  source,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps<EdgeData>) {
  const [open, setOpen] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)
  const { setEdges } = useReactFlow()

  // Get available events for the source node
  const nodes = useNodes()
  const sourceNode = nodes.find((n) => n.id === source)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sourceAgentType = (sourceNode?.data as any)?.agentType as string | undefined

  const { data: templates = [] } = useQuery<AgentTemplate[]>({
    queryKey: ['agentTemplates'],
    queryFn: agentsApi.listTemplates,
  })

  const sourceTemplate = templates.find((t) => t.name === sourceAgentType)
  // Qualify short event names with the agent type prefix so they match
  // what agent_cls.event_names() produces and the workflow compiler expects.
  // e.g. "message.received" → "telegram_watcher.message.received"
  const availableEvents = (sourceTemplate?.events ?? []).map((ev) => ({
    ...ev,
    name: sourceAgentType ? `${sourceAgentType}.${ev.name}` : ev.name,
  }))

  // Keep local state in sync with edge data while popover is open
  const [localEvent, setLocalEvent] = useState(data?.event ?? '')
  const [localFilter, setLocalFilter] = useState(data?.filter ?? '')

  useEffect(() => {
    if (open) {
      setLocalEvent(data?.event ?? '')
      setLocalFilter(data?.filter ?? '')
    }
  }, [open, data?.event, data?.filter])

  const close = useCallback(() => setOpen(false), [])
  useClickOutside(popoverRef, close)

  // Commit changes to the edge whenever local state changes
  const commit = useCallback(
    (event: string, filter: string) => {
      setEdges((eds) =>
        eds.map((e) =>
          e.id === id
            ? { ...e, data: { ...e.data, event: event || undefined, filter: filter || undefined } }
            : e
        )
      )
    },
    [id, setEdges]
  )

  const handleEventChange = (value: string) => {
    setLocalEvent(value)
    commit(value, localFilter)
  }

  const handleFilterChange = (value: string) => {
    setLocalFilter(value)
    commit(localEvent, value)
  }

  const clearFilter = () => {
    setLocalFilter('')
    commit(localEvent, '')
  }

  // ── layout ──────────────────────────────────────────────────────────────
  const [edgePath, labelX, labelY] = getStraightPath({ sourceX, sourceY, targetX, targetY })

  const hasEvent = !!data?.event
  const hasFilter = !!data?.filter
  const isValid = hasEvent

  const edgeColor = isValid ? '#6366f1' : '#9ca3af'

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          strokeWidth: 2,
          stroke: edgeColor,
          strokeDasharray: isValid ? undefined : '5 4',
        }}
        markerEnd="url(#arrow)"
      />

      <EdgeLabelRenderer>
        <div
          ref={popoverRef}
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: 'all',
            zIndex: 10,
          }}
          className="nodrag nopan"
        >
          {/* ── collapsed label ─────────────────────────────────────────── */}
          <button
            onClick={() => setOpen((v) => !v)}
            className={[
              'flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium shadow-sm',
              'border transition-all select-none',
              isValid
                ? 'bg-indigo-50 border-indigo-300 text-indigo-700 hover:bg-indigo-100'
                : 'bg-white border-gray-300 text-gray-400 hover:border-gray-400',
            ].join(' ')}
          >
            <span className="max-w-[120px] truncate">
              {data?.event ?? 'select event'}
            </span>
            {hasFilter && (
              <Filter className="w-2.5 h-2.5 text-indigo-400 flex-shrink-0" />
            )}
            <ChevronDown className={`w-3 h-3 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>

          {/* ── popover ─────────────────────────────────────────────────── */}
          {open && (
            <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-72 bg-white rounded-xl border border-gray-200 shadow-xl overflow-hidden">
              {/* event dropdown */}
              <div className="px-3 pt-3 pb-2">
                <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">
                  Trigger event
                </label>

                {availableEvents.length === 0 ? (
                  <div className="text-xs text-gray-400 italic py-1">
                    {sourceAgentType
                      ? `No events defined for ${sourceAgentType}`
                      : 'Source node has no agent type set'}
                  </div>
                ) : (
                  <select
                    value={localEvent}
                    onChange={(e) => handleEventChange(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-2.5 py-1.5 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                  >
                    <option value="">— choose event —</option>
                    {availableEvents.map((ev) => (
                      <option key={ev.name} value={ev.name}>
                        {ev.name}
                      </option>
                    ))}
                  </select>
                )}

                {/* payload schema hint */}
                {localEvent && (() => {
                  const ev = availableEvents.find((e) => e.name === localEvent)
                  if (!ev) return null
                  const schemaValue = ev.payload.event_schema_type === 'json' && typeof ev.payload.value === 'object'
                    ? ev.payload.value as Record<string, string>
                    : {}
                  const keys = Object.keys(schemaValue)
                  if (keys.length === 0) return null
                  return (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {keys.map((k) => (
                        <span
                          key={k}
                          className="text-[10px] bg-gray-100 text-gray-500 rounded px-1.5 py-0.5 font-mono"
                          title={`${k}: ${schemaValue[k]}`}
                        >
                          payload.{k}
                        </span>
                      ))}
                    </div>
                  )
                })()}
              </div>

              {/* divider */}
              <div className="border-t border-gray-100 mx-3" />

              {/* filter expression */}
              <div className="px-3 pt-2 pb-3">
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-wide flex items-center gap-1">
                    <Filter className="w-3 h-3" />
                    Filter
                    <span className="normal-case font-normal text-gray-400">(optional)</span>
                  </label>
                  {localFilter && (
                    <button
                      onClick={clearFilter}
                      className="text-gray-400 hover:text-red-400 transition-colors"
                      title="Clear filter"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>

                <textarea
                  value={localFilter}
                  onChange={(e) => handleFilterChange(e.target.value)}
                  rows={2}
                  spellCheck={false}
                  placeholder={
                    localEvent
                      ? (() => {
                          const ev = availableEvents.find((e) => e.name === localEvent)
                          const firstKey = ev?.payload.event_schema_type === 'json' && typeof ev.payload.value === 'object'
                            ? Object.keys(ev.payload.value as object)[0]
                            : undefined
                          return `e.g. payload.${firstKey ?? 'value'} == "expected"`
                        })()
                      : 'Select an event first'
                  }
                  className={[
                    'w-full border rounded-lg px-2.5 py-1.5 text-xs font-mono resize-none',
                    'focus:outline-none focus:ring-2 focus:ring-indigo-500',
                    'placeholder:text-gray-300',
                    localFilter ? 'border-indigo-300 bg-indigo-50/40' : 'border-gray-300 bg-white',
                  ].join(' ')}
                />
                <p className="text-[10px] text-gray-400 mt-1">
                  Python expression evaluated against the event payload.
                  Leave blank to pass all events through.
                </p>
              </div>
            </div>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}
