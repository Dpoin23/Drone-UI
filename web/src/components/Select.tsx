import { Check, ChevronDown } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

export type SelectOption<T extends string> = { value: T; label: string; dot?: string }

type Props<T extends string> = {
  value: T
  options: SelectOption<T>[]
  onChange: (value: T) => void
  id?: string
  ariaLabel?: string
  className?: string
}

export function Select<T extends string>({ value, options, onChange, id, ariaLabel, className = '' }: Props<T>) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  const selected = options.find((o) => o.value === value) ?? options[0]

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  function openList() {
    setActive(Math.max(0, options.findIndex((o) => o.value === value)))
    setOpen(true)
  }

  function choose(v: T) {
    onChange(v)
    setOpen(false)
  }

  function onKeyDown(e: KeyboardEvent) {
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault()
        openList()
      }
      return
    }
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setActive((i) => Math.min(options.length - 1, i + 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setActive((i) => Math.max(0, i - 1))
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        choose(options[active].value)
        break
      case 'Escape':
        e.preventDefault()
        e.stopPropagation()
        setOpen(false)
        break
      case 'Tab':
        setOpen(false)
        break
    }
  }

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        id={id}
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
        className={`input flex items-center gap-2 text-left ${open ? 'border-cyan-400/60 ring-2 ring-cyan-400/20' : ''}`}
      >
        {selected?.dot && <span className={`size-1.5 shrink-0 rounded-full ${selected.dot}`} />}
        <span className="flex-1 truncate">{selected?.label}</span>
        <ChevronDown className={`size-4 shrink-0 text-zinc-500 transition ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-activedescendant={`${listId}-${active}`}
          className="absolute top-full right-0 left-0 z-40 mt-1 min-w-max overflow-hidden rounded-lg border border-line bg-panel-2 py-1 shadow-xl shadow-black/50"
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={o.value === value}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(o.value)}
              className={`flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm ${
                i === active ? 'bg-white/[0.06] text-zinc-50' : 'text-zinc-300'
              }`}
            >
              {o.dot && <span className={`size-1.5 shrink-0 rounded-full ${o.dot}`} />}
              <span className="flex-1">{o.label}</span>
              <Check className={`size-3.5 text-cyan-400 ${o.value === value ? '' : 'invisible'}`} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
