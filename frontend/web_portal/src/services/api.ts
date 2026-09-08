import axios from 'axios';
import type { Alert, Detection, Camera, Video, Analytics, AlertStatus, Zone } from '../types';

// ─── Axios Client ─────────────────────────────────────────────────────────────

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'x-api-key': import.meta.env.VITE_IBVAP_API_KEY || 'admin-key',
  },
});

client.interceptors.request.use((config) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('ibvap_token') : null;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (r) => r,
  (err) => {
    console.error('[API]', err.response?.status, err.config?.url, err.message);
    return Promise.reject(err);
  }
);

// ─── Camera Endpoints ─────────────────────────────────────────────────────────

export const getCameras = (): Promise<Camera[]> =>
  client.get<Camera[]>('/api/cameras').then((r) => r.data);

export const getCameraById = (id: string): Promise<Camera> =>
  client.get<Camera>(`/api/cameras/${id}`).then((r) => r.data);

export const createCamera = (data: Partial<Camera>): Promise<Camera> =>
  client.post<Camera>('/api/cameras', data).then((r) => r.data);

export const updateCamera = (id: string, data: Partial<Camera>): Promise<Camera> =>
  client.put<Camera>(`/api/cameras/${id}`, data).then((r) => r.data);

export const deleteCamera = (id: string): Promise<{ status: string; message: string }> =>
  client.delete<{ status: string; message: string }>(`/api/cameras/${id}`).then((r) => r.data);

export interface StreamTestResponse {
  success: boolean;
  status: string;
  resolution?: string;
  fps?: number;
  error?: string;
}

export const testStream = (streamUrl: string, streamType: string = 'RTSP'): Promise<StreamTestResponse> =>
  client.post<StreamTestResponse>('/api/cameras/test-stream', {
    stream_url: streamUrl,
    stream_type: streamType,
  }).then((r) => r.data);

export const discoverCameras = (): Promise<{ status: string; discovered_cameras: any[]; local_ip: string; message: string }> =>
  client.post('/api/cameras/discover').then((r) => r.data);

export interface WebcamInferResponse {
  detections: Detection[];
  frame_seq: number;
  camera_id: string;
  error?: string;
}

export const inferWebcamFrame = (
  imageBase64: string,
  confThreshold: number = 0.45,
  frameSeq: number = 0,
  faceRecognitionEnabled: boolean = true,
  faceThreshold: number = 0.45,
  anprEnabled: boolean = true
): Promise<WebcamInferResponse> =>
  client
    .post<WebcamInferResponse>('/api/cameras/webcam/infer', {
      image_base64: imageBase64,
      conf_threshold: confThreshold,
      frame_seq: frameSeq,
      camera_id: 'WEBCAM-01',
      face_recognition_enabled: faceRecognitionEnabled,
      face_threshold: faceThreshold,
      anpr_enabled: anprEnabled,
    })
    .then((r) => r.data);



export const resetWebcamSession = (): Promise<{ status: string }> =>
  client.post<{ status: string }>('/api/cameras/webcam/reset').then((r) => r.data);


// ─── Alert Endpoints ──────────────────────────────────────────────────────────

export interface AlertFilters {
  status?: string;
  threat_level?: string;
  camera_id?: string;
}

export const getAlerts = (filters?: AlertFilters): Promise<Alert[]> =>
  client.get<Alert[]>('/api/alerts', { params: filters }).then((r) => r.data);

export const getAlertById = (id: string): Promise<Alert> =>
  client.get<Alert>(`/api/alerts/${id}`).then((r) => r.data);

export const createAlert = (
  data: Omit<Alert, 'id' | 'alert_id' | 'status' | 'created_at' | 'updated_at'>
): Promise<Alert> =>
  client.post<Alert>('/api/alerts', data).then((r) => r.data);

export const patchAlert = (id: string, status: AlertStatus): Promise<Alert> =>
  client.patch<Alert>(`/api/alerts/${id}`, { status }).then((r) => r.data);

// ─── Detection Endpoints ──────────────────────────────────────────────────────

export const getDetections = (
  camera_id?: string,
  video_id?: string,
  limit: number = 500
): Promise<Detection[]> =>
  client
    .get<Detection[]>('/api/detections', {
      params: {
        ...(camera_id ? { camera_id } : {}),
        ...(video_id ? { video_id } : {}),
        limit,
      },
    })
    .then((r) => r.data);

export const createDetection = (
  data: Omit<Detection, 'id'>
): Promise<Detection> =>
  client.post<Detection>('/api/detections', data).then((r) => r.data);

// ─── Video Endpoints ──────────────────────────────────────────────────────────

export const getVideos = (): Promise<Video[]> =>
  client.get<Video[]>('/api/videos').then((r) => r.data);

export const getVideoById = (id: string): Promise<Video> =>
  client.get<Video>(`/api/videos/${id}`).then((r) => r.data);

export const uploadVideo = (
  formData: FormData,
  onProgress?: (pct: number) => void
): Promise<Video> =>
  client
    .post<Video>('/api/videos/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded * 100) / e.total));
        }
      },
    })
    .then((r) => r.data);

export interface VideoAnalysisStatus {
  video_id: string;
  status: string;
  progress: number;
  current_frame: number;
  total_frames: number;
  fps: number;
  analysis_fps: number;
  duration: number;
  detections: number;
  tracks: number;
  events: number;
  error?: string | null;
}

export const getVideoAnalysisStatus = (videoId: string): Promise<VideoAnalysisStatus> =>
  client.get<VideoAnalysisStatus>(`/api/videos/${videoId}/analysis-status`).then((r) => r.data);

export const cancelVideoAnalysis = (videoId: string): Promise<{ status: string; message: string }> =>
  client.post<{ status: string; message: string }>(`/api/videos/${videoId}/cancel`).then((r) => r.data);


// ─── Analytics Endpoint ───────────────────────────────────────────────────────

export const getAnalytics = (videoId?: string, cameraId?: string): Promise<Analytics> =>
  client
    .get<Analytics>('/api/analytics', {
      params: {
        ...(videoId ? { video_id: videoId } : {}),
        ...(cameraId ? { camera_id: cameraId } : {}),
      },
    })
    .then((r) => r.data);

// ─── Zone Endpoints ───────────────────────────────────────────────────────────

export const getZones = (): Promise<Zone[]> =>
  client.get<Zone[]>('/api/zones').then((r) => r.data);

export const getZoneBySource = (sourceId: string): Promise<Zone> =>
  client.get<Zone>(`/api/zones/${sourceId}`).then((r) => r.data);

export const saveZone = (
  zone: Partial<Zone> & { source_id: string; coordinates: [number, number][] }
): Promise<Zone> =>
  client.post<Zone>('/api/zones', zone).then((r) => r.data);

export const updateZone = (
  sourceId: string,
  zone: Partial<Zone>
): Promise<Zone> =>
  client.put<Zone>(`/api/zones/${sourceId}`, zone).then((r) => r.data);

export const deleteZone = (sourceId: string): Promise<{ status: string; message: string }> =>
  client.delete<{ status: string; message: string }>(`/api/zones/${sourceId}`).then((r) => r.data);


// ─── Watchlist & Face Recognition Endpoints ───────────────────────────────────

import type { 
  WatchlistPerson, 
  TestFaceMatchResult,
  PersonPhotoGalleryResponse,
  FaceRecognitionEventResponse,
  WatchlistAuditLogResponse
} from '../types';

export const getWatchlist = (): Promise<WatchlistPerson[]> =>
  client.get<WatchlistPerson[]>('/api/watchlist').then((r) => r.data);

export const getWatchlistPersonById = (id: string): Promise<WatchlistPerson> =>
  client.get<WatchlistPerson>(`/api/watchlist/${id}`).then((r) => r.data);

export const registerWatchlistPerson = (formData: FormData): Promise<WatchlistPerson> =>
  client
    .post<WatchlistPerson>('/api/watchlist', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data);

export const addWatchlistPhoto = (personId: string, formData: FormData): Promise<any> =>
  client
    .post<any>(`/api/watchlist/${personId}/photos`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data);

export const deleteWatchlistPhoto = (personId: string, embeddingId: string): Promise<any> =>
  client.delete<any>(`/api/watchlist/${personId}/photos/${embeddingId}`).then((r) => r.data);

export const updateWatchlistPerson = (
  id: string,
  data: Partial<WatchlistPerson>
): Promise<WatchlistPerson> =>
  client.patch<WatchlistPerson>(`/api/watchlist/${id}`, data).then((r) => r.data);

export const deleteWatchlistPerson = (id: string, justification: string = "Manual deletion"): Promise<{ status: string; message: string }> =>
  client.delete<{ status: string; message: string }>(`/api/watchlist/${id}`, { params: { justification } }).then((r) => r.data);

export const testFaceMatch = (formData: FormData): Promise<TestFaceMatchResult> =>
  client
    .post<TestFaceMatchResult>('/api/watchlist/test-match', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data);

export const getFaceEvents = (params?: { person_id?: string; camera_id?: string; event_type?: string; limit?: number }): Promise<FaceRecognitionEventResponse[]> =>
  client.get<FaceRecognitionEventResponse[]>('/api/watchlist/events', { params }).then((r) => r.data);

export const getUnknownFaceClusters = (days: number = 7, minSightings: number = 2): Promise<{ clusters: any[]; total_unknown: number }> =>
  client.get<{ clusters: any[]; total_unknown: number }>('/api/watchlist/unknown-faces', { params: { days, min_sightings: minSightings } }).then((r) => r.data);

export const getAuditLog = (params?: { person_id?: string; action?: string; limit?: number }): Promise<WatchlistAuditLogResponse[]> =>
  client.get<WatchlistAuditLogResponse[]>('/api/watchlist/audit-log', { params }).then((r) => r.data);


// ─── ANPR Endpoints ───────────────────────────────────────────────────────────

import type { ANPREvent, ANPRStats, TestANPRResult } from '../types';

export const getANPREvents = (params?: {
  camera_id?: string;
  plate_text?: string;
  plate_status?: string;
  limit?: number;
}): Promise<ANPREvent[]> =>
  client.get<ANPREvent[]>('/api/anpr/events', { params }).then((r) => r.data);

export const getANPRStats = (): Promise<ANPRStats> =>
  client.get<ANPRStats>('/api/anpr/stats').then((r) => r.data);

export const testANPRPlate = (formData: FormData): Promise<TestANPRResult> =>
  client
    .post<TestANPRResult>('/api/anpr/test-recognize', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data);

// ─── Face Authentication Endpoints ───────────────────────────────────────────

import type { AuthUser, AuthResponse, RegisterWebcamPayload, LoginWebcamPayload } from '../types';

export const registerFaceWebcam = (data: RegisterWebcamPayload): Promise<AuthResponse> =>
  client.post<AuthResponse>('/api/auth/register-webcam', data).then((r) => r.data);

export const loginFaceWebcam = (data: LoginWebcamPayload): Promise<AuthResponse> =>
  client.post<AuthResponse>('/api/auth/login-webcam', data).then((r) => r.data);

export const getMe = (): Promise<AuthUser> =>
  client.get<AuthUser>('/api/auth/me').then((r) => r.data);





