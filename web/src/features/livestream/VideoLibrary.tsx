import { AlertCircle, Film, Link2, Loader2, Trash2, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { formatBytes, formatClock, timeAgo } from '../../lib/format'
import type { Video } from '../../lib/types'

type Props = {
  selectedId: number | null
  onSelect: (id: number | null) => void
}

function sourceLabel(video: Video): string {
  if (video.source === 'upload') return 'Upload'
  try {
    return new URL(video.source_url).hostname.replace(/^www\./, '')
  } catch {
    return 'Link'
  }
}

/** Pick, upload, or import (YouTube and other sites) a video to play through the feed display. */
export function VideoLibrary({ selectedId, onSelect }: Props) {
  const [videos, setVideos] = useState<Video[] | null>(null)
  const [link, setLink] = useState('')
  const [importing, setImporting] = useState(false)
  const [upload, setUpload] = useState<{ name: string; progress: number } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    try {
      setVideos(await api.listVideos())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load videos')
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .listVideos()
      .then((rows) => !cancelled && setVideos(rows))
      .catch((err: Error) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [])

  const downloading = videos?.some((v) => v.status === 'downloading') ?? false
  useEffect(() => {
    if (!downloading) return
    const id = setInterval(refresh, 1000)
    return () => clearInterval(id)
  }, [downloading, refresh])

  async function importLink() {
    if (!link.trim()) return
    setImporting(true)
    setError(null)
    try {
      const video = await api.importVideo(link.trim())
      setLink('')
      onSelect(video.id)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setImporting(false)
    }
  }

  async function uploadFile(file: File) {
    setUpload({ name: file.name, progress: 0 })
    setError(null)
    try {
      const video = await api.uploadVideo(file, (progress) => setUpload({ name: file.name, progress }))
      onSelect(video.id)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUpload(null)
    }
  }

  async function remove(id: number) {
    setConfirmDelete(null)
    setError(null)
    try {
      await api.deleteVideo(id)
      if (id === selectedId) onSelect(null)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  return (
    <div className="space-y-3">
      <div>
        <label className="label" htmlFor="video-link">Import from a link</label>
        <div className="flex gap-2">
          <input
            id="video-link"
            className="input font-mono"
            placeholder="https://www.youtube.com/watch?v=…"
            value={link}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter') return
              e.preventDefault()
              void importLink()
            }}
          />
          <button type="button" className="btn-ghost" disabled={importing || !link.trim()} onClick={importLink}>
            {importing ? <Loader2 className="size-4 animate-spin" /> : <Link2 className="size-4" />}
            Import
          </button>
        </div>
        <p className="mt-1 text-xs text-zinc-500">YouTube and most video sites. Downloaded to the ground station.</p>
      </div>

      <div className="flex items-center justify-between gap-3">
        <span className="label mb-0">Library</span>
        <button
          type="button"
          className="btn-ghost px-2.5 py-1.5 text-xs"
          disabled={upload !== null}
          onClick={() => fileInput.current?.click()}
        >
          <Upload className="size-3.5" />
          Upload file
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="video/*,.mkv"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            e.target.value = ''
            if (file) void uploadFile(file)
          }}
        />
      </div>

      <ul className="max-h-64 divide-y divide-line overflow-y-auto rounded-xl border border-line">
        {upload && (
          <li className="px-3 py-2.5">
            <div className="flex items-center gap-2 text-sm text-zinc-300">
              <Loader2 className="size-4 shrink-0 animate-spin text-cyan-400" />
              <span className="truncate">Uploading {upload.name}</span>
              <span className="ml-auto text-xs text-zinc-500 tabular-nums">{Math.round(upload.progress * 100)}%</span>
            </div>
            <Progress value={upload.progress} />
          </li>
        )}
        {videos === null ? (
          <li className="grid place-items-center py-8 text-zinc-500">
            <Loader2 className="size-5 animate-spin" />
          </li>
        ) : videos.length === 0 && !upload ? (
          <li className="px-3 py-8 text-center text-sm text-zinc-500">No videos yet. Import a link or upload a file.</li>
        ) : (
          videos.map((v) => (
            <li key={v.id} className={`flex items-start gap-3 px-3 py-2.5 ${v.id === selectedId ? 'bg-cyan-400/[0.06]' : ''}`}>
              <button
                type="button"
                role="radio"
                aria-checked={v.id === selectedId}
                onClick={() => onSelect(v.id)}
                className="flex min-w-0 flex-1 items-start gap-3 text-left"
              >
                <span
                  className={`mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border ${
                    v.id === selectedId ? 'border-cyan-400' : 'border-zinc-600'
                  }`}
                >
                  {v.id === selectedId && <span className="size-2 rounded-full bg-cyan-400" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5 text-sm text-zinc-100">
                    {v.source === 'upload' ? (
                      <Film className="size-3.5 shrink-0 text-zinc-500" />
                    ) : (
                      <Link2 className="size-3.5 shrink-0 text-zinc-500" />
                    )}
                    <span className="truncate">{v.title}</span>
                  </span>
                  {v.status === 'downloading' ? (
                    <>
                      <span className="mt-0.5 block text-xs text-amber-300">
                        Downloading from {sourceLabel(v)}… {Math.round((v.progress ?? 0) * 100)}%
                      </span>
                      <Progress value={v.progress ?? 0} />
                    </>
                  ) : v.status === 'error' ? (
                    <span className="mt-0.5 block text-xs text-rose-300">{v.error}</span>
                  ) : (
                    <span className="mt-0.5 block text-xs text-zinc-500">
                      {[
                        sourceLabel(v),
                        v.duration_s ? formatClock(v.duration_s) : null,
                        formatBytes(v.size_bytes),
                        timeAgo(v.created_at),
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  )}
                </span>
              </button>
              {confirmDelete === v.id ? (
                <span className="flex shrink-0 gap-1">
                  <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => setConfirmDelete(null)}>
                    Keep
                  </button>
                  <button type="button" className="btn-danger px-2 py-1 text-xs" onClick={() => remove(v.id)}>
                    Delete
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  className="shrink-0 rounded-md p-1 text-zinc-500 hover:bg-white/5 hover:text-rose-300"
                  aria-label={`Delete ${v.title}`}
                  onClick={() => setConfirmDelete(v.id)}
                >
                  <Trash2 className="size-4" />
                </button>
              )}
            </li>
          ))
        )}
      </ul>

      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          {error}
        </div>
      )}
    </div>
  )
}

function Progress({ value }: { value: number }) {
  return (
    <span className="mt-1.5 block h-1 overflow-hidden rounded-full bg-white/[0.06]">
      <span className="block h-full rounded-full bg-cyan-400 transition-[width]" style={{ width: `${value * 100}%` }} />
    </span>
  )
}
