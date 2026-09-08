// ─── Enums / Union Types ─────────────────────────────────────────────────────

export type ThreatLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE';

export type AlertStatus =
  | 'NEW'
  | 'ACKNOWLEDGED'
  | 'UNDER_INVESTIGATION'
  | 'RESOLVED';

export type CameraStatus = 'ONLINE' | 'OFFLINE' | 'MAINTENANCE' | 'ERROR';


export type AIStatus = 'RUNNING' | 'STOPPED' | 'ERROR';

export type VideoStatus =
  | 'READY'
  | 'UPLOADING'
  | 'PROCESSING'
  | 'AI_ANALYZING'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'ERROR';

export type EventType =
  | 'ZONE_INTRUSION'
  | 'LOITERING'
  | 'PERSON_DETECTED'
  | 'VEHICLE_DETECTED'
  | 'CAR_DETECTED'
  | 'BICYCLE_DETECTED'
  | 'MOTORCYCLE_DETECTED'
  | 'BUS_DETECTED'
  | 'TRUCK_DETECTED'
  | 'SUSPICIOUS_ACTIVITY'
  | 'PERSON_TRACKED'
  | 'VEHICLE_TRACKED'
  | 'OBJECT_TRACKED'
  | 'THREAT_CORRELATION'
  | 'THREAT_ESCALATION'
  | 'WATCHLIST_MATCH'
  | 'UNKNOWN_FACE'
  | 'FACE_DETECTED'
  | 'PLATE_DETECTED'
  | 'UNREADABLE_PLATE'
  | 'WATCHLIST_PLATE_MATCH';

export type ObjectType = 'PERSON' | 'VEHICLE' | 'ANIMAL' | 'UNKNOWN';

// ─── Face Recognition Models ──────────────────────────────────────────────────

export interface FaceMatch {
  is_match: boolean;
  person_id?: string;
  person_name?: string;
  identifier?: string;
  threat_priority?: string;
  similarity: number; // 0–100%
  cosine_score?: number;
}

export interface WatchlistPerson {
  id: string;
  name: string;
  identifier?: string | null;
  notes?: string | null;
  threat_priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  is_active: boolean;
  photo_path?: string | null;
  embeddings_count: number;
  created_at: string;
  updated_at: string;
}

export interface TestFaceMatchResult {
  face_detected: boolean;
  match_found: boolean;
  person_id?: string;
  person_name?: string;
  similarity: number;
  cosine_score: number;
  threshold_used: number;
  message: string;
}

// ─── Data Models ─────────────────────────────────────────────────────────────

export interface BoundingBox {
  x: number; // % of frame width
  y: number; // % of frame height
  w: number; // % of frame width
  h: number; // % of frame height
}

export type CameraSourceType = 'CCTV' | 'PHONE' | 'WEBCAM';

export interface Camera {
  id: string;
  name: string;
  location: string;
  source_type?: CameraSourceType;
  stream_url?: string;
  stream_type?: string;
  status: CameraStatus;
  ai_status: AIStatus;
  last_activity: string; // ISO timestamp
  created_at?: string;
  fps?: number;
  resolution?: string;
}


export interface ANPRPlateInfo {
  plate_detected: boolean;
  plate_text?: string | null;
  plate_confidence?: number | null;
  plate_status: 'READABLE' | 'UNREADABLE' | 'UNCERTAIN' | 'NOT_DETECTED';
  plate_bbox?: BoundingBox | null;
  vehicle_type?: string;
}

export interface Detection {
  id: string;
  camera_id: string;
  video_id?: string;
  object_type: ObjectType;
  object_id: string;
  confidence: number; // 0–100
  zone?: string;
  event_type: EventType;
  bbox: BoundingBox;
  timestamp: string;
  is_in_restricted_zone?: boolean;
  loitering_duration?: number; // seconds
  face_match?: FaceMatch | null;
  plate_info?: ANPRPlateInfo | null;
  // Video-relative frame identity — set only for uploaded-video detections
  frame_index?: number;      // 0-based frame counter
  video_time_sec?: number;   // frame_index / source_fps  (ground-truth video time)
}


export interface Alert {
  id: string;
  alert_id: string;
  camera_id: string;
  video_id?: string;
  event_type: EventType;
  object_type: ObjectType;
  object_id: string;
  threat_level: ThreatLevel;
  reason: string;
  confidence?: number;
  bbox?: BoundingBox;
  status: AlertStatus;
  snapshot_path?: string;
  created_at: string;
  updated_at: string;
}


export interface Video {
  id: string;
  filename: string;
  camera_id?: string;
  status: VideoStatus;
  file_path?: string;
  file_size?: number;
  duration?: number;
  created_at: string;
}

export interface Zone {
  id: string;
  source_id: string;
  source_type: 'CAMERA' | 'WEBCAM' | 'VIDEO';
  name: string;
  coordinates: [number, number][]; // [[x, y], ...] in % 0-100
  enabled: boolean;
  zone_type: 'RESTRICTED' | 'EXCLUSION' | 'BUFFER';
  created_at?: string;
  updated_at?: string;
}


export interface ThreatBreakdown {
  critical: number;
  high: number;
  medium: number;
  low: number;
  none: number;
}

export interface Analytics {
  total_detections: number;
  total_alerts: number;
  people_count: number;
  vehicle_count: number;
  loitering_count: number;
  intrusion_count: number;
  cameras_online: number;
  cameras_total: number;
  ai_engine_fps: number;
  processing_time_ms: number;
  threat_breakdown: ThreatBreakdown;
  recent_events: Detection[];
}

export interface SystemStatusData {
  backend_status: 'ONLINE' | 'OFFLINE';
  ai_engine_status: AIStatus;
  websocket_connected: boolean;
  database_status: 'OK' | 'ERROR';
  storage_used_mb: number;
  storage_total_mb: number;
  uptime_seconds: number;
  fps: number;
  processing_time_ms: number;
  model_name: string;
  alerts_today: number;
}

// ─── WebSocket Message ────────────────────────────────────────────────────────

export interface WSMessage {
  type: 'ALERT' | 'ALERT_UPDATE' | 'DETECTION' | 'SYSTEM' | 'VIDEO_PROGRESS' | 'VIDEO_STATUS';
  data: any;
  timestamp?: string;
}



// ─── UI Helper Types ──────────────────────────────────────────────────────────

export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: string;
  badge?: number;
}

export interface AppSettings {
  showBoundingBoxes: boolean;
  showRestrictedZone: boolean;
  showConfidence: boolean;
  alertSound: boolean;
  voiceAlerts: boolean;
  personBeep?: boolean;
  autoAcknowledge: boolean;
  aiThreshold: number;
  loiteringThreshold: number;
  storageRetention: number;
  sectorName?: string;
  faceRecognitionEnabled?: boolean;
  faceMatchThreshold?: number; // 30-80%
  anprEnabled?: boolean;
}

export interface ANPREvent {
  id: string;
  camera_id?: string | null;
  video_id?: string | null;
  vehicle_track_id: number;
  vehicle_type: string;
  plate_text?: string | null;
  plate_confidence?: number | null;
  plate_status: 'READABLE' | 'UNREADABLE' | 'UNCERTAIN' | 'NOT_DETECTED';
  video_time_sec?: number | null;
  snapshot_path?: string | null;
  timestamp: string;
  created_at: string;
}

export interface ANPRStats {
  total_vehicles_tracked: number;
  total_plates_detected: number;
  readable_plates_count: number;
  unreadable_plates_count: number;
  unique_plates: string[];
}

export interface TestANPRResult {
  plate_detected: boolean;
  plate_text?: string | null;
  plate_confidence?: number | null;
  plate_status: string;
  cleaned_text?: string | null;
  message: string;
}





