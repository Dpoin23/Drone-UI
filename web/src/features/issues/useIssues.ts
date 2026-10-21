import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { Category, Issue, IssueDraft, IssuePatch } from '../../lib/types'

export function useIssues(category?: Category) {
  const [issues, setIssues] = useState<Issue[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .listIssues(category)
      .then((rows) => {
        if (cancelled) return
        setIssues(rows)
        setError(null)
      })
      .catch((err: Error) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [category])

  const create = useCallback(async (draft: IssueDraft) => {
    const created = await api.createIssue(draft)
    setIssues((prev) => (!category || created.category === category ? [created, ...prev] : prev))
    return created
  }, [category])

  const update = useCallback(async (id: number, patch: IssuePatch) => {
    const updated = await api.updateIssue(id, patch)
    setIssues((prev) => prev.map((i) => (i.id === id ? updated : i)))
    return updated
  }, [])

  const remove = useCallback(async (id: number) => {
    await api.deleteIssue(id)
    setIssues((prev) => prev.filter((i) => i.id !== id))
  }, [])

  return { issues, loading, error, create, update, remove }
}
