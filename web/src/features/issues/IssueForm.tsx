import { AlertCircle, Loader2, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Modal } from '../../components/Modal'
import { Select } from '../../components/Select'
import type { Category, Issue, IssueDraft } from '../../lib/types'
import { ImageDropzone } from './ImageViews'
import { validateImageFiles } from './images'
import { categoryMeta, severityOptions } from './meta'

type Props = {
  open: boolean
  category: Category
  initialFiles?: File[]
  onClose: () => void
  onCreate: (draft: IssueDraft) => Promise<Issue>
  onAddImages: (issueId: number, files: File[]) => Promise<Issue>
}

const previews = new WeakMap<File, string>()

function previewUrl(file: File): string {
  let url = previews.get(file)
  if (!url) {
    url = URL.createObjectURL(file)
    previews.set(file, url)
  }
  return url
}

function releasePreview(file: File) {
  const url = previews.get(file)
  if (url) URL.revokeObjectURL(url)
  previews.delete(file)
}

const empty = (category: Category): IssueDraft => ({
  category,
  title: '',
  description: '',
  severity: category === 'security' ? 'high' : 'medium',
  location: '',
})

export function IssueForm({ open, category, initialFiles = [], onClose, onCreate, onAddImages }: Props) {
  const [draft, setDraft] = useState<IssueDraft>(() => empty(category))
  const [files, setFiles] = useState<File[]>(initialFiles)
  const [createdId, setCreatedId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const meta = categoryMeta[category]

  const set = <K extends keyof IssueDraft>(key: K, value: IssueDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))

  function addFiles(picked: File[]) {
    const { ok, error: problem } = validateImageFiles(picked)
    setFiles((prev) => [...prev, ...ok])
    setError(problem)
  }

  function removeFile(file: File) {
    releasePreview(file)
    setFiles((prev) => prev.filter((f) => f !== file))
  }

  function close() {
    files.forEach(releasePreview)
    setDraft(empty(category))
    setFiles([])
    setCreatedId(null)
    setError(null)
    onClose()
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const id = createdId ?? (await onCreate({ ...draft, category })).id
      setCreatedId(id)
      if (files.length) {
        try {
          await onAddImages(id, files)
        } catch (err) {
          const reason = err instanceof Error ? err.message : 'upload failed'
          throw new Error(`Entry saved, but the images didn't upload (${reason}). Submit again to retry the upload.`)
        }
      }
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
        <fieldset disabled={createdId !== null} className="space-y-4 disabled:opacity-60">
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
              <Select
                id="issue-severity"
                value={draft.severity}
                options={severityOptions}
                onChange={(v) => set('severity', v)}
              />
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
              className="input min-h-24 resize-y"
              maxLength={5000}
              placeholder="What did you see? Any follow-up needed?"
              value={draft.description}
              onChange={(e) => set('description', e.target.value)}
            />
          </div>
        </fieldset>

        <div>
          <div className="label">Images</div>
          {files.length > 0 ? (
            <div className="grid grid-cols-4 gap-2">
              {files.map((file) => (
                <div key={previewUrl(file)} className="group relative aspect-square overflow-hidden rounded-lg ring-1 ring-line">
                  <img src={previewUrl(file)} alt={file.name} className="h-full w-full object-cover" />
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => removeFile(file)}
                    className="absolute top-1 right-1 rounded-full bg-black/70 p-1 text-zinc-200 opacity-0 transition group-hover:opacity-100 hover:text-white focus:opacity-100"
                    aria-label={`Remove ${file.name}`}
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              ))}
              <ImageDropzone compact onFiles={addFiles} />
            </div>
          ) : (
            <ImageDropzone onFiles={addFiles} />
          )}
        </div>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            {error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-ghost" onClick={close}>
            {createdId !== null ? 'Close' : 'Cancel'}
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            {createdId !== null ? 'Retry upload' : `Log ${meta.singular}`}
          </button>
        </div>
      </form>
    </Modal>
  )
}
