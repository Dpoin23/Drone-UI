import { useEffect, useRef, type RefObject } from 'react'
import type { DetectionEvent, DetectionItem, VisionStream } from '../../lib/types'
import { findFeedElement, intrinsicSize, type FeedElement } from '../livestream/snapshot'
import type { LatestDetections } from './useVision'

const COLORS = { security: '#fb7185', maintenance: '#fbbf24' } as const

/** How long a result stays on screen without a newer one, in seconds. */
const HOLD_S: Record<VisionStream, number> = { intruder: 1.2, maintenance: 3 }
/** Velocity extrapolation stops after this long, so a lost track doesn't drift off. */
const MAX_EXTRAPOLATE_S = 0.6

type Rect = { x: number; y: number; w: number; h: number }

/** Where the video's pixels are drawn inside the overlay, accounting for object-fit letterboxing. */
function contentRect(media: FeedElement, overlay: HTMLCanvasElement): Rect | null {
  const [iw, ih] = intrinsicSize(media)
  if (!iw || !ih) return null
  const m = media.getBoundingClientRect()
  const o = overlay.getBoundingClientRect()
  const fit = getComputedStyle(media).objectFit
  if (fit === 'fill') return { x: m.left - o.left, y: m.top - o.top, w: m.width, h: m.height }
  const scale = fit === 'cover' ? Math.max(m.width / iw, m.height / ih) : Math.min(m.width / iw, m.height / ih)
  const w = iw * scale
  const h = ih * scale
  return { x: m.left - o.left + (m.width - w) / 2, y: m.top - o.top + (m.height - h) / 2, w, h }
}

/**
 * Seconds between the frame a result came from and what's on screen now, or null if the result
 * no longer applies. Recorded video is compared by media time, so boxes hold while paused and
 * vanish after a seek; live streams use wall-clock age.
 */
function resultAge(
  stream: VisionStream,
  event: DetectionEvent,
  receivedAt: number,
  media: FeedElement,
  syncMediaTime: boolean,
): number | null {
  if (syncMediaTime && event.media_time !== null && media instanceof HTMLVideoElement && Number.isFinite(media.duration)) {
    const dt = media.currentTime - event.media_time
    return dt >= -0.1 && dt <= HOLD_S[stream] ? Math.max(0, dt) : null
  }
  const age = (performance.now() - receivedAt) / 1000
  return age <= HOLD_S[stream] ? age : null
}

function drawItem(ctx: CanvasRenderingContext2D, item: DetectionItem, rect: Rect, dt: number, alpha: number) {
  let { x, y } = item.bbox
  if (item.velocity) {
    const t = Math.min(dt, MAX_EXTRAPOLATE_S)
    x += item.velocity.vx * t
    y += item.velocity.vy * t
  }
  const px = rect.x + x * rect.w
  const py = rect.y + y * rect.h
  const pw = item.bbox.w * rect.w
  const ph = item.bbox.h * rect.h
  const color = COLORS[item.category]

  ctx.globalAlpha = alpha
  ctx.strokeStyle = color
  ctx.lineWidth = 2
  ctx.strokeRect(px, py, pw, ph)

  const name = item.category === 'maintenance' ? (item.title ?? item.label) : item.label
  const text = `${name}${item.track_id !== null && item.category === 'security' ? ` #${item.track_id}` : ''} ${Math.round(item.confidence * 100)}%`
  ctx.font = '600 12px ui-monospace, SFMono-Regular, Menlo, monospace'
  const tw = ctx.measureText(text).width + 10
  const ty = py >= 20 ? py - 20 : py
  ctx.fillStyle = color
  ctx.fillRect(px - 1, ty, tw, 20)
  ctx.fillStyle = '#0b0f14'
  ctx.fillText(text, px + 4, ty + 14)
  ctx.globalAlpha = 1
}

export function DetectionOverlay({
  stage,
  detections,
  enabled,
  syncMediaTime,
}: {
  stage: HTMLElement | null
  detections: RefObject<LatestDetections>
  enabled: boolean
  /** True when results come from the frames this page sent, so media times line up with playback. */
  syncMediaTime: boolean
}) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx || !enabled) return
    let raf = 0

    const draw = () => {
      raf = requestAnimationFrame(draw)
      const dpr = window.devicePixelRatio || 1
      const w = Math.round(canvas.clientWidth * dpr)
      const h = Math.round(canvas.clientHeight * dpr)
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w
        canvas.height = h
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight)

      const media = findFeedElement(stage)
      const rect = media && contentRect(media, canvas)
      if (!media || !rect) return
      for (const stream of ['maintenance', 'intruder'] as const) {
        const latest = detections.current[stream]
        if (!latest) continue
        const dt = resultAge(stream, latest.event, latest.receivedAt, media, syncMediaTime)
        if (dt === null) continue
        const alpha = Math.min(1, 1.5 * (1 - dt / HOLD_S[stream]) + 0.25)
        for (const item of latest.event.items) drawItem(ctx, item, rect, dt, alpha)
      }
    }
    raf = requestAnimationFrame(draw)
    return () => {
      cancelAnimationFrame(raf)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
    }
  }, [stage, detections, enabled, syncMediaTime])

  return <canvas ref={ref} data-overlay className="pointer-events-none absolute inset-0 h-full w-full" />
}
