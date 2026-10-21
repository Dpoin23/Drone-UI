import { AlertCircle, ChevronRight, Inbox, Loader2, MapPin, Plus, Radar, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Select } from '../../components/Select'
import { timeAgo } from '../../lib/format'
import type { Category, IssueStatus, Severity } from '../../lib/types'
import { SeverityBadge, StatusBadge } from './Badges'
import { IssueDrawer } from './IssueDrawer'
import { IssueForm } from './IssueForm'
import { IssueThumb } from './ImageViews'
import { OPEN_STATUSES, STATUSES, categoryMeta, severityDot, severityOptions, statusLabel } from './meta'
import { useIssues } from './useIssues'

type StatusFilter = 'active' | 'all' | IssueStatus
type SortOrder = 'newest' | 'severity'

const severityRank: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 }

const severityFilterOptions = [{ value: 'all' as const, label: 'All severities' }, ...severityOptions]
const sortOptions: { value: SortOrder; label: string }[] = [
  { value: 'newest', label: 'Newest first' },
  { value: 'severity', label: 'Highest severity' },
]

export function IssuesPage({ category }: { category: Category }) {
  const meta = categoryMeta[category]
  const { issues, loading, error, create, update, remove, addImages, removeImage } = useIssues(category)
  const [creating, setCreating] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('active')
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all')
  const [sort, setSort] = useState<SortOrder>('newest')

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    const rows = issues.filter((i) => {
      if (statusFilter === 'active' && !OPEN_STATUSES.includes(i.status)) return false
      if (statusFilter !== 'active' && statusFilter !== 'all' && i.status !== statusFilter) return false
      if (severityFilter !== 'all' && i.severity !== severityFilter) return false
      if (q && !`${i.title} ${i.description} ${i.location}`.toLowerCase().includes(q)) return false
      return true
    })
    if (sort === 'severity') {
      rows.sort((a, b) => severityRank[a.severity] - severityRank[b.severity] || b.created_at.localeCompare(a.created_at))
    }
    return rows
  }, [issues, query, statusFilter, severityFilter, sort])

  const selected = issues.find((i) => i.id === selectedId) ?? null

  const filterTabs: { id: StatusFilter; label: string }[] = [
    { id: 'active', label: 'Active' },
    ...STATUSES.map((s) => ({ id: s, label: statusLabel(s, category) })),
    { id: 'all', label: 'All' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className={`grid size-12 place-items-center rounded-xl bg-gradient-to-b ring-1 ring-inset ${meta.accentBg}`}>
            <meta.icon className={`size-6 ${meta.accent}`} />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">{meta.title}</h1>
            <p className="text-sm text-zinc-400">{meta.blurb}</p>
          </div>
        </div>
        <button className="btn-primary" onClick={() => setCreating(true)}>
          <Plus className="size-4" />
          Log {meta.singular}
        </button>
      </div>

      <div className="flex items-center gap-2 rounded-lg border border-line bg-white/[0.02] px-3 py-2 text-xs text-zinc-400">
        <Radar className="size-4 shrink-0 text-cyan-400" />
        Entries will be created automatically from livestream and drone detections once the drone link is connected.
        You can still log entries manually.
      </div>

      <div className="panel">
        <div className="flex flex-col gap-3 border-b border-line p-3 lg:flex-row lg:items-center">
          <div className="flex gap-1 overflow-x-auto">
            {filterTabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setStatusFilter(t.id)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition ${
                  statusFilter === t.id ? 'bg-white/[0.08] text-zinc-50' : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex flex-1 flex-wrap gap-2 lg:justify-end">
            <div className="relative min-w-48 flex-1 lg:max-w-xs">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-zinc-500" />
              <input
                className="input pl-9"
                placeholder="Search title, notes, location"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <Select
              className="w-40"
              ariaLabel="Filter by severity"
              value={severityFilter}
              options={severityFilterOptions}
              onChange={setSeverityFilter}
            />
            <Select className="w-44" ariaLabel="Sort" value={sort} options={sortOptions} onChange={setSort} />
          </div>
        </div>

        {loading ? (
          <div className="grid place-items-center py-20 text-zinc-500">
            <Loader2 className="size-6 animate-spin" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center gap-2 py-20 text-sm text-rose-300">
            <AlertCircle className="size-4" />
            {error}
          </div>
        ) : visible.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
            <div className="grid size-12 place-items-center rounded-full bg-white/[0.04]">
              <Inbox className="size-5 text-zinc-500" />
            </div>
            <div>
              <p className="font-medium text-zinc-300">
                {issues.length === 0 ? `No ${meta.singular} entries yet` : 'Nothing matches these filters'}
              </p>
              <p className="text-sm text-zinc-500">
                {issues.length === 0
                  ? 'Entries are saved to your account.'
                  : 'Try a different status, severity, or search.'}
              </p>
            </div>
            {issues.length === 0 && (
              <button className="btn-ghost mt-1" onClick={() => setCreating(true)}>
                <Plus className="size-4" />
                Log the first one
              </button>
            )}
          </div>
        ) : (
          <ul className="divide-y divide-line overflow-hidden rounded-b-2xl">
            {visible.map((issue) => (
              <li key={issue.id}>
                <button
                  onClick={() => setSelectedId(issue.id)}
                  className="group flex w-full items-center gap-4 px-4 py-3 text-left transition hover:bg-white/[0.025]"
                >
                  <span className={`size-2 shrink-0 rounded-full ${severityDot[issue.severity]}`} />
                  {issue.images.length > 0 && <IssueThumb issueId={issue.id} images={issue.images} className="h-12 w-16" />}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium text-zinc-100">{issue.title}</span>
                      <span className="shrink-0 font-mono text-xs text-zinc-600">#{issue.id}</span>
                      {issue.source !== 'manual' && (
                        <span className="flex shrink-0 items-center gap-1 rounded-full bg-cyan-400/10 px-1.5 py-0.5 text-[10px] font-medium text-cyan-300 uppercase ring-1 ring-cyan-400/25 ring-inset">
                          <Radar className="size-3" />
                          Auto
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 flex items-center gap-3 text-xs text-zinc-500">
                      {issue.location && (
                        <span className="flex min-w-0 items-center gap-1 truncate">
                          <MapPin className="size-3 shrink-0" />
                          {issue.location}
                        </span>
                      )}
                      {issue.description && <span className="hidden truncate md:inline">{issue.description}</span>}
                    </div>
                  </div>
                  <div className="hidden shrink-0 sm:block">
                    <SeverityBadge severity={issue.severity} />
                  </div>
                  <div className="shrink-0">
                    <StatusBadge status={issue.status} category={category} />
                  </div>
                  <span className="hidden w-24 shrink-0 text-right text-xs text-zinc-500 md:block" title={issue.created_at}>
                    {timeAgo(issue.created_at)}
                  </span>
                  <ChevronRight className="size-4 shrink-0 text-zinc-600 transition group-hover:translate-x-0.5 group-hover:text-zinc-400" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <IssueForm
        open={creating}
        category={category}
        onClose={() => setCreating(false)}
        onCreate={create}
        onAddImages={addImages}
      />
      {selected && (
        <IssueDrawer
          key={selected.id}
          issue={selected}
          onClose={() => setSelectedId(null)}
          onUpdate={update}
          onDelete={remove}
          onAddImages={addImages}
          onRemoveImage={removeImage}
        />
      )}
    </div>
  )
}
