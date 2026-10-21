import { useCallback, useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { Category, Issue, IssueDraft, IssuePatch } from '../../lib/types'
import { forgetImage } from './images'

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
    setIssues((prev) => {
      prev.find((i) => i.id === id)?.images.forEach((img) => forgetImage(img.id))
      return prev.filter((i) => i.id !== id)
    })
  }, [])

  const replace = (updated: Issue) => setIssues((prev) => prev.map((i) => (i.id === updated.id ? updated : i)))

  const addImages = useCallback(async (id: number, files: File[]) => {
    const updated = await api.uploadImages(id, files)
    replace(updated)
    return updated
  }, [])

  const removeImage = useCallback(async (id: number, imageId: number) => {
    const updated = await api.deleteImage(id, imageId)
    forgetImage(imageId)
    replace(updated)
    return updated
  }, [])

  return { issues, loading, error, create, update, remove, addImages, removeImage }
}
