import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { Video } from '../../lib/types'
import type { StreamStatus } from './VideoPlayer'
import { handlePlayerKey, playerCommands } from './playerCommands'
import { VideoControls } from './VideoControls'

const DEFAULT_FPS = 30

type Props = {
  videoId: number | null
  onStatus: (status: StreamStatus, message?: string) => void
  onVideo?: (video: Video | null) => void
}

/**
 * Plays a video from the account's test library in the feed display. The file is served from the
 * ground station (same origin), so frames can be drawn to a canvas for snapshots and detection.
 * Mount with `key={videoId}` so switching videos starts from a clean state.
 */
export function TestVideoPlayer({ videoId, onStatus, onVideo }: Props) {
  const [meta, setMeta] = useState<Video | null>(null)
  const [src, setSrc] = useState<string | null>(null)
  const [video, setVideo] = useState<HTMLVideoElement | null>(null)

  useEffect(() => {
    if (videoId === null) {
      onStatus('idle', 'Pick a test video in stream settings')
      return
    }
    let cancelled = false
    let timer = 0
    onStatus('connecting')

    const load = async () => {
      try {
        const v = await api.getVideo(videoId)
        if (cancelled) return
        setMeta(v)
        if (v.status === 'downloading') {
          onStatus('connecting', `Downloading video… ${Math.round((v.progress ?? 0) * 100)}%`)
          timer = window.setTimeout(load, 1000)
        } else if (v.status === 'error') {
          onStatus('error', v.error ?? 'Import failed')
        } else {
          const { url } = await api.videoPlaybackUrl(videoId)
          if (!cancelled) setSrc(url)
        }
      } catch (err) {
        if (!cancelled) onStatus('error', err instanceof Error ? err.message : 'Could not load video')
      }
    }
    void load()

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [videoId, onStatus])

  useEffect(() => onVideo?.(meta), [meta, onVideo])

  const fps = meta?.fps || DEFAULT_FPS

  return (
    <div
      tabIndex={0}
      aria-label="Test video player"
      className="h-full w-full outline-none"
      onKeyDown={(e) => video && handlePlayerKey(e, video, fps)}
    >
      {src && (
        <video
          ref={setVideo}
          src={src}
          autoPlay
          muted
          playsInline
          className="h-full w-full object-contain"
          onClick={() => video && playerCommands(video, fps).toggle()}
          onLoadedData={() => onStatus('live')}
          onError={() => onStatus('error', "Couldn't play this video. The browser may not support its format.")}
        />
      )}
      {video && <VideoControls video={video} fps={fps} />}
    </div>
  )
}
