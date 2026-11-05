import type { Category, Issue, IssueDraft, IssuePatch, StreamSettings, User, Video } from './types'

const TOKEN_KEY = 'drone-ui.token'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) {
      const field = detail[0].loc?.at(-1)
      return field ? `${field}: ${detail[0].msg}` : detail[0].msg
    }
  }
  return fallback
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (typeof init.body === 'string') headers.set('Content-Type', 'application/json')

  let res: Response
  try {
    res = await fetch(path, { ...init, headers })
  } catch {
    throw new ApiError(0, 'Cannot reach the ground station service')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    if (res.status === 401 && token) onUnauthorized?.()
    throw new ApiError(res.status, errorMessage(body, `Request failed (${res.status})`))
  }
  return res
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await send(path, init)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

type AuthResponse = { token: string; user: User }

export const api = {
  register: (username: string, password: string) =>
    request<AuthResponse>('/api/auth/register', { method: 'POST', body: JSON.stringify({ username, password }) }),
  login: (username: string, password: string) =>
    request<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  me: () => request<User>('/api/auth/me'),

  listIssues: (category?: Category) =>
    request<Issue[]>(`/api/issues${category ? `?category=${category}` : ''}`),
  createIssue: (draft: IssueDraft) =>
    request<Issue>('/api/issues', { method: 'POST', body: JSON.stringify(draft) }),
  updateIssue: (id: number, patch: IssuePatch) =>
    request<Issue>(`/api/issues/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteIssue: (id: number) => request<void>(`/api/issues/${id}`, { method: 'DELETE' }),

  uploadImages: (issueId: number, files: File[]) => {
    const form = new FormData()
    for (const f of files) form.append('files', f, f.name)
    return request<Issue>(`/api/issues/${issueId}/images`, { method: 'POST', body: form })
  },
  deleteImage: (issueId: number, imageId: number) =>
    request<Issue>(`/api/issues/${issueId}/images/${imageId}`, { method: 'DELETE' }),
  fetchImage: async (issueId: number, imageId: number) =>
    (await send(`/api/issues/${issueId}/images/${imageId}`)).blob(),

  getStreamSettings: () => request<StreamSettings>('/api/stream-settings'),
  putStreamSettings: (settings: StreamSettings) =>
    request<StreamSettings>('/api/stream-settings', { method: 'PUT', body: JSON.stringify(settings) }),

  listVideos: () => request<Video[]>('/api/videos'),
  getVideo: (id: number) => request<Video>(`/api/videos/${id}`),
  importVideo: (url: string) =>
    request<Video>('/api/videos/import', { method: 'POST', body: JSON.stringify({ url }) }),
  deleteVideo: (id: number) => request<void>(`/api/videos/${id}`, { method: 'DELETE' }),
  videoPlaybackUrl: (id: number) => request<{ url: string; expires_at: number }>(`/api/videos/${id}/playback`),
  uploadVideo: (file: File, onProgress?: (fraction: number) => void) =>
    new Promise<Video>((resolve, reject) => {
      // XHR rather than fetch: fetch can't report upload progress, and videos can be large.
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/videos/upload')
      const token = tokenStore.get()
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      xhr.responseType = 'json'
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) return resolve(xhr.response as Video)
        if (xhr.status === 401 && token) onUnauthorized?.()
        reject(new ApiError(xhr.status, errorMessage(xhr.response, `Upload failed (${xhr.status})`)))
      }
      xhr.onerror = () => reject(new ApiError(0, 'Cannot reach the ground station service'))
      const form = new FormData()
      form.append('file', file, file.name)
      xhr.send(form)
    }),
}
