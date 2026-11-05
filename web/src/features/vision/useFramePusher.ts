import { useEffect, useState } from 'react'
import { findFeedElement, intrinsicSize, type FeedElement } from '../livestream/snapshot'

type Options = {
  socket: WebSocket | null
  stage: HTMLElement | null
  enabled: boolean
  fps: number
  maxWidth: number
  /** Changes when the session restarts, so a paused frame is sent again. */
  sessionKey: string
}

const JPEG_QUALITY = 0.8

function encodeFrame(header: object, jpeg: ArrayBuffer): Uint8Array<ArrayBuffer> {
  const head = new TextEncoder().encode(JSON.stringify(header))
  const out = new Uint8Array(new ArrayBuffer(4 + head.length + jpeg.byteLength))
  new DataView(out.buffer).setUint32(0, head.length)
  out.set(head, 4)
  out.set(new Uint8Array(jpeg), 4 + head.length)
  return out
}

/** Recorded videos have a finite duration; WebRTC streams report Infinity and have no media time. */
function mediaTime(el: FeedElement): number | null {
  return el instanceof HTMLVideoElement && Number.isFinite(el.duration) ? el.currentTime : null
}

/**
 * Sends the frames the feed is displaying to the ground station, for sources it can't read
 * itself (demo feed, test videos in sync with playback, or WebRTC as a fallback).
 *
 * Like the server's latest-frame buffer, nothing queues: a tick is skipped while the previous
 * frame is still being encoded or is still in the socket's send buffer.
 */
export function useFramePusher({ socket, stage, enabled, fps, maxWidth, sessionKey }: Options) {
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!enabled || !socket || !stage || fps <= 0) return

    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    let busy = false
    let epoch = 0
    let lastSource: FeedElement | null = null
    let lastMediaTime: number | null = null

    const tick = async () => {
      if (busy || !ctx || socket.readyState !== WebSocket.OPEN || socket.bufferedAmount > 0) return
      const source = findFeedElement(stage)
      if (!source) return
      if (source instanceof HTMLVideoElement && source.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return
      const [w, h] = intrinsicSize(source)
      if (!w || !h) return

      if (source !== lastSource) {
        lastSource = source
        lastMediaTime = null
        epoch += 1
      }
      const time = mediaTime(source)
      // A paused video shows one frame; send it once rather than re-running inference on it.
      if (time !== null && source instanceof HTMLVideoElement && source.paused && time === lastMediaTime) return

      const scale = Math.min(1, maxWidth / w)
      canvas.width = Math.round(w * scale)
      canvas.height = Math.round(h * scale)
      const capturedAt = Date.now()
      ctx.drawImage(source, 0, 0, canvas.width, canvas.height)

      busy = true
      try {
        const blob = await new Promise<Blob | null>((resolve, reject) => {
          try {
            canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY)
          } catch (err) {
            reject(err)
          }
        })
        if (!blob || socket.readyState !== WebSocket.OPEN) return
        const header = { ts: capturedAt, media_time: time, epoch, w: canvas.width, h: canvas.height }
        socket.send(encodeFrame(header, await blob.arrayBuffer()))
        lastMediaTime = time
        setError(null)
      } catch {
        setError(
          "The browser can't read this stream's frames (cross-origin). Switch image processing to ground station capture.",
        )
      } finally {
        busy = false
      }
    }

    const timer = window.setInterval(() => void tick(), 1000 / fps)
    return () => clearInterval(timer)
  }, [socket, stage, enabled, fps, maxWidth, sessionKey])

  return enabled ? error : null
}
