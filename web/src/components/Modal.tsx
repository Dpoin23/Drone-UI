import { X } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'

type Props = {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  side?: 'center' | 'right'
}

export function Modal({ open, onClose, title, children, side = 'center' }: Props) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const container =
    side === 'right'
      ? 'fixed inset-y-0 right-0 flex w-full max-w-lg flex-col border-l border-line bg-panel shadow-2xl'
      : 'relative w-full max-w-lg rounded-2xl border border-line bg-panel shadow-2xl'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className={container}>
        <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
          <h2 className="min-w-0 truncate text-base font-semibold text-zinc-100">{title}</h2>
          <button className="rounded-md p-1 text-zinc-400 hover:bg-white/5 hover:text-zinc-100" onClick={onClose} aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        <div className={side === 'right' ? 'flex-1 overflow-y-auto p-5' : 'p-5'}>{children}</div>
      </div>
    </div>
  )
}
