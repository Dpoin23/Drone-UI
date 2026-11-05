import { useCallback, useEffect, useRef, useState } from 'react'
import { api, tokenStore } from '../../lib/api'
import type {
  DetectionEvent,
  VisionAlert,
  VisionCapabilities,
  VisionSession,
  VisionSettings,
  VisionStats,
  VisionStream,
} from '../../lib/types'

export type LatestDetections = Record<VisionStream, { event: DetectionEvent; receivedAt: number } | null>

const MAX_BACKOFF_MS = 10_000

function liveUrl(): string {
  const { protocol, host } = window.location
  return `${protocol === 'https:' ? 'wss:' : 'ws:'}//${host}/api/vision/live`
}

/**
 * Ground-side image processing: settings, session control, and the live WebSocket that carries
 * detections, alerts, and stats to the UI (and feed frames from it, in browser-frames mode).
 * Detections go into a ref, not state, so the overlay can redraw at frame rate without re-rendering.
 */
export function useVision(onAlert?: (alert: VisionAlert) => void) {
  const [capabilities, setCapabilities] = useState<VisionCapabilities | null>(null)
  const [settings, setSettings] = useState<VisionSettings | null>(null)
  const [session, setSession] = useState<VisionSession>({ running: false })
  const [stats, setStats] = useState<VisionStats | null>(null)
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const detections = useRef<LatestDetections>({ intruder: null, maintenance: null })
  const alertRef = useRef(onAlert)

  useEffect(() => {
    alertRef.current = onAlert
  }, [onAlert])

  useEffect(() => {
    api.getVisionCapabilities().then(setCapabilities).catch(() => undefined)
    api.getVisionSettings().then(setSettings).catch(() => undefined)
  }, [])

  useEffect(() => {
    let closed = false
    let retry = 0
    let backoff = 1000
    let ws: WebSocket | null = null

    const connect = () => {
      const token = tokenStore.get()
      if (!token) return
      ws = new WebSocket(liveUrl())
      ws.binaryType = 'arraybuffer'
      ws.onopen = () => {
        backoff = 1000
        ws?.send(JSON.stringify({ type: 'auth', token }))
        setSocket(ws)
      }
      ws.onmessage = (e) => {
        if (typeof e.data !== 'string') return
        const msg = JSON.parse(e.data)
        switch (msg.type) {
          case 'status':
            setSession(msg.session)
            if (!msg.session.running) {
              detections.current = { intruder: null, maintenance: null }
              setStats(null)
            }
            break
          case 'detections': {
            const stream: unknown = msg.stream
            if (stream === 'intruder' || stream === 'maintenance') {
              detections.current[stream] = { event: msg, receivedAt: performance.now() }
            }
            break
          }
          case 'stats':
            setStats(msg)
            break
          case 'alert':
            alertRef.current?.(msg)
            break
          case 'error':
            setError(msg.message)
            break
        }
      }
      ws.onclose = (e) => {
        setSocket((current) => (current === ws ? null : current))
        if (closed || e.code === 4401) return
        retry = window.setTimeout(connect, backoff)
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS)
      }
    }
    connect()

    return () => {
      closed = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [])

  const run = useCallback(async (action: () => Promise<unknown>): Promise<boolean> => {
    setBusy(true)
    setError(null)
    try {
      await action()
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
      return false
    } finally {
      setBusy(false)
    }
  }, [])

  const start = useCallback(() => run(async () => setSession(await api.startVision())), [run])
  const stop = useCallback(
    () =>
      run(async () => {
        await api.stopVision()
        setSession({ running: false })
      }),
    [run],
  )
  const saveSettings = useCallback(
    (next: VisionSettings) =>
      run(async () => {
        setSettings(await api.putVisionSettings(next))
        setSession(await api.getVisionSession())
      }),
    [run],
  )

  return { capabilities, settings, session, stats, socket, detections, busy, error, start, stop, saveSettings }
}

export type Vision = ReturnType<typeof useVision>
