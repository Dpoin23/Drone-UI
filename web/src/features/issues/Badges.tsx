import type { Category, IssueStatus, Severity } from '../../lib/types'
import { severityDot, severityStyle, statusLabel, statusStyle } from './meta'

const pill = 'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset'

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`${pill} capitalize ${severityStyle[severity]}`}>
      <span className={`size-1.5 rounded-full ${severityDot[severity]}`} />
      {severity}
    </span>
  )
}

export function StatusBadge({ status, category }: { status: IssueStatus; category: Category }) {
  return <span className={`${pill} ${statusStyle[status]}`}>{statusLabel(status, category)}</span>
}
