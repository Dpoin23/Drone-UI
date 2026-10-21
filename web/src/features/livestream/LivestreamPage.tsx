import {
  Activity,
  AlertCircle,
  ChevronRight,
  Loader2,
  Maximize2,
  Radio,
  Settings2,
  ShieldAlert,
  Wrench,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { timeAgo } from '../../lib/format'
import type { Category, StreamSettings, StreamTransport } from '../../lib/types'
import { Modal } from '../../components/Modal'
import { IssueForm } from '../issues/IssueForm'
import { IssueThumb } from '../issues/ImageViews'
import { OPEN_STATUSES, severityDot } from '../issues/meta'
import { useIssues } from '../issues/useIssues'
import { captureFrame } from './snapshot'
import { VideoPlayer, type StreamStatus } from './VideoPlayer'

const transports: { id: StreamTransport; label: string; placeholder: string; hint: string }[] = [
  { id: 'demo', label: 'Demo feed', placeholder: '', hint: 'Simulated perimeter footage for testing without the drone.' },
  {
    id: 'webrtc',
    label: 'WebRTC (WHEP)',
    placeholder: 'http://drone.local:8889/cam/whep',
    hint: 'Low-latency stream from MediaMTX on the Pi.',
  },
  {
    id: 'mjpeg',
    label: 'MJPEG',
    placeholder: 'http://drone.local:8080/stream.mjpg',
    hint: 'Simple fallback stream over HTTP. Higher bandwidth.',
  },
]

const statusUi: Record<StreamStatus, { label: string; dot: string; text: string }> = {
  idle: { label: 'Not configured', dot: 'bg-zinc-500', text: 'text-zinc-400' },
  connecting: { label: 'Connecting', dot: 'bg-amber-400 animate-pulse', text: 'text-amber-300' },
  live: { label: 'Live', dot: 'bg-emerald-400 shadow-[0_0_10px_2px_rgb(52_211_153/0.5)]', text: 'text-emerald-300' },
  error: { label: 'Error', dot: 'bg-rose-400', text: 'text-rose-300' },
}

export function LivestreamPage() {
  const [saved, setSaved] = useState<StreamSettings | null>(null)
  const [draft, setDraft] = useState<StreamSettings>({ transport: 'demo', url: '' })
  const [showSettings, setShowSettings] = useState(false)
  const [saving, setSaving] = useState(false)
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const [status, setStatus] = useState<{ status: StreamStatus; message?: string }>({ status: 'idle' })
  const [quickLog, setQuickLog] = useState<{ category: Category; files: File[] } | null>(null)
  const [now, setNow] = useState(() => new Date())
  const stageRef = useRef<HTMLDivElement>(null)
  const { issues, loading: issuesLoading, create, addImages } = useIssues()

  useEffect(() => {
    api
      .getStreamSettings()
      .then((s) => {
        setSaved(s)
        setDraft(s)
      })
      .catch(() => setSaved({ transport: 'demo', url: '' }))
  }, [])

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  const onStatus = useCallback((s: StreamStatus, message?: string) => setStatus({ status: s, message }), [])

  function openSettings() {
    if (saved) setDraft(saved)
    setSettingsError(null)
    setShowSettings(true)
  }

  async function startQuickLog(category: Category) {
    const snapshot = await captureFrame(stageRef.current)
    setQuickLog({ category, files: snapshot ? [snapshot] : [] })
  }

  async function saveSettings() {
    setSaving(true)
    setSettingsError(null)
    try {
      const next = await api.putStreamSettings(draft)
      setSaved(next)
      setShowSettings(false)
    } catch (err) {
      setSettingsError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const active = issues.filter((i) => OPEN_STATUSES.includes(i.status))
  const activeSecurity = active.filter((i) => i.category === 'security')
  const activeMaintenance = active.filter((i) => i.category === 'maintenance')
  const transportMeta = transports.find((t) => t.id === (saved?.transport ?? 'demo'))!
  const draftMeta = transports.find((t) => t.id === draft.transport)!
  const ui = statusUi[status.status]

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <StatusTile icon={Radio} label="Stream">
            <span className={`flex items-center gap-2 ${ui.text}`}>
              <span className={`size-2 rounded-full ${ui.dot}`} />
              {ui.label}
            </span>
          </StatusTile>
          <StatusTile icon={Activity} label="Transport">{transportMeta.label}</StatusTile>
          <StatusTile icon={ShieldAlert} label="Active security">
            <span className={activeSecurity.length ? 'text-rose-300' : ''}>{activeSecurity.length}</span>
          </StatusTile>
          <StatusTile icon={Wrench} label="Active maintenance">
            <span className={activeMaintenance.length ? 'text-amber-300' : ''}>{activeMaintenance.length}</span>
          </StatusTile>
        </div>

        <div className="panel overflow-hidden">
          <div ref={stageRef} className="group relative aspect-video bg-black">
            {saved ? (
              <VideoPlayer settings={saved} onStatus={onStatus} />
            ) : (
              <div className="grid h-full place-items-center text-zinc-500">
                <Loader2 className="size-6 animate-spin" />
              </div>
            )}

            <div className="pointer-events-none absolute inset-0">
              <Corner className="top-4 left-4 border-t-2 border-l-2" />
              <Corner className="top-4 right-4 border-t-2 border-r-2" />
              <Corner className="bottom-4 left-4 border-b-2 border-l-2" />
              <Corner className="right-4 bottom-4 border-r-2 border-b-2" />
              <div className="absolute top-1/2 left-1/2 size-8 -translate-1/2">
                <div className="absolute top-1/2 left-0 h-px w-full bg-white/30" />
                <div className="absolute top-0 left-1/2 h-full w-px bg-white/30" />
              </div>

              <div className="absolute top-6 left-8 flex items-center gap-2 rounded-md bg-black/50 px-2 py-1 font-mono text-xs backdrop-blur">
                <span className={`size-2 rounded-full ${ui.dot}`} />
                <span className="text-zinc-200">{saved?.transport === 'demo' ? 'DEMO' : ui.label.toUpperCase()}</span>
              </div>
              <div className="absolute top-6 right-8 rounded-md bg-black/50 px-2 py-1 font-mono text-xs text-zinc-200 backdrop-blur">
                {now.toISOString().slice(0, 19).replace('T', ' ')}Z
              </div>

              {status.status !== 'live' && status.message && (
                <div className="absolute inset-x-0 bottom-8 flex justify-center">
                  <div className="flex items-center gap-2 rounded-lg bg-black/70 px-3 py-2 text-sm text-zinc-200 backdrop-blur">
                    <AlertCircle className="size-4 text-amber-400" />
                    {status.message}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-3 py-2.5">
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span className="font-mono">{saved?.url || transportMeta.hint}</span>
            </div>
            <div className="flex gap-2">
              <button className="btn-ghost px-2.5" onClick={openSettings}>
                <Settings2 className="size-4" />
                Stream settings
              </button>
              <button
                className="btn-ghost px-2.5"
                onClick={() => stageRef.current?.requestFullscreen?.()}
                title="Fullscreen"
              >
                <Maximize2 className="size-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <Modal
        open={showSettings}
        onClose={() => setShowSettings(false)}
        title={
          <span className="flex items-center gap-2">
            <Settings2 className="size-4 text-cyan-400" />
            Stream settings
          </span>
        }
      >
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void saveSettings()
          }}
        >
          <div className="space-y-2">
            {transports.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setDraft((d) => ({ ...d, transport: t.id }))}
                className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition ${
                  draft.transport === t.id ? 'border-cyan-400/50 bg-cyan-400/[0.06]' : 'border-line hover:bg-white/[0.03]'
                }`}
              >
                <span
                  className={`mt-0.5 grid size-4 shrink-0 place-items-center rounded-full border ${
                    draft.transport === t.id ? 'border-cyan-400' : 'border-zinc-600'
                  }`}
                >
                  {draft.transport === t.id && <span className="size-2 rounded-full bg-cyan-400" />}
                </span>
                <span>
                  <span className="block text-sm font-medium text-zinc-100">{t.label}</span>
                  <span className="mt-0.5 block text-xs text-zinc-500">{t.hint}</span>
                </span>
              </button>
            ))}
          </div>
          {draft.transport !== 'demo' && (
            <div>
              <label className="label" htmlFor="stream-url">Stream URL</label>
              <input
                id="stream-url"
                className="input font-mono"
                required
                autoFocus
                placeholder={draftMeta.placeholder}
                value={draft.url}
                onChange={(e) => setDraft((d) => ({ ...d, url: e.target.value }))}
              />
            </div>
          )}
          {settingsError && <p className="text-sm text-rose-300">{settingsError}</p>}
          <div className="flex items-center justify-between gap-3 pt-2">
            <p className="text-xs text-zinc-500">Saved to your account.</p>
            <div className="flex gap-2">
              <button type="button" className="btn-ghost" onClick={() => setShowSettings(false)}>
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={saving}>
                {saving && <Loader2 className="size-4 animate-spin" />}
                Save & connect
              </button>
            </div>
          </div>
        </form>
      </Modal>

      <aside className="space-y-4">
        <div className="panel p-4">
          <h2 className="text-sm font-semibold text-zinc-100">Log from feed</h2>
          <p className="mt-0.5 mb-3 text-xs text-zinc-500">Attaches a snapshot of the current frame.</p>
          <div className="grid grid-cols-2 gap-2">
            <button
              className="flex flex-col items-start gap-2 rounded-xl border border-rose-500/25 bg-rose-500/[0.07] p-3 text-left transition hover:bg-rose-500/[0.12]"
              onClick={() => startQuickLog('security')}
            >
              <ShieldAlert className="size-5 text-rose-400" />
              <span className="text-sm font-medium text-rose-100">Security risk</span>
            </button>
            <button
              className="flex flex-col items-start gap-2 rounded-xl border border-amber-500/25 bg-amber-500/[0.07] p-3 text-left transition hover:bg-amber-500/[0.12]"
              onClick={() => startQuickLog('maintenance')}
            >
              <Wrench className="size-5 text-amber-400" />
              <span className="text-sm font-medium text-amber-100">Maintenance</span>
            </button>
          </div>
        </div>

        <div className="panel">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="text-sm font-semibold text-zinc-100">Active issues</h2>
            <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-xs text-zinc-400 tabular-nums">{active.length}</span>
          </div>
          {issuesLoading ? (
            <div className="grid place-items-center py-10 text-zinc-500">
              <Loader2 className="size-5 animate-spin" />
            </div>
          ) : active.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-zinc-500">All clear. Nothing active.</p>
          ) : (
            <ul className="max-h-[480px] divide-y divide-line overflow-y-auto">
              {active.slice(0, 12).map((issue) => (
                <li key={issue.id}>
                  <Link
                    to={`/${issue.category}`}
                    className="group flex items-center gap-3 px-4 py-3 transition hover:bg-white/[0.025]"
                  >
                    {issue.category === 'security' ? (
                      <ShieldAlert className="size-4 shrink-0 text-rose-400" />
                    ) : (
                      <Wrench className="size-4 shrink-0 text-amber-400" />
                    )}
                    <IssueThumb issueId={issue.id} images={issue.images} className="h-9 w-12" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm text-zinc-200">{issue.title}</div>
                      <div className="flex items-center gap-2 text-xs text-zinc-500">
                        <span className={`size-1.5 rounded-full ${severityDot[issue.severity]}`} />
                        <span className="capitalize">{issue.severity}</span>
                        <span>·</span>
                        <span>{timeAgo(issue.created_at)}</span>
                      </div>
                    </div>
                    <ChevronRight className="size-4 shrink-0 text-zinc-600 group-hover:text-zinc-400" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {quickLog && (
        <IssueForm
          open
          category={quickLog.category}
          initialFiles={quickLog.files}
          onClose={() => setQuickLog(null)}
          onCreate={create}
          onAddImages={addImages}
        />
      )}
    </div>
  )
}

function StatusTile({ icon: Icon, label, children }: { icon: typeof Radio; label: string; children: ReactNode }) {
  return (
    <div className="panel flex items-center gap-3 px-4 py-3">
      <Icon className="size-4 shrink-0 text-zinc-500" />
      <div className="min-w-0">
        <div className="text-[11px] font-medium tracking-wide text-zinc-500 uppercase">{label}</div>
        <div className="truncate text-sm font-medium text-zinc-100 tabular-nums">{children}</div>
      </div>
    </div>
  )
}

function Corner({ className }: { className: string }) {
  return <div className={`absolute size-6 border-white/40 ${className}`} />
}
