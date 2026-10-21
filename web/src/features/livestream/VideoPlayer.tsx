import { useCallback, useEffect, useRef } from 'react'
import type { StreamSettings } from '../../lib/types'
import { DemoFeed } from './DemoFeed'
import { startWhep } from './whep'

export type StreamStatus = 'idle' | 'connecting' | 'live' | 'error'

type Props = {
  settings: StreamSettings
  onStatus: (status: StreamStatus, message?: string) => void
}

export function VideoPlayer({ settings, onStatus }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const { transport, url } = settings

  useEffect(() => {
    if (transport !== 'webrtc') return
    const video = videoRef.current
    if (!video || !url) {
      onStatus('idle', 'Set a WHEP URL in stream settings')
      return
    }

    let cancelled = false
    let session: { close: () => void } | null = null
    onStatus('connecting')

    startWhep(url, video, (state) => {
      if (cancelled) return
      if (state === 'connected') onStatus('live')
      else if (state === 'failed' || state === 'disconnected') onStatus('error', `WebRTC ${state}`)
    })
      .then((s) => {
        if (cancelled) s.close()
        else session = s
      })
      .catch((err: Error) => !cancelled && onStatus('error', err.message))

    return () => {
      cancelled = true
      session?.close()
    }
  }, [transport, url, onStatus])

  useEffect(() => {
    if (transport === 'mjpeg') onStatus(url ? 'connecting' : 'idle', url ? undefined : 'Set an MJPEG URL in stream settings')
  }, [transport, url, onStatus])

  const onDemoReady = useCallback(() => onStatus('live'), [onStatus])

  if (transport === 'demo') return <DemoFeed onReady={onDemoReady} />

  if (transport === 'mjpeg') {
    return url ? (
      <img
        key={url}
        src={url}
        alt="Drone camera feed"
        className="h-full w-full object-contain"
        onLoad={(e) => {
          e.currentTarget.style.visibility = 'visible'
          onStatus('live')
        }}
        onError={(e) => {
          e.currentTarget.style.visibility = 'hidden'
          onStatus('error', 'Could not load MJPEG stream')
        }}
      />
    ) : null
  }

  return <video ref={videoRef} autoPlay muted playsInline className="h-full w-full object-contain" />
}
