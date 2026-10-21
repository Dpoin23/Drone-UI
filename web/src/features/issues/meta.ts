import { ShieldAlert, Wrench, type LucideIcon } from 'lucide-react'
import type { Category, IssueStatus, Severity } from '../../lib/types'

export const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']
export const STATUSES: IssueStatus[] = ['open', 'acknowledged', 'resolved', 'false_positive']
export const OPEN_STATUSES: IssueStatus[] = ['open', 'acknowledged']

export const severityStyle: Record<Severity, string> = {
  critical: 'bg-rose-500/15 text-rose-300 ring-rose-500/30',
  high: 'bg-orange-500/15 text-orange-300 ring-orange-500/30',
  medium: 'bg-sky-500/15 text-sky-300 ring-sky-500/30',
  low: 'bg-zinc-500/15 text-zinc-300 ring-zinc-500/30',
}

export const severityDot: Record<Severity, string> = {
  critical: 'bg-rose-400 shadow-[0_0_10px_2px_rgb(251_113_133/0.5)]',
  high: 'bg-orange-400',
  medium: 'bg-sky-400',
  low: 'bg-zinc-400',
}

export const statusStyle: Record<IssueStatus, string> = {
  open: 'bg-cyan-500/10 text-cyan-300 ring-cyan-500/30',
  acknowledged: 'bg-violet-500/10 text-violet-300 ring-violet-500/30',
  resolved: 'bg-emerald-500/10 text-emerald-300 ring-emerald-500/30',
  false_positive: 'bg-zinc-500/10 text-zinc-400 ring-zinc-500/30',
}

export function statusLabel(status: IssueStatus, category: Category): string {
  switch (status) {
    case 'open':
      return 'Open'
    case 'acknowledged':
      return category === 'security' ? 'Acknowledged' : 'In progress'
    case 'resolved':
      return 'Resolved'
    case 'false_positive':
      return category === 'security' ? 'False positive' : 'Dismissed'
  }
}

type CategoryMeta = {
  title: string
  singular: string
  blurb: string
  icon: LucideIcon
  accent: string
  accentBg: string
  examples: string
}

export const categoryMeta: Record<Category, CategoryMeta> = {
  security: {
    title: 'Security risks',
    singular: 'security risk',
    blurb: 'People, vehicles, open gates, fence breaches, and unknown objects near the perimeter.',
    icon: ShieldAlert,
    accent: 'text-rose-400',
    accentBg: 'from-rose-500/20 to-rose-500/0 ring-rose-500/30',
    examples: 'e.g. Unknown person near north gate',
  },
  maintenance: {
    title: 'Maintenance',
    singular: 'maintenance issue',
    blurb: 'Damaged fencing, debris, overgrowth, broken lights, standing water, and corrosion.',
    icon: Wrench,
    accent: 'text-amber-400',
    accentBg: 'from-amber-500/20 to-amber-500/0 ring-amber-500/30',
    examples: 'e.g. Fence panel sagging at post 14',
  },
}
