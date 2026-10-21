import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

export const ACCEPTED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024

// Image endpoints need the bearer token, so <img src> can't point at them directly.
// Fetch once per image and share the object URL between the list and the drawer.
const cache = new Map<number, Promise<string>>()

function loadImage(issueId: number, imageId: number): Promise<string> {
  let p = cache.get(imageId)
  if (!p) {
    p = api.fetchImage(issueId, imageId).then((blob) => URL.createObjectURL(blob))
    p.catch(() => cache.delete(imageId))
    cache.set(imageId, p)
  }
  return p
}

export function forgetImage(imageId: number) {
  const p = cache.get(imageId)
  cache.delete(imageId)
  p?.then((url) => URL.revokeObjectURL(url)).catch(() => undefined)
}

export function useImageSrc(issueId: number, imageId: number | undefined) {
  const [state, setState] = useState<{ id: number; url: string | null; failed: boolean } | null>(null)

  useEffect(() => {
    if (imageId === undefined) return
    let cancelled = false
    loadImage(issueId, imageId)
      .then((url) => !cancelled && setState({ id: imageId, url, failed: false }))
      .catch(() => !cancelled && setState({ id: imageId, url: null, failed: true }))
    return () => {
      cancelled = true
    }
  }, [issueId, imageId])

  const current = state && state.id === imageId ? state : null
  return { src: current?.url ?? null, failed: current?.failed ?? false }
}

export function validateImageFiles(files: File[]): { ok: File[]; error: string | null } {
  const ok: File[] = []
  const problems: string[] = []
  for (const f of files) {
    if (!ACCEPTED_IMAGE_TYPES.includes(f.type)) problems.push(`${f.name} is not a JPEG, PNG, GIF, or WebP image`)
    else if (f.size > MAX_IMAGE_BYTES) problems.push(`${f.name} is larger than 10 MB`)
    else ok.push(f)
  }
  return { ok, error: problems.length ? problems.join('. ') : null }
}
