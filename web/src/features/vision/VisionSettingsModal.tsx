import { Loader2, ScanEye } from 'lucide-react'
import { useState } from 'react'
import { Modal } from '../../components/Modal'
import type { FrameSource, VisionCapabilities, VisionSettings, VisionStream } from '../../lib/types'

const sources: { id: FrameSource; label: string; hint: string }[] = [
  {
    id: 'auto',
    label: 'Automatic',
    hint: 'The ground station captures live drone streams itself; the browser sends demo and test-video frames.',
  },
  {
    id: 'server',
    label: 'Ground station capture',
    hint: 'Decode the stream on the ground station with OpenCV (RTSP from MediaMTX, MJPEG, or the test video file). Keeps running with the tab closed.',
  },
  {
    id: 'browser',
    label: 'Frames from this browser',
    hint: 'Send the frames this page is showing. Detections follow pause, seek, and frame stepping.',
  },
]

type Props = {
  onClose: () => void
  settings: VisionSettings
  capabilities: VisionCapabilities
  onSave: (next: VisionSettings) => Promise<void>
}

/** Mount only while open, so each opening starts from the saved settings. */
export function VisionSettingsModal({ onClose, settings, capabilities, onSave }: Props) {
  const [draft, setDraft] = useState(settings)
  const [saving, setSaving] = useState(false)

  function setRate(mode: keyof VisionSettings['rates'], stream: VisionStream, value: string) {
    const n = Math.min(Math.max(Number(value) || 0, 0), capabilities.max_rate)
    setDraft((d) => ({ ...d, rates: { ...d.rates, [mode]: { ...d.rates[mode], [stream]: n } } }))
  }

  async function submit() {
    setSaving(true)
    try {
      await onSave(draft)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <ScanEye className="size-4 text-cyan-400" />
          Processing settings
        </span>
      }
    >
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <fieldset>
          <legend className="label">Frames</legend>
          <div className="space-y-2">
            {sources.map((s) => (
              <label
                key={s.id}
                className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition ${
                  draft.frame_source === s.id ? 'border-cyan-400/50 bg-cyan-400/[0.06]' : 'border-line hover:bg-white/[0.03]'
                }`}
              >
                <input
                  type="radio"
                  name="frame-source"
                  className="mt-1 accent-cyan-400"
                  checked={draft.frame_source === s.id}
                  onChange={() => setDraft((d) => ({ ...d, frame_source: s.id }))}
                />
                <span>
                  <span className="block text-sm font-medium text-zinc-100">{s.label}</span>
                  <span className="mt-0.5 block text-xs text-zinc-500">{s.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {draft.frame_source !== 'browser' && (
          <div>
            <label className="label" htmlFor="capture-url">Capture URL (optional)</label>
            <input
              id="capture-url"
              className="input font-mono"
              placeholder="rtsp://drone.local:8554/cam"
              value={draft.capture_url}
              onChange={(e) => setDraft((d) => ({ ...d, capture_url: e.target.value }))}
            />
            <p className="mt-1 text-xs text-zinc-500">
              Leave empty to use the feed's URL. A WebRTC (WHEP) feed is read over MediaMTX's RTSP port 8554.
              {capabilities.capture.gstreamer ? ' RTSP is decoded with GStreamer.' : ''}
            </p>
          </div>
        )}

        <div>
          <span className="label">Inference rate per flight mode (FPS, 0 = off)</span>
          <div className="overflow-hidden rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead className="bg-white/[0.03] text-xs text-zinc-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Mode</th>
                  <th className="px-2 py-2 text-left font-medium">Intruder</th>
                  <th className="px-2 py-2 text-left font-medium">Maintenance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {capabilities.modes.map((m) => (
                  <tr key={m.id}>
                    <td className="px-3 py-1.5 text-zinc-300">{m.label}</td>
                    {(['intruder', 'maintenance'] as const).map((stream) => (
                      <td key={stream} className="px-2 py-1.5">
                        <input
                          type="number"
                          aria-label={`${m.label} ${stream} FPS`}
                          className="input w-20 px-2 py-1 font-mono tabular-nums"
                          min={0}
                          max={capabilities.max_rate}
                          step={0.5}
                          value={draft.rates[m.id][stream]}
                          onChange={(e) => setRate(m.id, stream, e.target.value)}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            className="mt-1.5 text-xs text-cyan-300 hover:text-cyan-200"
            onClick={() => setDraft((d) => ({ ...d, rates: capabilities.default_rates }))}
          >
            Reset to defaults
          </button>
        </div>

        <div className="space-y-2">
          <Toggle
            checked={draft.auto_issues}
            onChange={(v) => setDraft((d) => ({ ...d, auto_issues: v }))}
            label="Log confirmed detections as issues"
            hint="Creates a security risk or maintenance issue with an annotated snapshot, GPS position, and time."
          />
          <Toggle
            checked={draft.follow_telemetry}
            onChange={(v) => setDraft((d) => ({ ...d, follow_telemetry: v }))}
            label="Follow the drone's flight mode"
            hint="Switch modes automatically when telemetry reports takeoff, transit, patrol, inspection, or return to base."
          />
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            Save
          </button>
        </div>
      </form>
    </Modal>
  )
}

function Toggle({
  checked,
  onChange,
  label,
  hint,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
  hint: string
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <input
        type="checkbox"
        className="mt-1 accent-cyan-400"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-sm text-zinc-200">{label}</span>
        <span className="block text-xs text-zinc-500">{hint}</span>
      </span>
    </label>
  )
}
