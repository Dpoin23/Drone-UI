import { AlertCircle, Loader2, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Modal } from '../../components/Modal'
import { formatDateTime } from '../../lib/format'
import type { Issue, IssuePatch, IssueStatus } from '../../lib/types'
import { SeverityBadge, StatusBadge } from './Badges'
import { SEVERITIES, STATUSES, statusLabel, statusStyle } from './meta'

type Props = {
  issue: Issue
  onClose: () => void
  onUpdate: (id: number, patch: IssuePatch) => Promise<unknown>
  onDelete: (id: number) => Promise<unknown>
}

export function IssueDrawer({ issue, onClose, onUpdate, onDelete }: Props) {
  const [form, setForm] = useState<IssuePatch>(() => ({
    title: issue.title,
    description: issue.description,
    severity: issue.severity,
    location: issue.location,
  }))
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty =
    form.title !== issue.title ||
    form.description !== issue.description ||
    form.severity !== issue.severity ||
    form.location !== issue.location

  async function run(action: () => Promise<unknown>) {
    setSaving(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setSaving(false)
    }
  }

  const setStatus = (status: IssueStatus) => run(() => onUpdate(issue.id, { status }))
  const save = () => run(() => onUpdate(issue.id, form))
  const remove = () => run(async () => {
    await onDelete(issue.id)
    onClose()
  })

  return (
    <Modal open side="right" onClose={onClose} title={`#${issue.id} · ${issue.title}`}>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={issue.severity} />
          <StatusBadge status={issue.status} category={issue.category} />
          <span className="text-xs text-zinc-500">Source: {issue.source}</span>
        </div>

        <section>
          <div className="label">Status</div>
          <div className="grid grid-cols-2 gap-2">
            {STATUSES.map((s) => (
              <button
                key={s}
                disabled={saving}
                onClick={() => setStatus(s)}
                className={`rounded-lg px-3 py-2 text-sm font-medium ring-1 ring-inset transition ${
                  issue.status === s ? statusStyle[s] : 'text-zinc-400 ring-line hover:bg-white/[0.04] hover:text-zinc-200'
                }`}
              >
                {statusLabel(s, issue.category)}
              </button>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <div>
            <label className="label" htmlFor="edit-title">Title</label>
            <input
              id="edit-title"
              className="input"
              maxLength={200}
              value={form.title ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="edit-severity">Severity</label>
              <select
                id="edit-severity"
                className="input capitalize"
                value={form.severity}
                onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value as Issue['severity'] }))}
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="edit-location">Location</label>
              <input
                id="edit-location"
                className="input"
                maxLength={200}
                value={form.location ?? ''}
                onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
              />
            </div>
          </div>
          <div>
            <label className="label" htmlFor="edit-description">Notes</label>
            <textarea
              id="edit-description"
              className="input min-h-36 resize-y"
              maxLength={5000}
              value={form.description ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex justify-end">
            <button className="btn-primary" disabled={!dirty || saving || !form.title?.trim()} onClick={save}>
              {saving && <Loader2 className="size-4 animate-spin" />}
              Save changes
            </button>
          </div>
        </section>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {error}
          </div>
        )}

        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 rounded-xl border border-line bg-black/20 p-4 text-sm">
          <dt className="text-zinc-500">Logged</dt>
          <dd className="text-zinc-300">{formatDateTime(issue.created_at)}</dd>
          <dt className="text-zinc-500">Updated</dt>
          <dd className="text-zinc-300">{formatDateTime(issue.updated_at)}</dd>
          {issue.resolved_at && (
            <>
              <dt className="text-zinc-500">Closed</dt>
              <dd className="text-zinc-300">{formatDateTime(issue.resolved_at)}</dd>
            </>
          )}
        </dl>

        <div className="border-t border-line pt-4">
          {confirmDelete ? (
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-zinc-400">Delete this entry permanently?</span>
              <div className="flex gap-2">
                <button className="btn-ghost" onClick={() => setConfirmDelete(false)}>Cancel</button>
                <button className="btn-danger" disabled={saving} onClick={remove}>Delete</button>
              </div>
            </div>
          ) : (
            <button className="btn-danger" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="size-4" />
              Delete entry
            </button>
          )}
        </div>
      </div>
    </Modal>
  )
}
