import type { KeyboardEvent } from 'react'

const SPEEDS = [0.25, 0.5, 1, 1.5, 2]
export const SKIP_SECONDS = 10
const NUDGE_SECONDS = 5

export function playerCommands(video: HTMLVideoElement, fps: number) {
  const seek = (t: number) => {
    const end = Number.isFinite(video.duration) ? video.duration : t
    video.currentTime = Math.min(Math.max(0, t), end)
  }
  return {
    seek,
    toggle: () => (video.paused || video.ended ? void video.play().catch(() => {}) : video.pause()),
    stop: () => {
      video.pause()
      seek(0)
    },
    skip: (seconds: number) => seek(video.currentTime + seconds),
    step: (frames: number) => {
      video.pause()
      seek(video.currentTime + frames / fps)
    },
    toggleMute: () => {
      video.muted = !video.muted
    },
    toggleLoop: () => {
      video.loop = !video.loop
      return video.loop
    },
    cycleSpeed: () => {
      video.playbackRate = SPEEDS.find((s) => s > video.playbackRate) ?? SPEEDS[0]
    },
  }
}

/** Keyboard shortcuts for the player. Returns true if the key was handled. */
export function handlePlayerKey(e: KeyboardEvent, video: HTMLVideoElement, fps: number): boolean {
  if (e.metaKey || e.ctrlKey || e.altKey) return false
  const target = e.target as HTMLElement
  if (target.tagName === 'BUTTON' && (e.key === ' ' || e.key === 'Enter')) return false
  if (target.tagName === 'INPUT' && ['ArrowLeft', 'ArrowRight', 'Home'].includes(e.key)) return false
  const c = playerCommands(video, fps)
  const actions: Record<string, () => void> = {
    ' ': c.toggle,
    k: c.toggle,
    j: () => c.skip(-SKIP_SECONDS),
    l: () => c.skip(SKIP_SECONDS),
    ArrowLeft: () => c.skip(-NUDGE_SECONDS),
    ArrowRight: () => c.skip(NUDGE_SECONDS),
    ',': () => c.step(-1),
    '.': () => c.step(1),
    Home: c.stop,
    m: c.toggleMute,
  }
  const action = actions[e.key.length === 1 ? e.key.toLowerCase() : e.key]
  if (!action) return false
  e.preventDefault()
  action()
  return true
}
