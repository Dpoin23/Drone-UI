/** Grab the current frame of whatever is playing inside `stage` as a JPEG file. */
export async function captureFrame(stage: HTMLElement | null): Promise<File | null> {
  const source = stage?.querySelector<HTMLCanvasElement | HTMLVideoElement | HTMLImageElement>('canvas, video, img')
  if (!source) return null

  const [w, h] =
    source instanceof HTMLCanvasElement
      ? [source.width, source.height]
      : source instanceof HTMLVideoElement
        ? [source.videoWidth, source.videoHeight]
        : [source.naturalWidth, source.naturalHeight]
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
