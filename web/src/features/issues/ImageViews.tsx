import { ChevronLeft, ChevronRight, ImageOff, ImagePlus, X } from 'lucide-react'
import { useEffect, useRef, useState, type DragEvent } from 'react'
import type { IssueImage } from '../../lib/types'
import { ACCEPTED_IMAGE_TYPES, useImageSrc } from './images'

export function IssueImg({ issueId, image, className = '' }: { issueId: number; image: IssueImage; className?: string }) {
  const { src, failed } = useImageSrc(issueId, image.id)
  if (failed) {
    return (
      <div className={`grid place-items-center bg-black/40 text-zinc-600 ${className}`}>
        <ImageOff className="size-4" />
      </div>
    )
  }
  if (!src) return <div className={`animate-pulse bg-white/[0.05] ${className}`} />
  return <img src={src} alt={image.filename} className={`object-cover ${className}`} />
}

/** Preview of an issue's first image, with a count badge when it has more. */
export function IssueThumb({ issueId, images, className = '' }: { issueId: number; images: IssueImage[]; className?: string }) {
  if (images.length === 0) return null
  return (
    <div className={`relative shrink-0 overflow-hidden rounded-lg ring-1 ring-line ${className}`}>
      <IssueImg issueId={issueId} image={images[0]} className="h-full w-full" />
      {images.length > 1 && (
        <span className="absolute right-1 bottom-1 rounded bg-black/70 px-1 text-[10px] font-semibold text-zinc-100 tabular-nums backdrop-blur">
          +{images.length - 1}
        </span>
      )}
    </div>
  )
}

export function ImageDropzone({ onFiles, compact = false }: { onFiles: (files: File[]) => void; compact?: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    onFiles(Array.from(e.dataTransfer.files))
  }

  return (
    <button
      type="button"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`flex w-full items-center justify-center gap-2 rounded-lg border border-dashed text-sm transition ${
        dragging
          ? 'border-cyan-400/60 bg-cyan-400/[0.06] text-cyan-200'
          : 'border-white/15 text-zinc-400 hover:border-white/25 hover:bg-white/[0.03] hover:text-zinc-200'
      } ${compact ? 'h-full min-h-20 flex-col' : 'py-5'}`}
    >
      <ImagePlus className="size-5" />
      <span>{compact ? 'Add' : 'Drop images or click to upload'}</span>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_IMAGE_TYPES.join(',')}
        className="hidden"
        onChange={(e) => {
          onFiles(Array.from(e.target.files ?? []))
          e.target.value = ''
        }}
      />
    </button>
  )
}

export function Lightbox({
  issueId,
  images,
  index,
  onIndex,
  onClose,
}: {
  issueId: number
  images: IssueImage[]
  index: number
  onIndex: (i: number) => void
  onClose: () => void
}) {
  const image = images[index]
  const { src } = useImageSrc(issueId, image?.id)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowRight') onIndex((index + 1) % images.length)
      else if (e.key === 'ArrowLeft') onIndex((index - 1 + images.length) % images.length)
      else return
      e.stopPropagation()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [index, images.length, onIndex, onClose])

  if (!image) return null
  const nav = 'absolute top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-2 text-zinc-100 backdrop-blur hover:bg-white/20'

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/90 p-6" onClick={onClose}>
      <button className="absolute top-4 right-4 rounded-md p-2 text-zinc-300 hover:bg-white/10" aria-label="Close">
        <X className="size-6" />
      </button>
      {src ? (
        <img src={src} alt={image.filename} className="max-h-full max-w-full rounded-lg object-contain" onClick={(e) => e.stopPropagation()} />
      ) : (
        <div className="size-12 animate-pulse rounded-full bg-white/10" />
      )}
      {images.length > 1 && (
        <>
          <button
            className={`${nav} left-4`}
            aria-label="Previous image"
            onClick={(e) => {
              e.stopPropagation()
              onIndex((index - 1 + images.length) % images.length)
            }}
          >
            <ChevronLeft className="size-6" />
          </button>
          <button
            className={`${nav} right-4`}
            aria-label="Next image"
            onClick={(e) => {
              e.stopPropagation()
              onIndex((index + 1) % images.length)
            }}
          >
            <ChevronRight className="size-6" />
          </button>
        </>
      )}
      <div className="absolute inset-x-0 bottom-4 text-center text-sm text-zinc-400">
        {image.filename} · {index + 1} / {images.length}
      </div>
    </div>
  )
}
