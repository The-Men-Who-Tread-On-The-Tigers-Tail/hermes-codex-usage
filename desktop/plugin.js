import {
  useQuery,
  queryClient,
  Button,
  Badge,
  Popover,
  PopoverTrigger,
  PopoverContent,
  cn
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'hermes-codex-usage'
const QUERY_KEY = [ID, 'quota']
const POLL_MS = 60 * 1000
let rest = null

function formatPercent(value) {
  return value == null || !Number.isFinite(value) ? '—' : `${Math.round(value)}%`
}

function formatReset(epochSeconds) {
  if (!Number.isFinite(epochSeconds)) return 'reset unavailable'
  const date = new Date(epochSeconds * 1000)
  const relative = Math.max(0, Math.floor((date.getTime() - Date.now()) / 60000))
  const local = date.toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })
  return relative < 1 ? `now (${local})` : `in ${relative}m (${local})`
}

function windowLabel(window) {
  if (window === 'five_hour') return '5-hour'
  if (window === 'weekly') return 'Weekly'
  return 'Custom'
}

function refresh() {
  if (!rest) return Promise.resolve()
  return rest('/quota/refresh', { method: 'POST' }).then(function (data) {
    queryClient.setQueryData(QUERY_KEY, data)
    return data
  })
}

function LimitRow({ limit, window }) {
  const remaining = Math.max(0, Math.min(100, window.remainingPercent))
  return jsxs('div', {
    className: 'flex flex-col gap-1',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between text-xs',
        children: [
          jsx('span', { className: 'text-(--ui-text-secondary)', children: windowLabel(window.window) }),
          jsx('span', { className: 'font-mono text-(--ui-text-primary)', children: `${formatPercent(remaining)} left` })
        ]
      }),
      jsx('div', {
        className: 'h-1.5 overflow-hidden rounded-full bg-(--ui-surface-tertiary)',
        children: jsx('div', {
          className: 'h-full rounded-full bg-(--ui-accent) transition-all',
          style: { width: `${remaining}%` }
        })
      }),
      jsx('div', {
        className: 'text-[0.65rem] text-(--ui-text-quaternary)',
        children: `Resets ${formatReset(window.resetsAt)}`
      })
    ]
  })
}

function LimitCard({ limit }) {
  return jsxs('div', {
    className: 'flex flex-col gap-2 rounded-lg border border-(--ui-stroke-secondary) p-3',
    children: [
      jsx('div', { className: 'text-xs font-semibold text-(--ui-text-primary)', children: limit.limitName || limit.limitId }),
      jsx('div', { className: 'flex flex-col gap-2', children: limit.windows.map(function (window) {
        return jsx(LimitRow, { key: `${limit.limitId}-${window.window}`, limit, window })
      }) })
    ]
  })
}

function ErrorState({ data }) {
  const error = data && (data.error || data.refreshError)
  return jsxs('div', {
    className: 'flex flex-col gap-2 p-3 text-sm',
    children: [
      jsx('div', { className: 'text-(--ui-text-primary)', children: 'Codex usage unavailable' }),
      jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: error ? error.message : 'No data returned by Codex.' }),
      jsx('div', { className: 'text-xs text-(--ui-text-quaternary)', children: 'Check that Codex CLI is installed and logged in on the Hermes gateway host.' }),
      jsx(Button, { size: 'sm', onClick: function () { void refresh() }, children: 'Retry' })
    ]
  })
}

function UsageContent() {
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: function () { return rest ? rest('/quota') : Promise.resolve({ success: false, limits: [], error: { message: 'Backend unavailable' } }) },
    refetchInterval: POLL_MS,
    retry: 1
  })
  if (query.isLoading && !query.data) return jsx('div', { className: 'p-3 text-sm text-(--ui-text-secondary)', children: 'Loading Codex usage…' })
  if (!query.data || !query.data.success) return jsx(ErrorState, { data: query.data })
  const limits = query.data.limits || []
  return jsxs('div', {
    className: 'flex flex-col gap-3 p-3',
    children: [
      jsxs('div', {
        className: 'flex items-center justify-between',
        children: [
          jsxs('div', { className: 'flex items-center gap-2', children: [jsx('span', { className: 'text-sm font-semibold', children: 'Codex Usage' }), query.data.planType ? jsx(Badge, { children: query.data.planType }) : null] }),
          jsx(Button, { size: 'sm', variant: 'ghost', disabled: query.isFetching, onClick: function () { void refresh() }, children: query.isFetching ? 'Refreshing…' : 'Refresh' })
        ]
      }),
      query.data.stale ? jsx('div', { className: 'text-xs text-amber-500', children: 'Showing the last successful snapshot; refresh failed.' }) : null,
      limits.length ? limits.map(function (limit) { return jsx(LimitCard, { key: limit.limitId, limit }) }) : jsx('div', { className: 'text-sm text-(--ui-text-secondary)', children: 'Codex returned no quota windows.' }),
      jsx('div', { className: 'text-[0.65rem] text-(--ui-text-quaternary)', children: query.data.fetchedAt ? `Checked ${new Date(query.data.fetchedAt).toLocaleString()}` : '' })
    ]
  })
}

function UsagePane() {
  return jsx(UsageContent, {})
}

function StatusChip() {
  const query = useQuery({
    queryKey: QUERY_KEY,
    queryFn: function () { return rest ? rest('/quota') : Promise.resolve({ success: false, limits: [] }) },
    refetchInterval: POLL_MS,
    retry: 1
  })
  const data = query.data
  if (!data || !data.success) return null
  const codex = (data.limits || []).find(function (item) { return item.limitId === 'codex' }) || (data.limits || [])[0]
  if (!codex || !codex.windows.length) return null
  const parts = codex.windows.map(function (window) { return `${window.window === 'five_hour' ? '5h' : window.window === 'weekly' ? 'W' : 'C'} ${formatPercent(window.remainingPercent)}` })
  return jsx(Popover, {
    children: [
      jsx(PopoverTrigger, {
        key: 'trigger',
        children: jsx('button', {
          type: 'button',
          className: cn('inline-flex h-full items-center px-1.5 text-[0.6875rem] text-(--ui-text-tertiary)', 'hover:bg-(--chrome-action-hover) hover:text-foreground'),
          children: `Codex · ${parts.join(' · ')}`
        })
      }),
      jsx(PopoverContent, {
        key: 'content',
        align: 'end',
        className: 'z-50 w-80 rounded-lg border border-(--ui-stroke-secondary) p-1 shadow-lg',
        children: jsx(UsageContent, {})
      })
    ]
  })
}

export default {
  id: ID,
  name: 'Codex Usage',
  register: function (ctx) {
    rest = ctx.rest
    ctx.registerMany([
      { id: 'usage-pane', area: 'panes', title: 'Codex Usage', data: { placement: 'right', width: '320px' }, render: function () { return jsx(UsagePane, {}) } },
      { id: 'usage-chip', area: 'statusBar.right', order: 110, render: function () { return jsx(StatusChip, {}) } },
      { id: 'usage-command', area: 'palette', data: { label: 'Refresh Codex usage', category: 'Codex', run: function () { return refresh() } } }
    ])
  }
}
