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

export type StreamTransport = 'demo' | 'webrtc' | 'mjpeg' | 'video'
/** For the `video` transport, `url` holds the id of a video in the account's library. */
export type StreamSettings = { transport: StreamTransport; url: string }

export type FlightMode = 'takeoff_landing' | 'transit' | 'patrol' | 'inspection' | 'return_to_base'
export type VisionStream = 'intruder' | 'maintenance'
export type FrameSource = 'auto' | 'server' | 'browser'
export type VisionRates = Record<FlightMode, Record<VisionStream, number>>

export type VisionSettings = {
  mode: FlightMode
  frame_source: FrameSource
  capture_url: string
  rates: VisionRates
  auto_issues: boolean
  follow_telemetry: boolean
}

export type VisionCapabilities = {
  installed: boolean
  streams: Record<VisionStream, { available: boolean; model: string | null; reason: string | null; note: string | null }>
  capture: { opencv: boolean; gstreamer: boolean }
  modes: { id: FlightMode; label: string }[]
  default_rates: VisionRates
  max_rate: number
  imgsz: number
}

export type WorkerState = 'loading' | 'off' | 'waiting' | 'running' | 'error' | 'unavailable'

export type WorkerStatus = {
  state: WorkerState
  message: string | null
  detector: string | null
  device: string | null
  target_fps: number
  actual_fps: number
  infer_ms: number | null
  infer_ms_p95: number | null
  latency_ms: number | null
  latency_ms_p95: number | null
  processed: number
  skipped: number
  errors: number
}

export type VisionSession =
  | { running: false }
  | {
      running: true
      started_at: string
      mode: FlightMode
      rates: VisionRates
      auto_issues: boolean
      follow_telemetry: boolean
      frame_source: 'server' | 'browser'
      transport: string
      source: { label: string; state: string; message: string | null }
      push_fps: number
      push_max_width: number
      workers: Record<VisionStream, WorkerStatus>
    }

export type GeoPosition = { lat: number; lon: number; alt_m: number | null; heading_deg: number | null }

export type DetectionItem = {
  id: string | null
  track_id: number | null
  category: Category
  label: string
  kind: string
  title?: string
  severity: Severity
  confidence: number
  bbox: { x: number; y: number; w: number; h: number }
  velocity: { vx: number; vy: number } | null
  hits: number
}

export type DetectionEvent = {
  type: 'detections'
  stream: VisionStream
  detector: string
  frame_seq: number
  frame_ts: string
  media_time: number | null
  frame_size: [number, number]
  infer_ms: number
  latency_ms: number
  position: GeoPosition | null
  items: DetectionItem[]
}

export type VisionAlert = {
  type: 'alert'
  stream: VisionStream
  category: Category
  title: string
  label: string
  severity: Severity
  confidence: number
  track_id: number | null
  issue_id: number | null
  frame_ts: string
  media_time: number | null
  position: GeoPosition | null
}

export type VisionStats = {
  type: 'stats'
  frames_in: number
  frames_overwritten: number
  capture_fps: number
  ingest_kbps: number | null
  frame_size: [number, number] | null
  alerts: number
  issues_created: number
  telemetry: (GeoPosition & { ts: number; flight_mode: string | null; age_s: number }) | null
  workers: Record<VisionStream, WorkerStatus>
}

export type Video = {
  id: number
  title: string
  source: 'upload' | 'url'
  source_url: string
  status: 'downloading' | 'ready' | 'error'
  progress: number | null
  error: string | null
  content_type: string
  size_bytes: number
  duration_s: number | null
  fps: number | null
  created_at: string
}
