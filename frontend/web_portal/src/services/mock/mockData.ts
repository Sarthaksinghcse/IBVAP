import type { Alert, Camera, Detection, Analytics, SystemStatusData } from '../../types';

// ─── Configured Camera Definitions (Templates) ─────────────────────────────────

export const MOCK_CAMERAS: Camera[] = [];


// ─── Real Event Memory Storage (Starts Empty) ──────────────────────────────────

export const MOCK_ALERTS: Alert[] = [];

export const MOCK_DETECTIONS: Detection[] = [];

export const MOCK_ANALYTICS: Analytics = {
  total_detections: 0,
  total_alerts: 0,
  people_count: 0,
  vehicle_count: 0,
  loitering_count: 0,
  intrusion_count: 0,
  cameras_online: 0,
  cameras_total: 7,
  ai_engine_fps: 0.0,
  processing_time_ms: 0,
  threat_breakdown: { critical: 0, high: 0, medium: 0, low: 0, none: 0 },
  recent_events: [],
};

export const MOCK_SYSTEM_STATUS: SystemStatusData = {
  backend_status: 'ONLINE',
  ai_engine_status: 'STOPPED',
  websocket_connected: true,
  database_status: 'OK',
  storage_used_mb: 2048,
  storage_total_mb: 10240,
  uptime_seconds: 86400,
  fps: 0.0,
  processing_time_ms: 0,
  model_name: 'YOLOv8 + DeepSORT',
  alerts_today: 0,
};

export const MOCK_CHART_DATA = Array.from({ length: 24 }, (_, i) => {
  const hour = (new Date().getHours() - 23 + i + 24) % 24;
  return {
    time: `${hour.toString().padStart(2, '0')}:00`,
    people: 0,
    vehicles: 0,
    alerts: 0,
  };
});

export const MOCK_CAMERA_ALERTS: { camera: string; count: number }[] = [];

