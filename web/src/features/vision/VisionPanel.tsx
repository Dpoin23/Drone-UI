import { AlertCircle, Loader2, Play, ScanEye, Settings2, Square } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Select } from '../../components/Select'
import type { FlightMode, VisionStream, WorkerStatus } from '../../lib/types'
import type { Vision } from './useVision'
import { VisionSettingsModal } from './VisionSettingsModal'

const STREAM_LABELS: Record<VisionStream, string> = {
  intruder: 'Intruder detection',
  maintenance: 'Maintenance detection',
}

const stateDot: Record<WorkerStatus['state'], string> = {
  loading: 'bg-amber-400 animate-pulse',
  waiting: 'bg-amber-400',
  running: 'bg-emerald-400',
  off: 'bg-zinc-600',
  error: 'bg-rose-400',
  unavailable: 'bg-zinc-600',
}

const sourceStateText: Record<string, string> = {
  live: 'text-emerald-300',
  connecting: 'text-amber-300',
  waiting: 'text-amber-300',
  error: 'text-rose-300',
}

function fps(n: number) {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

export function VisionPanel({ vision, frameError }: { vision: Vision; frameError: string | null }) {
  const { capabilities, settings, session, stats, busy, error, start, stop, saveSettings } = vision
  const [showSettings, setShowSettings] = useState(false)
  const installed = capabilities?.installed ?? true
  const mode = session.running ? session.mode : settings?.mode
  const workers = stats?.workers ?? (session.running ? session.workers : null)
  const modeOptions = (capabilities?.modes ?? []).map((m) => ({ value: m.id, label: m.label }))

  return (
    <div className="panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <ScanEye className="size-4 text-cyan-400" />
            Image processing
          </h2>
          <p className="mt-0.5 truncate text-xs text-zinc-500">
            {session.running ? session.source.label : 'YOLO detection and tracking on the feed.'}
          </p>
        </div>
        <button
          className={`${session.running ? 'btn-ghost' : 'btn-primary'} shrink-0 px-3 py-1.5`}
          onClick={session.running ? stop : start}
          disabled={busy || !installed}
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" />
          ) : session.running ? (
            <Square className="size-3.5" />
          ) : (
            <Play className="size-3.5" />
          )}
          {session.running ? 'Stop' : 'Start'}
        </button>
      </div>

      {!installed && (
        <Notice>
          Image processing isn't installed on the ground station. Install <span className="font-mono">requirements-vision.txt</span>.
        </Notice>
      )}

      <div className="mt-3">
        <label className="label" htmlFor="flight-mode">Flight mode</label>
        {mode && settings ? (
          <Select<FlightMode>
            id="flight-mode"
            value={mode}
            options={modeOptions}
            onChange={(m) => void saveSettings({ ...settings, mode: m })}
          />
        ) : (
          <div className="input text-zinc-500">Loading…</div>
        )}
      </div>

      <ul className="mt-3 space-y-2">
        {(['intruder', 'maintenance'] as const).map((stream) => {
          const w = workers?.[stream]
          const target = w?.target_fps ?? (mode && settings ? settings.rates[mode][stream] : 0)
          const cap = capabilities?.streams[stream]
          const state: WorkerStatus['state'] = w?.state ?? (cap && !cap.available ? 'unavailable' : 'off')
          const detail =
            w?.message ??
            (state === 'unavailable' ? cap?.reason : null) ??
            [w?.detector ?? cap?.model, w?.device, w?.infer_ms != null ? `${Math.round(w.infer_ms)} ms` : null]
              .filter(Boolean)
              .join(' · ')
          return (
            <li key={stream} className="rounded-xl border border-line bg-white/[0.02] px-3 py-2">
              <div className="flex items-center gap-2 text-sm">
                <span className={`size-1.5 shrink-0 rounded-full ${target > 0 ? stateDot[state] : 'bg-zinc-600'}`} />
                <span className="flex-1 text-zinc-200">{STREAM_LABELS[stream]}</span>
                <span className="font-mono text-xs text-zinc-400 tabular-nums">
                  {target <= 0
                    ? 'off'
                    : session.running && w
                      ? `${w.actual_fps.toFixed(1)} / ${fps(target)} fps`
                      : `${fps(target)} fps`}
                </span>
              </div>
              {detail && <p className="mt-0.5 truncate pl-3.5 text-xs text-zinc-500" title={detail}>{detail}</p>}
            </li>
          )
        })}
      </ul>

      {session.running && (
        <div className="mt-3 space-y-1 text-xs text-zinc-500">
          <div className="flex justify-between gap-2">
            <span>Frames</span>
            <span className={`truncate ${sourceStateText[session.source.state] ?? 'text-zinc-400'}`}>
              {session.source.state === 'live'
                ? `${session.frame_source === 'browser' ? 'From this browser' : 'Ground station capture'}${
                    stats ? ` · ${stats.capture_fps.toFixed(1)} fps` : ''
                  }`
                : (session.source.message ?? session.source.state)}
            </span>
          </div>
          {stats && (
            <>
              <div className="flex justify-between gap-2">
                <span>Skipped (latest-frame)</span>
                <span className="text-zinc-400 tabular-nums">{stats.frames_overwritten.toLocaleString()}</span>
              </div>
              <div className="flex justify-between gap-2">
                <span>Alerts · issues logged</span>
                <span className="text-zinc-400 tabular-nums">
                  {stats.alerts} · {stats.issues_created}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span>GPS</span>
                <span className="truncate text-zinc-400 tabular-nums">
                  {stats.telemetry?.lat != null && stats.telemetry.lon != null
                    ? `${stats.telemetry.lat.toFixed(5)}, ${stats.telemetry.lon.toFixed(5)}`
                    : 'No fix'}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {(frameError || error) && <Notice>{frameError ?? error}</Notice>}

      <button className="btn-ghost mt-3 w-full" onClick={() => setShowSettings(true)} disabled={!settings}>
        <Settings2 className="size-4" />
        Processing settings
      </button>

      {showSettings && settings && capabilities && (
        <VisionSettingsModal
          onClose={() => setShowSettings(false)}
          settings={settings}
          capabilities={capabilities}
          onSave={async (next) => {
            if (await saveSettings(next)) setShowSettings(false)
          }}
        />
      )}
    </div>
  )
}

function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="mt-3 flex gap-2 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-200">
      <AlertCircle className="mt-px size-3.5 shrink-0" />
      <span>{children}</span>
    </p>
  )
}
