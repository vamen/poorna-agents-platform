import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  agentDefinitionsApi,
  type AgentDefinitionCreate,
  type ToolDefinition,
  type ModelEntry,
  type EventSchema,
  MODEL_OPTIONS,
  type Provider,
  type Strategy,
} from '../api/agentDefinitions'
import { toolsApi, type ToolMeta } from '../api/toolConfigs'
import {
  ArrowLeft, Plus, Trash2,
  ChevronDown, ChevronRight, Info, Server, Copy, Check,
} from 'lucide-react'

// ─── constants ───────────────────────────────────────────────────────────────

const PROVIDERS: { value: Provider; label: string }[] = [
  { value: 'openai',    label: 'OpenAI'    },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'google',    label: 'Google'    },
  { value: 'azure',     label: 'Azure'     },
  { value: 'ollama',    label: 'Ollama'    },
]

const STRATEGIES: { value: Strategy; label: string; hint: string }[] = [
  { value: 'predict', label: 'Predict',              hint: 'Bare LLM call — no scaffolding. Mirrors DSPy Predict.' },
  { value: 'cot',     label: 'Chain-of-Thought',     hint: 'Appends step-by-step reasoning suffix to system prompt.' },
  { value: 'react',   label: 'ReAct',                hint: 'Thought → Action → Observation loop. Requires tools.' },
]

const PAYLOAD_TYPES = ['string', 'number', 'boolean', 'object', 'array', 'any']

const STANDARD_INPUT_VARS = [
  { name: 'event_name',    desc: 'Triggering event name' },
  { name: 'payload',       desc: 'Event payload as JSON' },
  { name: 'session_id',    desc: 'Workflow session UUID' },
  { name: 'from_agent_id', desc: 'Upstream agent UUID' },
  { name: 'timestamp',     desc: 'ISO-8601 UTC datetime' },
]

// ─── JSON preview ─────────────────────────────────────────────────────────────

/** Syntax-highlight a JSON string with Tailwind colour classes. */
function highlightJson(json: string): React.ReactNode {
  const tokens = json.split(/("(?:[^"\\]|\\.)*"(?:\s*:)?|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[{}[\],])/g)
  return tokens.map((tok, i) => {
    if (!tok) return null
    // key (string followed by colon)
    if (/^".*":$/.test(tok)) return <span key={i} className="text-sky-400">{tok}</span>
    // string value
    if (/^"/.test(tok)) return <span key={i} className="text-emerald-400">{tok}</span>
    // boolean / null
    if (tok === 'true' || tok === 'false') return <span key={i} className="text-amber-400">{tok}</span>
    if (tok === 'null') return <span key={i} className="text-red-400">{tok}</span>
    // number
    if (/^-?\d/.test(tok)) return <span key={i} className="text-violet-400">{tok}</span>
    // braces / brackets / comma
    if (/^[{}[\],]$/.test(tok)) return <span key={i} className="text-gray-500">{tok}</span>
    // whitespace / other
    return <span key={i}>{tok}</span>
  })
}

function JsonPreview({ payload }: { payload: AgentDefinitionCreate }) {
  const [copied, setCopied] = useState(false)
  const json = JSON.stringify(payload, null, 2)

  const copy = () => {
    navigator.clipboard.writeText(json)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="flex flex-col h-full bg-gray-950 rounded-xl border border-gray-800 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-800">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Live JSON</span>
        <button
          onClick={copy}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre className="flex-1 overflow-auto px-4 py-3 text-[11.5px] font-mono leading-relaxed text-gray-300">
        {highlightJson(json)}
      </pre>
    </div>
  )
}

// ─── sub-components ──────────────────────────────────────────────────────────

function Section({ title, hint, children, defaultOpen = true }: {
  title: string; hint?: string; children: React.ReactNode; defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <button type="button" onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-5 py-4 text-left hover:bg-gray-50 transition-colors">
        {open
          ? <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0" />
          : <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />}
        <span className="font-semibold text-gray-900">{title}</span>
        {hint && <span className="text-xs text-gray-400 font-normal ml-1">— {hint}</span>}
      </button>
      {open && <div className="px-5 pb-5 space-y-4 border-t border-gray-100">{children}</div>}
    </div>
  )
}

function Field({ label, required, hint, children }: {
  label: string; required?: boolean; hint?: string; children: React.ReactNode
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        {label}{required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {hint && <p className="text-xs text-gray-400 mb-1.5">{hint}</p>}
      {children}
    </div>
  )
}

const inputCls = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50'

// ─── Model list editor ────────────────────────────────────────────────────────

interface ModelRowState extends ModelEntry {
  _id: string
}

function ModelsEditor({ models, onChange }: {
  models: ModelRowState[]
  onChange: (m: ModelRowState[]) => void
}) {
  const add = () => onChange([...models, {
    _id: crypto.randomUUID(), provider: 'openai',
    name: MODEL_OPTIONS.openai[0],
  }])

  const remove = (id: string) => onChange(models.filter(m => m._id !== id))

  const update = (id: string, patch: Partial<ModelRowState>) =>
    onChange(models.map(m => m._id === id ? { ...m, ...patch } : m))

  return (
    <div className="space-y-3">
      {models.map((m, idx) => {
        const opts = MODEL_OPTIONS[m.provider] || []
        return (
          <div key={m._id} className="border border-gray-200 rounded-lg p-3 space-y-2 bg-gray-50">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-gray-400 w-6">
                {idx === 0 ? 'P' : `F${idx}`}
              </span>
              <select value={m.provider}
                onChange={e => {
                  const p = e.target.value as Provider
                  update(m._id, { provider: p, name: MODEL_OPTIONS[p]?.[0] || '' })
                }}
                className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-400">
                {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
              {opts.length > 0
                ? <select value={m.name} onChange={e => update(m._id, { name: e.target.value })}
                    className="border border-gray-300 rounded px-2 py-1 text-xs flex-1 focus:outline-none focus:ring-1 focus:ring-blue-400">
                    {opts.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                : <input value={m.name} onChange={e => update(m._id, { name: e.target.value })}
                    placeholder="deployment-name"
                    className="border border-gray-300 rounded px-2 py-1 text-xs flex-1 focus:outline-none focus:ring-1 focus:ring-blue-400" />
              }
              {models.length > 1 &&
                <button type="button" onClick={() => remove(m._id)}
                  className="p-1 text-gray-400 hover:text-red-500">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>}
            </div>
          </div>
        )
      })}
      <div className="flex items-center gap-3">
        <button type="button" onClick={add}
          className="flex items-center gap-1 text-sm text-blue-600 hover:underline">
          <Plus className="w-3.5 h-3.5" /> Add fallback model
        </button>
        <span className="text-xs text-gray-400">P = primary · F1, F2… = fallbacks tried in order</span>
      </div>
    </div>
  )
}

// ─── Events editor ────────────────────────────────────────────────────────────

interface EventRowState {
  _id: string
  name: string
  event_schema_type: 'json' | 'string'
  value: { key: string; type: string }[]
}

function EventsEditor({ events, onChange }: {
  events: EventRowState[]
  onChange: (rows: EventRowState[]) => void
}) {
  const add = () => onChange([...events, {
    _id: crypto.randomUUID(), name: '', event_schema_type: 'json', value: [],
  }])
  const remove = (id: string) => onChange(events.filter(e => e._id !== id))
  const update = (id: string, patch: Partial<EventRowState>) =>
    onChange(events.map(e => e._id === id ? { ...e, ...patch } : e))

  const addField = (id: string) => {
    const ev = events.find(e => e._id === id)!
    update(id, { value: [...ev.value, { key: '', type: 'string' }] })
  }
  const removeField = (id: string, fi: number) => {
    const ev = events.find(e => e._id === id)!
    update(id, { value: ev.value.filter((_, i) => i !== fi) })
  }
  const updateField = (id: string, fi: number, patch: Partial<{ key: string; type: string }>) => {
    const ev = events.find(e => e._id === id)!
    update(id, { value: ev.value.map((f, i) => i === fi ? { ...f, ...patch } : f) })
  }

  return (
    <div className="space-y-3">
      {events.length === 0 && (
        <p className="text-xs text-gray-400 italic">No events yet. At least one is required.</p>
      )}
      {events.map((ev, idx) => (
        <div key={ev._id} className="border border-gray-200 rounded-lg p-3 space-y-2 bg-gray-50">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-500 w-5">{idx + 1}.</span>
            <input value={ev.name}
              onChange={e => update(ev._id, { name: e.target.value })}
              placeholder="event.name  (e.g. result.success)"
              className={`${inputCls} flex-1 text-xs`} />
            <select value={ev.event_schema_type}
              onChange={e => update(ev._id, { event_schema_type: e.target.value as 'json' | 'string' })}
              className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none">
              <option value="json">json</option>
              <option value="string">string</option>
            </select>
            <button type="button" onClick={() => remove(ev._id)}
              className="p-1 text-gray-400 hover:text-red-500">
              <Trash2 className="w-4 h-4" />
            </button>
          </div>

          {ev.event_schema_type === 'json' && (
            <div className="ml-7 space-y-1.5">
              <p className="text-xs text-gray-500 font-medium">Payload fields (value)</p>
              {ev.value.map((field, fi) => (
                <div key={fi} className="flex items-center gap-2">
                  <input value={field.key}
                    onChange={e => updateField(ev._id, fi, { key: e.target.value })}
                    placeholder="field_name"
                    className="border border-gray-300 rounded px-2 py-1 text-xs flex-1 focus:outline-none focus:ring-1 focus:ring-blue-400" />
                  <select value={field.type}
                    onChange={e => updateField(ev._id, fi, { type: e.target.value })}
                    className="border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none">
                    {PAYLOAD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <button type="button" onClick={() => removeField(ev._id, fi)}
                    className="p-0.5 text-gray-400 hover:text-red-400">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
              <button type="button" onClick={() => addField(ev._id)}
                className="text-xs text-blue-600 hover:underline">+ Add field</button>
            </div>
          )}
        </div>
      ))}
      <button type="button" onClick={add}
        className="flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <Plus className="w-3.5 h-3.5" /> Add event
      </button>
    </div>
  )
}

// ─── form state helpers ───────────────────────────────────────────────────────

interface FormState {
  name: string
  display_name: string
  description: string
  is_long_running: boolean
  strategy: Strategy
  max_iterations: number
  system_prompt: string
  user_prompt: string
  tools: string[]
  mcp_servers: string[]
  context_messages: number
}

const DEFAULT_FORM: FormState = {
  name: '', display_name: '', description: '',
  is_long_running: false, strategy: 'cot', max_iterations: 10,
  system_prompt: 'You are a helpful assistant.',
  user_prompt: 'Event: {{ event_name }}\n\nPayload:\n{{ payload }}',
  tools: [],
  mcp_servers: [],
  context_messages: 0,
}

function toModelRows(model: { provider: string; name: string }[]): ModelRowState[] {
  return model.map(m => ({
    _id: crypto.randomUUID(),
    provider: m.provider as Provider,
    name: m.name,
  }))
}

function toEventRows(events: EventSchema[]): EventRowState[] {
  return events.map(e => ({
    _id: crypto.randomUUID(),
    name: e.name,
    event_schema_type: e.payload.event_schema_type,
    value: e.payload.event_schema_type === 'json' && typeof e.payload.value === 'object' && e.payload.value
      ? Object.entries(e.payload.value as Record<string, string>).map(([key, type]) => ({ key, type }))
      : [],
  }))
}

function buildPayload(form: FormState, modelRows: ModelRowState[], eventRows: EventRowState[]): AgentDefinitionCreate {
  const models: ModelEntry[] = modelRows.map(m => ({
    provider: m.provider,
    name: m.name,
  }))

  const events: EventSchema[] = eventRows.map(ev => ({
    name: ev.name,
    payload: ev.event_schema_type === 'json'
      ? {
          event_schema_type: 'json' as const,
          value: Object.fromEntries(ev.value.filter(f => f.key).map(f => [f.key, f.type])),
        }
      : { event_schema_type: 'string' as const },
  }))

  return {
    name: form.name,
    display_name: form.display_name,
    description: form.description || undefined,
    is_long_running: form.is_long_running,
    reasoning: {
      strategy: form.strategy,
      ...(form.strategy === 'react' ? { max_iterations: form.max_iterations } : {}),
      model: models,
      prompt: { system: form.system_prompt, user: form.user_prompt },
      tools: form.tools,
      mcp_servers: form.mcp_servers,
      context_messages: form.context_messages,
    },
    events,
  }
}

// ─── main component ───────────────────────────────────────────────────────────

export function CustomAgentEditor() {
  const { id } = useParams<{ id: string }>()
  const isEdit = Boolean(id)
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: toolDefs = [] } = useQuery<ToolDefinition[]>({
    queryKey: ['agentDefinitionTools'],
    queryFn: agentDefinitionsApi.listTools,
  })

  const { data: allToolMetas = [] } = useQuery<ToolMeta[]>({
    queryKey: ['tools'],
    queryFn: toolsApi.listTools,
  })
  const mcpServerMetas = allToolMetas.filter(t => t.kind === 'mcp_server')

  const { data: existing, isLoading } = useQuery({
    queryKey: ['agentDefinition', id],
    queryFn: () => agentDefinitionsApi.get(id!),
    enabled: isEdit,
  })

  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [modelRows, setModelRows] = useState<ModelRowState[]>([{
    _id: crypto.randomUUID(), provider: 'openai',
    name: MODEL_OPTIONS.openai[0],
  }])
  const [eventRows, setEventRows] = useState<EventRowState[]>([])
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!existing) return
    const r = existing.reasoning
    setForm({
      name: existing.name,
      display_name: existing.display_name,
      description: existing.description || '',
      is_long_running: existing.is_long_running,
      strategy: r.strategy,
      max_iterations: r.max_iterations ?? 10,
      system_prompt: r.prompt.system,
      user_prompt: r.prompt.user,
      tools: r.tools,
      mcp_servers: r.mcp_servers ?? [],
      context_messages: r.context_messages ?? 0,
    })
    setModelRows(toModelRows(r.model))
    setEventRows(toEventRows(existing.events))
  }, [existing])

  const setF = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm(f => ({ ...f, [k]: v }))

  const toggleTool = (name: string) =>
    setF('tools', form.tools.includes(name)
      ? form.tools.filter(t => t !== name)
      : [...form.tools, name])

  const toggleMcpServer = (name: string) =>
    setF('mcp_servers', form.mcp_servers.includes(name)
      ? form.mcp_servers.filter(s => s !== name)
      : [...form.mcp_servers, name])

  const validate = () => {
    const errs: Record<string, string> = {}
    if (!form.name) errs.name = 'Required'
    else if (!/^[a-z][a-z0-9_]*$/.test(form.name)) errs.name = 'snake_case only'
    if (!form.display_name) errs.display_name = 'Required'
    if (!form.system_prompt) errs.system_prompt = 'Required'
    if (!form.user_prompt) errs.user_prompt = 'Required'
    if (modelRows.length === 0) errs.models = 'At least one model required'
    if (eventRows.length === 0) errs.events = 'At least one event required'
    else if (eventRows.some(e => !e.name)) errs.events = 'All events must have a name'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const createMutation = useMutation({
    mutationFn: agentDefinitionsApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agentDefinitions'] })
      qc.invalidateQueries({ queryKey: ['agentTemplates'] })
      navigate('/workspace/agent-definitions')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof agentDefinitionsApi.update>[1] }) =>
      agentDefinitionsApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agentDefinitions'] })
      qc.invalidateQueries({ queryKey: ['agentTemplates'] })
      navigate('/workspace/agent-definitions')
    },
  })

  const isPending = createMutation.isPending || updateMutation.isPending
  const serverError = (createMutation.error as Error | null)?.message
    || (updateMutation.error as Error | null)?.message

  const handleSubmit = () => {
    if (!validate()) return
    const payload = buildPayload(form, modelRows, eventRows)
    if (isEdit && id) {
      const { name: _name, ...updatePayload } = payload
      updateMutation.mutate({ id, data: updatePayload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const livePayload = useMemo(
    () => buildPayload(form, modelRows, eventRows),
    [form, modelRows, eventRows],
  )

  if (isEdit && isLoading) {
    return <div className="flex-1 flex items-center justify-center text-gray-400">Loading…</div>
  }

  return (
    <div className="flex flex-1 min-h-0 bg-gray-50">

      {/* ── left: form ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-4">

        {/* header */}
        <div className="flex items-center gap-3 mb-2">
          <button onClick={() => navigate('/workspace/agent-definitions')}
            className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-500">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {isEdit ? 'Edit Agent Definition' : 'Define Custom Agent'}
            </h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Describe a reusable AI agent with its own model, prompts, tools, and events.
            </p>
          </div>
        </div>

        {/* 1 — Identity */}
        <Section title="Identity">
          <div className="pt-3 grid grid-cols-2 gap-4">
            <Field label="Name" required hint="snake_case, immutable after creation">
              <input value={form.name}
                onChange={e => setF('name', e.target.value.toLowerCase().replace(/\s+/g, '_'))}
                disabled={isEdit} placeholder="my_agent"
                className={`${inputCls} ${errors.name ? 'border-red-400' : ''}`} />
              {errors.name && <p className="text-xs text-red-500 mt-1">{errors.name}</p>}
            </Field>
            <Field label="Display name" required>
              <input value={form.display_name} onChange={e => setF('display_name', e.target.value)}
                placeholder="My Custom Agent"
                className={`${inputCls} ${errors.display_name ? 'border-red-400' : ''}`} />
              {errors.display_name && <p className="text-xs text-red-500 mt-1">{errors.display_name}</p>}
            </Field>
          </div>
          <Field label="Description">
            <input value={form.description} onChange={e => setF('description', e.target.value)}
              placeholder="What does this agent do?" className={inputCls} />
          </Field>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={form.is_long_running}
              onChange={e => setF('is_long_running', e.target.checked)} />
            <span className="text-sm text-gray-700">Long-running</span>
            <span className="text-xs text-gray-400">(durable process — watchers, listeners)</span>
          </label>
        </Section>

        {/* 2 — Reasoning */}
        <Section title="Reasoning" hint="strategy, models, prompt, tools">
          <div className="pt-3 space-y-3">
            {STRATEGIES.map(s => (
              <label key={s.value} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                form.strategy === s.value ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
              }`}>
                <input type="radio" name="strategy" value={s.value}
                  checked={form.strategy === s.value}
                  onChange={() => setF('strategy', s.value)} className="mt-0.5" />
                <div>
                  <div className="text-sm font-medium text-gray-800">{s.label}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{s.hint}</div>
                </div>
              </label>
            ))}

            {form.strategy === 'react' && (
              <Field label="Max iterations" hint="Max Thought/Action/Observation cycles.">
                <input type="number" min={1} max={50} value={form.max_iterations}
                  onChange={e => setF('max_iterations', Number(e.target.value))}
                  className={`${inputCls} w-32`} />
              </Field>
            )}
          </div>

          {/* Models */}
          <div className="border-t border-gray-100 pt-4">
            <p className="text-sm font-medium text-gray-700 mb-2">
              Models <span className="text-red-500">*</span>
              <span className="text-xs text-gray-400 font-normal ml-1">— primary + optional fallbacks</span>
            </p>
            {errors.models && <p className="text-xs text-red-500 mb-2">{errors.models}</p>}
            <ModelsEditor models={modelRows} onChange={setModelRows} />
          </div>

          {/* Prompt */}
          <div className="border-t border-gray-100 pt-4 space-y-3">
            <div className="p-3 bg-blue-50 border border-blue-100 rounded-lg flex gap-2">
              <Info className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-medium text-blue-700 mb-1">Available template variables</p>
                <div className="flex flex-wrap gap-1.5">
                  {STANDARD_INPUT_VARS.map(v => (
                    <span key={v.name} title={v.desc}
                      className="px-1.5 py-0.5 bg-white border border-blue-200 rounded text-xs font-mono text-blue-700 cursor-help">
                      {'{{ '}{v.name}{' }}'}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <Field label="System prompt" required
              hint="Sets the agent's role. Strategy suffix appended automatically at runtime.">
              <textarea rows={5} value={form.system_prompt}
                onChange={e => setF('system_prompt', e.target.value)}
                className={`${inputCls} resize-y font-mono text-xs leading-relaxed ${errors.system_prompt ? 'border-red-400' : ''}`} />
              {errors.system_prompt && <p className="text-xs text-red-500 mt-1">{errors.system_prompt}</p>}
            </Field>

            <Field label="User prompt template" required
              hint="Rendered per-message with StandardMessage variables.">
              <textarea rows={4} value={form.user_prompt}
                onChange={e => setF('user_prompt', e.target.value)}
                className={`${inputCls} resize-y font-mono text-xs leading-relaxed ${errors.user_prompt ? 'border-red-400' : ''}`} />
              {errors.user_prompt && <p className="text-xs text-red-500 mt-1">{errors.user_prompt}</p>}
            </Field>
          </div>

          {/* Conversation history */}
          <div className="border-t border-gray-100 pt-4">
            <Field label="Conversation history"
              hint="Number of prior session messages to include as context on each run (0 = disabled).">
              <div className="flex items-center gap-3">
                <input type="number" min={0} max={100} value={form.context_messages}
                  onChange={e => setF('context_messages', Math.max(0, Number(e.target.value)))}
                  className={`${inputCls} w-24`} />
                <span className="text-xs text-gray-400">messages</span>
              </div>
            </Field>
          </div>

          {/* Tools */}
          <div className="border-t border-gray-100 pt-4">
            <p className="text-sm font-medium text-gray-700 mb-1">
              Tools
              <span className="text-xs text-gray-400 font-normal ml-1">— only meaningful for ReAct</span>
            </p>
            {form.tools.length > 0 && (
              <p className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
                🔑 Tool credentials (API keys, OAuth tokens) are configured per agent instance —
                open the agent on the workflow canvas after creation to connect each tool.
              </p>
            )}
            <div className="space-y-2">
              {toolDefs.map(tool => {
                const selected = form.tools.includes(tool.name)
                return (
                  <label key={tool.name} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    selected ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-gray-300'
                  } ${tool.phase2_only ? 'opacity-50' : ''}`}>
                    <input type="checkbox" checked={selected}
                      onChange={() => toggleTool(tool.name)}
                      disabled={tool.phase2_only} className="mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-mono font-medium text-gray-800">{tool.name}</span>
                        {tool.phase2_only && (
                          <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">Phase 2</span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5">{tool.description}</p>
                    </div>
                  </label>
                )
              })}
            </div>
          </div>

          {/* MCP Servers */}
          {mcpServerMetas.length > 0 && (
            <div className="border-t border-gray-100 pt-4">
              <p className="text-sm font-medium text-gray-700 mb-1">
                MCP Servers
                <span className="text-xs text-gray-400 font-normal ml-1">— external services via MCP protocol</span>
              </p>
              <p className="text-xs text-gray-400 mb-2">
                Credentials are configured per agent instance after creation.
              </p>
              <div className="space-y-2">
                {mcpServerMetas.map(mcp => {
                  const selected = form.mcp_servers.includes(mcp.name)
                  return (
                    <label key={mcp.name} className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      selected ? 'border-violet-400 bg-violet-50' : 'border-gray-200 hover:border-gray-300'
                    }`}>
                      <input type="checkbox" checked={selected}
                        onChange={() => toggleMcpServer(mcp.name)} className="mt-0.5" />
                      <Server className={`w-4 h-4 mt-0.5 flex-shrink-0 ${selected ? 'text-violet-600' : 'text-gray-400'}`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-gray-800">{mcp.display_name}</span>
                          <span className="text-xs font-mono text-gray-400">{mcp.name}</span>
                          {mcp.phase === 2 && (
                            <span className="text-xs bg-violet-100 text-violet-600 px-1.5 py-0.5 rounded">Phase 2</span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mt-0.5">{mcp.description}</p>
                      </div>
                    </label>
                  )
                })}
              </div>
            </div>
          )}
        </Section>

        {/* 3 — Events */}
        <Section title="Events" hint="output events this agent can emit (required)">
          <div className="pt-3">
            {errors.events && <p className="text-xs text-red-500 mb-2">{errors.events}</p>}
            <EventsEditor events={eventRows} onChange={setEventRows} />
          </div>
        </Section>

        {serverError && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
            {serverError}
          </div>
        )}

        <div className="flex items-center justify-end gap-3 pt-2 pb-8">
          <button type="button" onClick={() => navigate('/workspace/agent-definitions')}
            className="px-5 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm hover:bg-gray-50">
            Cancel
          </button>
          <button type="button" onClick={handleSubmit} disabled={isPending}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
            {isPending
              ? (isEdit ? 'Saving…' : 'Creating…')
              : (isEdit ? 'Save changes' : 'Create agent')}
          </button>
        </div>
      </div>
      </div>

      {/* ── right: live JSON preview ──────────────────────────────── */}
      <div className="w-[420px] flex-shrink-0 border-l border-gray-200 p-4 overflow-hidden flex flex-col">
        <JsonPreview payload={livePayload} />
      </div>

    </div>
  )
}
