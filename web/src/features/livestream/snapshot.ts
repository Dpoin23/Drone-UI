export type FeedElement = HTMLCanvasElement | HTMLVideoElement | HTMLImageElement

/** The element showing the feed inside `stage`: the demo canvas, a `<video>`, or an MJPEG `<img>`. */
export function findFeedElement(stage: HTMLElement | null): FeedElement | null {
  return stage?.querySelector<FeedElement>('canvas:not([data-overlay]), video, img') ?? null
}

export function intrinsicSize(source: FeedElement): [number, number] {
  if (source instanceof HTMLCanvasElement) return [source.width, source.height]
  if (source instanceof HTMLVideoElement) return [source.videoWidth, source.videoHeight]
  return [source.naturalWidth, source.naturalHeight]
}

/** Grab the current frame of whatever is playing inside `stage` as a JPEG file. */
export async function captureFrame(stage: HTMLElement | null): Promise<File | null> {
  const source = findFeedElement(stage)
  if (!source) return null

  const [w, h] = intrinsicSize(source)
  if (!w || !h) return null

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  canvas.getContext('2d')?.drawImage(source, 0, 0, w, h)

  try {
    // Throws for cross-origin MJPEG streams without CORS headers (tainted canvas).
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.9))
    if (!blob) return null
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
    return new File([blob], `snapshot-${stamp}.jpg`, { type: 'image/jpeg' })
  } catch {
    return null
  }
}
