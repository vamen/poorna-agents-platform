/**
 * ToolConfigForm — dynamic credential/config form for a tool or MCP server.
 *
 * Reads ui.yaml fields from the backend and renders appropriate widgets:
 *   text, email, url, password, select, textarea, key_value, oauth2_button
 *
 * Conditions are simple equality expressions: "path == 'value'"
 * e.g. "credential.credential_type == 'oauth2'"
 */

import { useState, useCallback, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toolsApi, type ToolUiField, type ToolUiHints, type ToolConfigResponse } from '../api/toolConfigs'
import { ExternalLink, CheckCircle, Loader2, Key, Pencil } from 'lucide-react'

// ── Secret masking ────────────────────────────────────────────────────────────

/** Show first 4 + dots + last 4 of a secret. Short secrets are fully masked. */
function maskSecret(val: string): string {
  if (!val) return ''
  if (val.length <= 8) return '••••••••'
  return val.slice(0, 4) + '••••••••' + val.slice(-4)
}

/** Seed any select widget to its first option so conditional fields are
 *  immediately visible (e.g. the oauth2_button for gmail). */
function buildInitialValues(ui: ToolUiHints): Record<string, unknown> {
  let values: Record<string, unknown> = {}
  for (const field of ui.fields ?? []) {
    if (field.widget === 'select' && field.options && field.options.length > 0) {
      values = setNestedValue(values, field.path, field.options[0].value)
    }
  }
  return values
}

// ── Condition evaluator ───────────────────────────────────────────────────────

function evalCondition(condition: string | undefined, values: Record<string, unknown>): boolean {
  if (!condition) return true
  // Parse "path == 'value'" or 'path == "value"'
  const match = condition.match(/^([\w.]+)\s*==\s*['"](.+)['"]$/)
  if (!match) return true
  const [, path, expected] = match
  const actual = getNestedValue(values, path)
  return String(actual) === expected
}

function getNestedValue(obj: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((cur, key) => {
    if (cur && typeof cur === 'object') return (cur as Record<string, unknown>)[key]
    return undefined
  }, obj)
}

function setNestedValue(
  obj: Record<string, unknown>,
  path: string,
  value: unknown
): Record<string, unknown> {
  const keys = path.split('.')
  const result = { ...obj }
  let cur: Record<string, unknown> = result
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i]
    cur[k] = cur[k] && typeof cur[k] === 'object' ? { ...(cur[k] as object) } : {}
    cur = cur[k] as Record<string, unknown>
  }
  cur[keys[keys.length - 1]] = value
  return result
}

// ── Widget components ─────────────────────────────────────────────────────────

function TextWidget({
  field,
  value,
  onChange,
  type = 'text',
}: {
  field: ToolUiField
  value: string
  onChange: (v: string) => void
  type?: string
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={field.placeholder}
      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
    />
  )
}

function SelectWidget({
  field,
  value,
  onChange,
}: {
  field: ToolUiField
  value: string
  onChange: (v: string) => void
}) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
    >
      <option value="">— choose —</option>
      {field.options?.map(o => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  )
}

function KeyValueWidget({
  value,
  onChange,
}: {
  value: Record<string, string>
  onChange: (v: Record<string, string>) => void
}) {
  const entries = Object.entries(value)
  const addRow = () => onChange({ ...value, '': '' })
  const updateKey = (oldKey: string, newKey: string) => {
    const updated: Record<string, string> = {}
    for (const [k, v] of entries) {
      updated[k === oldKey ? newKey : k] = v
    }
    onChange(updated)
  }
  const updateVal = (key: string, val: string) => onChange({ ...value, [key]: val })
  const removeRow = (key: string) => {
    const updated = { ...value }
    delete updated[key]
    onChange(updated)
  }

  return (
    <div className="space-y-1.5">
      {entries.map(([k, v], i) => (
        <div key={i} className="flex gap-2">
          <input
            value={k}
            onChange={e => updateKey(k, e.target.value)}
            placeholder="Header"
            className="flex-1 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <input
            value={v}
            onChange={e => updateVal(k, e.target.value)}
            placeholder="Value"
            className="flex-1 border border-gray-300 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            onClick={() => removeRow(k)}
            className="text-gray-400 hover:text-red-500 text-xs px-1"
          >✕</button>
        </div>
      ))}
      <button
        onClick={addRow}
        className="text-xs text-blue-600 hover:text-blue-700"
      >+ Add header</button>
    </div>
  )
}

function OAuth2ButtonWidget({
  field,
  agentId,
  toolName,
  oauthProvider,
  existingConfig,
  onBeforeOAuth,
}: {
  field: ToolUiField
  agentId: string
  toolName: string
  oauthProvider?: string
  existingConfig: ToolConfigResponse | undefined
  onBeforeOAuth?: () => Promise<void>
}) {
  const [loading, setLoading] = useState(false)
  const [preError, setPreError] = useState<string | null>(null)

  // Check if already connected (oauth2 needs refresh_token; oauth1 needs access_token)
  const credential = existingConfig?.config?.credential as Record<string, unknown> | undefined
  const isConnected =
    (credential?.credential_type === 'oauth2' && !!credential?.refresh_token) ||
    (credential?.credential_type === 'oauth1' && !!credential?.access_token)

  const handleConnect = async () => {
    setLoading(true)
    setPreError(null)
    try {
      // Ensure the agent row exists before opening OAuth popup
      if (onBeforeOAuth) await onBeforeOAuth()
      const { auth_url } = await toolsApi.getOAuthUrl(agentId, toolName, oauthProvider)

      // Open in a popup so the app tab stays intact
      const popup = window.open(
        auth_url,
        'oauth_popup',
        'width=600,height=720,scrollbars=yes,resizable=yes'
      )
      if (!popup) {
        // Popup blocked — fall back to full redirect
        window.location.href = auth_url
        return
      }

      // Poll until the popup closes or redirects back to localhost
      const poll = setInterval(() => {
        try {
          if (!popup || popup.closed) {
            clearInterval(poll)
            setLoading(false)
            onSaved?.()   // re-fetch tool configs
            return
          }
          const href = popup.location.href
          // Once redirected back to our frontend (localhost / same origin)
          if (href && href.includes(window.location.hostname)) {
            clearInterval(poll)
            popup.close()
            setLoading(false)
            onSaved?.()
          }
        } catch {
          // Cross-origin (still on Twitter/Google) — keep polling
        }
      }, 500)
    } catch (err) {
      setPreError(err instanceof Error ? err.message : 'Failed to connect')
      setLoading(false)
    }
  }

  if (isConnected) {
    return (
      <div className="flex items-center gap-2 text-sm text-green-700 bg-green-50 border border-green-200 rounded px-3 py-2">
        <CheckCircle className="w-4 h-4 flex-shrink-0" />
        <span>{field.connected_text ?? 'Connected'}</span>
        <button
          onClick={handleConnect}
          className="ml-auto text-xs text-green-600 underline hover:no-underline"
        >
          Reconnect
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <button
        onClick={handleConnect}
        disabled={loading}
        className="flex items-center gap-2 bg-white border border-gray-300 text-gray-700 text-sm font-medium px-4 py-2 rounded hover:bg-gray-50 disabled:opacity-50 w-full justify-center"
      >
        {loading
          ? <Loader2 className="w-4 h-4 animate-spin" />
          : <ExternalLink className="w-4 h-4" />
        }
        {field.button_text ?? 'Connect'}
      </button>
      {preError && <p className="text-xs text-red-500 text-center">{preError}</p>}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  agentId: string
  toolName: string
  existingConfig?: ToolConfigResponse
  /** Called before the OAuth redirect fires — use to create the agent row first. */
  onBeforeOAuth?: () => Promise<void>
  onSaved?: () => void
}

export function ToolConfigForm({ agentId, toolName, existingConfig, onBeforeOAuth, onSaved }: Props) {
  const { data: ui, isLoading } = useQuery({
    queryKey: ['tool-ui', toolName],
    queryFn: () => toolsApi.getUi(toolName),
  })

  const { data: meta } = useQuery({
    queryKey: ['tool-meta-single', toolName],
    queryFn: async () => {
      const tools = await toolsApi.listTools()
      return tools.find(t => t.name === toolName) ?? null
    },
  })

  // Initialise form values: existing config if present, otherwise seed
  // every select widget to its first option so all dependent fields
  // (especially the oauth2_button) are immediately visible.
  const [values, setValues] = useState<Record<string, unknown>>(
    existingConfig?.config ?? {}
  )
  const [seeded, setSeeded] = useState(!!existingConfig)

  // Password fields with saved values start "locked" — shown as masked text
  const [lockedPaths, setLockedPaths] = useState<Set<string>>(new Set())
  const [locksInitialized, setLocksInitialized] = useState(false)

  useEffect(() => {
    if (!ui || seeded) return
    // No existing config — build defaults from UI field definitions
    setValues(buildInitialValues(ui))
    setSeeded(true)
  }, [ui, seeded])

  // Once the UI schema loads, lock all password fields that already have a value
  useEffect(() => {
    if (!ui || locksInitialized) return
    if (!existingConfig?.config) {
      setLocksInitialized(true)
      return
    }
    const locked = new Set<string>()
    for (const field of ui.fields ?? []) {
      if (field.widget === 'password') {
        const v = getNestedValue(existingConfig.config as Record<string, unknown>, field.path)
        if (v && String(v).length > 0) locked.add(field.path)
      }
    }
    setLockedPaths(locked)
    setLocksInitialized(true)
  }, [ui, locksInitialized, existingConfig])

  const upsertMutation = useMutation({
    mutationFn: () =>
      toolsApi.upsertConfig(agentId, toolName, {
        kind: meta?.kind ?? 'tool',
        config: values,
      }),
    onSuccess: () => onSaved?.(),
  })

  const handleChange = useCallback((path: string, value: unknown) => {
    setValues(prev => setNestedValue(prev, path, value))
  }, [])

  if (isLoading) {
    return <div className="text-sm text-gray-400 py-4 text-center">Loading form…</div>
  }

  if (!ui?.fields?.length) {
    return <div className="text-sm text-gray-400 py-4 text-center">No configuration needed.</div>
  }

  const visibleFields = ui.fields.filter(f => evalCondition(f.condition, values))

  return (
    <div className="space-y-4">
      {visibleFields.map(field => {
        const rawValue = getNestedValue(values, field.path)

        // oauth2_button is handled differently — doesn't have a direct value binding
        if (field.widget === 'oauth2_button') {
          return (
            <div key={field.path}>
              {field.label && (
                <label className="block text-xs font-medium text-gray-700 mb-1">{field.label}</label>
              )}
              <OAuth2ButtonWidget
                field={field}
                agentId={agentId}
                toolName={toolName}
                oauthProvider={meta?.oauth_provider}
                existingConfig={existingConfig}
                onBeforeOAuth={onBeforeOAuth}
              />
              {field.help && <p className="text-xs text-gray-400 mt-1">{field.help}</p>}
            </div>
          )
        }

        return (
          <div key={field.path}>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              {field.label}
              {field.sensitive && <Key className="w-3 h-3 inline ml-1 text-gray-400" />}
            </label>

            {field.widget === 'select' ? (
              <SelectWidget
                field={field}
                value={String(rawValue ?? '')}
                onChange={v => handleChange(field.path, v)}
              />
            ) : field.widget === 'textarea' ? (
              <textarea
                value={String(rawValue ?? '')}
                onChange={e => handleChange(field.path, e.target.value)}
                placeholder={field.placeholder}
                rows={5}
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            ) : field.widget === 'key_value' ? (
              <KeyValueWidget
                value={(rawValue as Record<string, string>) ?? {}}
                onChange={v => handleChange(field.path, v)}
              />
            ) : field.widget === 'password' ? (
              lockedPaths.has(field.path) ? (
                /* Saved value — show masked with a Change button */
                <div className="flex items-center gap-2">
                  <span className="flex-1 font-mono text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded px-3 py-1.5 tracking-widest overflow-hidden">
                    {maskSecret(String(rawValue ?? ''))}
                  </span>
                  <button
                    type="button"
                    onClick={() => setLockedPaths(prev => {
                      const next = new Set(prev)
                      next.delete(field.path)
                      return next
                    })}
                    className="flex items-center gap-1 text-xs text-blue-600 hover:underline whitespace-nowrap"
                  >
                    <Pencil className="w-3 h-3" />
                    Change
                  </button>
                </div>
              ) : (
                <TextWidget
                  field={field}
                  value={String(rawValue ?? '')}
                  onChange={v => handleChange(field.path, v)}
                  type="password"
                />
              )
            ) : (
              <TextWidget
                field={field}
                value={String(rawValue ?? '')}
                onChange={v => handleChange(field.path, v)}
                type={field.widget === 'email' ? 'email' : field.widget === 'url' ? 'url' : 'text'}
              />
            )}

            {field.help && <p className="text-xs text-gray-400 mt-1">{field.help}</p>}
          </div>
        )
      })}

      {/* Only show save button for non-oauth2-only forms */}
      {visibleFields.some(f => f.widget !== 'oauth2_button') && (
        <div className="pt-2">
          <button
            onClick={() => upsertMutation.mutate()}
            disabled={upsertMutation.isPending}
            className="w-full bg-blue-600 text-white text-sm font-medium py-2 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {upsertMutation.isPending ? 'Saving…' : 'Save Configuration'}
          </button>
          {upsertMutation.isSuccess && (
            <p className="text-xs text-green-600 text-center mt-1">Saved ✓</p>
          )}
          {upsertMutation.isError && (
            <p className="text-xs text-red-500 text-center mt-1">Save failed. Check values.</p>
          )}
        </div>
      )}
    </div>
  )
}
