import {
  FastForward,
  Pause,
  Play,
  Repeat,
  Rewind,
  Square,
  StepBack,
  StepForward,
  Volume2,
  VolumeX,
} from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { formatClock } from '../../lib/format'
import { playerCommands, SKIP_SECONDS } from './playerCommands'

const EVENTS = [
  'play', 'pause', 'timeupdate', 'seeked', 'durationchange', 'loadedmetadata', 'ratechange', 'volumechange', 'ended',
] as const

type PlaybackState = { paused: boolean; time: number; duration: number; rate: number; muted: boolean }

function readState(video: HTMLVideoElement): PlaybackState {
  return {
    paused: video.paused,
    time: video.currentTime,
    duration: video.duration,
    rate: video.playbackRate,
    muted: video.muted,
  }
}

function usePlaybackState(video: HTMLVideoElement): PlaybackState {
  const [state, setState] = useState(() => readState(video))
  useEffect(() => {
    const update = () => setState(readState(video))
    EVENTS.forEach((e) => video.addEventListener(e, update))
    return () => EVENTS.forEach((e) => video.removeEventListener(e, update))
  }, [video])
  return state
}

export function VideoControls({ video, fps }: { video: HTMLVideoElement; fps: number }) {
  const s = usePlaybackState(video)
  const [loop, setLoop] = useState(video.loop)
  const c = playerCommands(video, fps)
  const duration = Number.isFinite(s.duration) ? s.duration : 0

  return (
    <div
      className={`absolute inset-x-0 bottom-0 z-10 bg-linear-to-t from-black/85 via-black/50 to-transparent px-4 pt-10 pb-3 transition-opacity ${
        s.paused ? 'opacity-100' : 'opacity-0 focus-within:opacity-100 group-hover:opacity-100'
      }`}
    >
      <input
        type="range"
        aria-label="Seek"
        min={0}
        max={duration}
        step="any"
        value={Math.min(s.time, duration)}
        onChange={(e) => c.seek(Number(e.target.value))}
        className="h-1 w-full cursor-pointer accent-cyan-400"
      />
      <div className="mt-2 flex items-center gap-1">
        <ControlButton label="Stop (Home)" onClick={c.stop}>
          <Square className="size-4" />
        </ControlButton>
        <ControlButton label={`Back ${SKIP_SECONDS} s (J)`} onClick={() => c.skip(-SKIP_SECONDS)}>
          <Rewind className="size-4" />
        </ControlButton>
        <ControlButton label="Previous frame (,)" onClick={() => c.step(-1)}>
          <StepBack className="size-4" />
        </ControlButton>
        <ControlButton label={s.paused ? 'Play (Space)' : 'Pause (Space)'} onClick={c.toggle} primary>
          {s.paused ? <Play className="size-5" /> : <Pause className="size-5" />}
        </ControlButton>
        <ControlButton label="Next frame (.)" onClick={() => c.step(1)}>
          <StepForward className="size-4" />
        </ControlButton>
        <ControlButton label={`Forward ${SKIP_SECONDS} s (L)`} onClick={() => c.skip(SKIP_SECONDS)}>
          <FastForward className="size-4" />
        </ControlButton>
        <span className="ml-2 font-mono text-xs text-zinc-300 tabular-nums">
          {formatClock(s.time, true)} / {formatClock(s.duration)}
        </span>

        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={c.cycleSpeed}
            title="Playback speed"
            className="rounded-md px-2 py-1 font-mono text-xs text-zinc-200 tabular-nums hover:bg-white/10"
          >
            {s.rate}×
          </button>
          <ControlButton label={loop ? 'Loop on' : 'Loop off'} onClick={() => setLoop(c.toggleLoop())} active={loop}>
            <Repeat className="size-4" />
          </ControlButton>
          <ControlButton label={s.muted ? 'Unmute (M)' : 'Mute (M)'} onClick={c.toggleMute}>
            {s.muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
          </ControlButton>
        </div>
      </div>
    </div>
  )
}

function ControlButton({
  label,
  onClick,
  primary,
  active,
  children,
}: {
  label: string
  onClick: () => void
  primary?: boolean
  active?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      // Keep focus on the player so keyboard shortcuts keep working after a click.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={`grid place-items-center rounded-md transition ${
        primary ? 'size-9 bg-white/10 text-white hover:bg-white/20' : 'size-8 hover:bg-white/10'
      } ${active ? 'text-cyan-300' : primary ? '' : 'text-zinc-200'}`}
    >
      {children}
    </button>
  )
}
