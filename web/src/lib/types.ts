export type User = { id: number; username: string }

export type Category = 'security' | 'maintenance'
export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type IssueStatus = 'open' | 'acknowledged' | 'resolved' | 'false_positive'

export type IssueImage = {
  id: number
  filename: string
  content_type: string
  size_bytes: number
  created_at: string
}

export type Issue = {
  id: number
  category: Category
  title: string
  description: string
  severity: Severity
  status: IssueStatus
  location: string
  source: string
  created_at: string
  updated_at: string
  resolved_at: string | null
  images: IssueImage[]
}

export type IssueDraft = {
  category: Category
  title: string
  description: string
  severity: Severity
  location: string
}

export type IssuePatch = Partial<Pick<Issue, 'title' | 'description' | 'severity' | 'status' | 'location'>>

export type StreamTransport = 'demo' | 'webrtc' | 'mjpeg'
export type StreamSettings = { transport: StreamTransport; url: string }
