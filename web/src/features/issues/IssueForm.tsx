import { AlertCircle, Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Modal } from '../../components/Modal'
import type { Category, IssueDraft } from '../../lib/types'
import { SEVERITIES, categoryMeta } from './meta'

type Props = {
  open: boolean
  category: Category
  onClose: () => void
  onCreate: (draft: IssueDraft) => Promise<unknown>
}

const empty = (category: Category): IssueDraft => ({
  category,
  title: '',
  description: '',
  severity: category === 'security' ? 'high' : 'medium',
  location: '',
})

export function IssueForm({ open, category, onClose, onCreate }: Props) {
  const [draft, setDraft] = useState<IssueDraft>(() => empty(category))
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const meta = categoryMeta[category]

  const set = <K extends keyof IssueDraft>(key: K, value: IssueDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))

  function close() {
    setDraft(empty(category))
    setError(null)
    onClose()
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await onCreate({ ...draft, category })
      close()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title={
        <span className="flex items-center gap-2">
          <meta.icon className={`size-4 ${meta.accent}`} />
          New {meta.singular}
        </span>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="label" htmlFor="issue-title">Title</label>
          <input
            id="issue-title"
            className="input"
            required
            maxLength={200}
            autoFocus
            placeholder={meta.examples}
            value={draft.title}
            onChange={(e) => set('title', e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="issue-severity">Severity</label>
            <select
              id="issue-severity"
              className="input capitalize"
              value={draft.severity}
              onChange={(e) => set('severity', e.target.value as IssueDraft['severity'])}
            >
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="issue-location">Location</label>
            <input
              id="issue-location"
              className="input"
              maxLength={200}
              placeholder="e.g. North fence, post 14"
              value={draft.location}
              onChange={(e) => set('location', e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="label" htmlFor="issue-description">Notes</label>
          <textarea
            id="issue-description"
            className="input min-h-28 resize-y"
            maxLength={5000}
            placeholder="What did you see? Any follow-up needed?"
            value={draft.description}
            onChange={(e) => set('description', e.target.value)}
          />
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-ghost" onClick={close}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            Log {meta.singular}
          </button>
        </div>
      </form>
    </Modal>
  )
}
