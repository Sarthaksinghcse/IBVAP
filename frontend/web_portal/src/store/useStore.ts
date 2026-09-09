import { create } from 'zustand';
import type {
  Alert,
  Detection,
  Camera,
  Analytics,
  SystemStatusData,
  AlertStatus,
  Zone,
  WatchlistPerson,
} from '../types';
import * as api from '../services/api';

export interface AppSettings {
  showBoundingBoxes: boolean;
  showRestrictedZone: boolean;
  showConfidence: boolean;
  alertSound: boolean;
  voiceAlerts: boolean;
  autoAcknowledge: boolean;
  aiThreshold: number;
  loiteringThreshold: number;
  storageRetention: number;
  sectorName?: string;
  faceRecognitionEnabled: boolean;
  faceMatchThreshold: number;
  anprEnabled: boolean;
  // Acoustic alert when a person is inside a restricted zone. Read by
  // CCTVPanel; defaults to on when unset.
  personBeep?: boolean;
}



const DEFAULT_SETTINGS: AppSettings = {
  showBoundingBoxes: true,
  showRestrictedZone: true,
  showConfidence: true,
  alertSound: true,
  voiceAlerts: true,
  autoAcknowledge: false,
  aiThreshold: 30,
  loiteringThreshold: 15,
  storageRetention: 30,
  faceRecognitionEnabled: true,
  faceMatchThreshold: 45,
  anprEnabled: true,
};




const loadSettingsFromStorage = (): AppSettings => {
  try {
    const raw = localStorage.getItem('shield_settings');
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch (e) {
    console.warn('[useStore] Failed to load settings from storage:', e);
  }
  return DEFAULT_SETTINGS;
};

interface IBVAPState {
  // --- Data ---
  alerts: Alert[];
  detections: Detection[];
  cameras: Camera[];
  zones: Record<string, Zone>;
  watchlist: WatchlistPerson[];
  activeTracksBySource: Record<string, Detection[]>;
  analytics: Analytics | null;
  systemStatus: SystemStatusData;
  settings: AppSettings;


  // --- UI State & Preferences ---
  wsConnected: boolean;
  selectedCameraId: string;
  selectedAlertId: string | null;
  isMockMode: boolean;
  uploadProgress: number;
  uploadStatus: string | null;
  activeVideoUrl: string | null;
  activeVideoId: string | null;
  uploadedVideoName: string | null;
  pendingVideoBlob: string | null;
  enhancedVideoUrl: string | null;
  isLowLightVideo: boolean;
  videoViewMode: 'ENHANCED' | 'ORIGINAL';
  videoAnalysisMetrics: {
    progress: number;
    currentFrame: number;
    totalFrames: number;
    fps: number;
    detections: number;
    tracks: number;
    events: number;
    status: string;
    low_light?: boolean;
    brightness?: number;
    raw_video_url?: string | null;
    enhanced_video_url?: string | null;
  } | null;
  timeZone: string;
  timeFormat: '12h' | '24h';
  theme: 'dark' | 'light' | 'system';
  readAlertIds: string[];

  // --- Settings Action ---
  updateSetting: <K extends keyof AppSettings>(key: K, val: AppSettings[K]) => void;
  setTimeZone: (tz: string) => void;
  setTimeFormat: (fmt: '12h' | '24h') => void;
  setTheme: (theme: 'dark' | 'light' | 'system') => void;
  markAlertRead: (id: string) => void;
  markAllAlertsRead: () => void;
  setEnhancedVideoUrl: (url: string | null) => void;
  setIsLowLightVideo: (v: boolean) => void;
  setVideoViewMode: (mode: 'ENHANCED' | 'ORIGINAL') => void;
  setVideoAnalysisMetrics: (metrics: Partial<{
    progress: number;
    currentFrame: number;
    totalFrames: number;
    fps: number;
    detections: number;
    tracks: number;
    events: number;
    status: string;
    low_light?: boolean;
    brightness?: number;
    raw_video_url?: string | null;
    enhanced_video_url?: string | null;
  }> | null) => void;



  // --- Browser Camera State ---
  cameraMode: boolean;
  activeCameraStream: MediaStream | null;
  cameraLoading: boolean;
  cameraError: string | null;
  cameraResolution: string | null;
  availableCameraDevices: MediaDeviceInfo[];
  selectedCameraDeviceId: string | null;

  // --- Legacy Compatibility Aliases ---
  isWebcamActive: boolean;
  webcamStream: MediaStream | null;
  webcamError: string | null;
  webcamResolution: string | null;

  // --- Zone Actions ---
  setZones: (zones: Zone[]) => void;
  setZoneForSource: (sourceId: string, zone: Zone | null) => void;
  deleteZoneFromStore: (sourceId: string) => void;
  fetchZones: () => Promise<void>;

  // --- Watchlist Actions ---
  fetchWatchlist: () => Promise<void>;
  addWatchlistPersonToStore: (person: WatchlistPerson) => void;
  updateWatchlistPersonInStore: (id: string, partial: Partial<WatchlistPerson>) => void;
  removeWatchlistPersonFromStore: (id: string) => void;

  // --- Alert Actions ---

  setAlerts: (alerts: Alert[]) => void;
  addAlert: (alert: Alert) => void;
  updateAlertStatus: (id: string, status: AlertStatus) => void;

  // --- Detection Actions ---
  setDetections: (detections: Detection[]) => void;
  addDetection: (detection: Detection) => void;
  setActiveTracksForSource: (sourceId: string, tracks: Detection[]) => void;


  // --- Camera Actions ---
  setCameras: (cameras: Camera[]) => void;
  fetchCameras: () => Promise<void>;
  addCamera: (camera: Camera) => void;
  updateCamera: (id: string, partial: Partial<Camera>) => void;
  removeCamera: (id: string) => void;

  // --- Analytics Actions ---
  setAnalytics: (analytics: Analytics) => void;

  // --- System Actions ---
  setSystemStatus: (status: Partial<SystemStatusData>) => void;
  setWsConnected: (connected: boolean) => void;

  // --- UI Actions ---
  setSelectedCamera: (id: string) => void;
  setSelectedAlert: (id: string | null) => void;
  setUploadProgress: (progress: number) => void;
  setUploadStatus: (status: string | null) => void;
  setActiveVideoUrl: (url: string | null) => void;
  setActiveVideoId: (id: string | null) => void;
  setUploadedVideoName: (name: string | null) => void;
  setPendingVideoBlob: (url: string | null) => void;

  // --- Browser Camera Actions ---
  setCameraMode: (mode: boolean) => void;
  startDeviceCamera: (deviceId?: string) => Promise<boolean>;
  stopDeviceCamera: () => void;
  switchCameraDevice: (deviceId: string) => Promise<boolean>;
  setCameraError: (err: string | null) => void;
  enumerateCameraDevices: () => Promise<MediaDeviceInfo[]>;

  // --- Legacy Webcam Aliases ---
  startWebcam: () => Promise<boolean>;
  stopWebcam: () => void;
  setWebcamError: (err: string | null) => void;
}

export const useStore = create<IBVAPState>((set, get) => ({
  // --- Initial State ---
  alerts: [],
  detections: [],
  cameras: [],
  zones: {},
  watchlist: [],
  activeTracksBySource: {},
  analytics: null,



  systemStatus: {
    backend_status: 'OFFLINE',
    ai_engine_status: 'STOPPED',
    websocket_connected: false,
    database_status: 'OK',
    storage_used_mb: 0,
    storage_total_mb: 10240,
    uptime_seconds: 0,
    fps: 0,
    processing_time_ms: 0,
    model_name: 'YOLOv8 + DeepSORT',
    alerts_today: 0,
  },
  settings: loadSettingsFromStorage(),
  wsConnected: false,
  selectedCameraId: '',
  selectedAlertId: null,
  isMockMode: import.meta.env.VITE_USE_MOCK === 'true',
  uploadProgress: 0,
  uploadStatus: null,
  activeVideoUrl: null,
  activeVideoId: (() => {
    try { return localStorage.getItem('shield_active_video_id') || null; } catch { return null; }
  })(),
  uploadedVideoName: (() => {
    try { return localStorage.getItem('shield_uploaded_video_name') || null; } catch { return null; }
  })(),
  pendingVideoBlob: null,
  enhancedVideoUrl: null,
  isLowLightVideo: false,
  videoViewMode: 'ENHANCED',
  videoAnalysisMetrics: null,

  setEnhancedVideoUrl: (enhancedVideoUrl) => set({ enhancedVideoUrl }),
  setIsLowLightVideo: (isLowLightVideo) => set({ isLowLightVideo }),
  setVideoViewMode: (videoViewMode) => set({ videoViewMode }),

  setVideoAnalysisMetrics: (metrics) => {
    set((state) => {
      const low_light = metrics?.low_light ?? state.videoAnalysisMetrics?.low_light ?? false;
      const enhanced_url = metrics?.enhanced_video_url ?? state.videoAnalysisMetrics?.enhanced_video_url ?? null;
      return {
        isLowLightVideo: low_light,
        enhancedVideoUrl: enhanced_url ?? state.enhancedVideoUrl,
        videoAnalysisMetrics: metrics
          ? {
              progress: metrics.progress ?? state.videoAnalysisMetrics?.progress ?? 0,
              currentFrame: metrics.currentFrame ?? state.videoAnalysisMetrics?.currentFrame ?? 0,
              totalFrames: metrics.totalFrames ?? state.videoAnalysisMetrics?.totalFrames ?? 0,
              fps: metrics.fps ?? state.videoAnalysisMetrics?.fps ?? 25.0,
              detections: metrics.detections ?? state.videoAnalysisMetrics?.detections ?? 0,
              tracks: metrics.tracks ?? state.videoAnalysisMetrics?.tracks ?? 0,
              events: metrics.events ?? state.videoAnalysisMetrics?.events ?? 0,
              status: metrics.status ?? state.videoAnalysisMetrics?.status ?? 'PROCESSING',
              low_light: low_light,
              brightness: metrics.brightness ?? state.videoAnalysisMetrics?.brightness ?? 0.0,
              raw_video_url: metrics.raw_video_url ?? state.videoAnalysisMetrics?.raw_video_url ?? null,
              enhanced_video_url: enhanced_url,
            }
          : null,
      };
    });
  },

  timeZone: (() => {
    try { return localStorage.getItem('shield_timezone') || 'SYSTEM'; } catch { return 'SYSTEM'; }
  })(),
  timeFormat: (() => {
    try { return (localStorage.getItem('shield_timeformat') as '12h' | '24h') || '24h'; } catch { return '24h'; }
  })(),
  theme: (() => {
    try { return (localStorage.getItem('shield_theme') as 'dark' | 'light' | 'system') || 'dark'; } catch { return 'dark'; }
  })(),
  readAlertIds: (() => {
    try { return JSON.parse(localStorage.getItem('shield_read_alerts') || '[]'); } catch { return []; }
  })(),

  updateSetting: (key, val) => {
    set((state) => {
      const next = { ...state.settings, [key]: val };
      try {
        localStorage.setItem('shield_settings', JSON.stringify(next));
      } catch (e) {
        console.warn('[useStore] Failed to save settings to storage:', e);
      }
      return { settings: next };
    });
  },

  setTimeZone: (tz) => {
    try { localStorage.setItem('shield_timezone', tz); } catch {}
    set({ timeZone: tz });
  },

  setTimeFormat: (fmt) => {
    try { localStorage.setItem('shield_timeformat', fmt); } catch {}
    set({ timeFormat: fmt });
  },

  setTheme: (theme) => {
    try {
      localStorage.setItem('shield_theme', theme);
      if (theme === 'light') {
        document.documentElement.classList.add('light');
        document.documentElement.classList.remove('dark');
        document.documentElement.setAttribute('data-theme', 'light');
      } else {
        document.documentElement.classList.add('dark');
        document.documentElement.classList.remove('light');
        document.documentElement.setAttribute('data-theme', 'dark');
      }
    } catch {}
    set({ theme });
  },


  markAlertRead: (id) => {
    set((state) => {
      if (state.readAlertIds.includes(id)) return state;
      const next = [id, ...state.readAlertIds].slice(0, 500);
      try { localStorage.setItem('shield_read_alerts', JSON.stringify(next)); } catch {}
      return { readAlertIds: next };
    });
  },

  markAllAlertsRead: () => {
    set((state) => {
      const allIds = state.alerts.map((a) => a.id);
      try { localStorage.setItem('shield_read_alerts', JSON.stringify(allIds)); } catch {}
      return { readAlertIds: allIds };
    });
  },


  // Browser Camera State
  cameraMode: false,
  activeCameraStream: null,
  cameraLoading: false,
  cameraError: null,
  cameraResolution: null,
  availableCameraDevices: [],
  selectedCameraDeviceId: null,

  // Legacy Aliases
  isWebcamActive: false,
  webcamStream: null,
  webcamError: null,
  webcamResolution: null,

  // --- Zone Actions ---
  setZones: (zoneList) => {
    const zoneMap: Record<string, Zone> = {};
    for (const z of zoneList) {
      zoneMap[z.source_id] = z;
    }
    set({ zones: zoneMap });
  },

  setZoneForSource: (sourceId, zone) => {
    set((state) => {
      const next = { ...state.zones };
      if (zone) {
        next[sourceId] = zone;
      } else {
        delete next[sourceId];
      }
      return { zones: next };
    });
  },

  deleteZoneFromStore: (sourceId) => {
    set((state) => {
      const next = { ...state.zones };
      delete next[sourceId];
      return { zones: next };
    });
  },

  fetchZones: async () => {
    try {
      const data = await api.getZones();
      const zoneMap: Record<string, Zone> = {};
      for (const z of data) {
        zoneMap[z.source_id] = z;
      }
      set({ zones: zoneMap });
    } catch (e) {
      console.warn('[useStore] Failed to fetch zones:', e);
    }
  },

  // --- Watchlist Actions ---
  fetchWatchlist: async () => {
    try {
      const data = await api.getWatchlist();
      set({ watchlist: data });
    } catch (e) {
      console.warn('[useStore] Failed to fetch watchlist:', e);
    }
  },

  addWatchlistPersonToStore: (person) => {
    set((s) => ({ watchlist: [person, ...s.watchlist.filter((p) => p.id !== person.id)] }));
  },

  updateWatchlistPersonInStore: (id, partial) => {
    set((s) => ({
      watchlist: s.watchlist.map((p) => (p.id === id ? { ...p, ...partial } : p)),
    }));
  },

  removeWatchlistPersonFromStore: (id) => {
    set((s) => ({
      watchlist: s.watchlist.filter((p) => p.id !== id),
    }));
  },

  // --- Alert Actions ---
  setAlerts: (alerts) => set({ alerts }),


  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts.filter((a) => a.id !== alert.id)].slice(0, 200),
    })),
  updateAlertStatus: (id, status) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.id === id
          ? { ...a, status, updated_at: new Date().toISOString() }
          : a
      ),
    })),

  // --- Detection Actions ---
  setDetections: (detections) => set({ detections: (detections || []).slice(0, 500) }),
  addDetection: (detection) =>
    set((state) => ({
      detections: [detection, ...state.detections].slice(0, 500),
    })),
  setActiveTracksForSource: (sourceId, tracks) =>
    set((state) => ({
      activeTracksBySource: {
        ...state.activeTracksBySource,
        [sourceId]: tracks,
      },
    })),


  // --- Camera Actions ---
  setCameras: (cameras) => {
    set((state) => ({
      cameras,
      selectedCameraId: state.selectedCameraId || (cameras.length > 0 ? cameras[0].id : ''),
    }));
  },
  fetchCameras: async () => {
    try {
      const cams = await api.getCameras();
      const currentSelected = get().selectedCameraId;
      const targetCamId = currentSelected || (cams.length > 0 ? cams[0].id : '');
      set({
        cameras: cams,
        selectedCameraId: targetCamId,
      });
      if (targetCamId) {
        api.getDetections(targetCamId, undefined, 100)
          .then((dets) => {
            if (dets && dets.length > 0) {
              set((state) => {
                const existingIds = new Set(state.detections.map((d) => d.id));
                const newDets = dets.filter((d) => !existingIds.has(d.id));
                return { detections: [...newDets, ...state.detections].slice(0, 500) };
              });
            }
          })
          .catch(() => {});
      }
    } catch (e) {
      console.warn('[useStore] Failed to fetch cameras:', e);
    }
  },
  addCamera: (camera) =>
    set((state) => {
      const next = [...state.cameras.filter((c) => c.id !== camera.id), camera];
      return {
        cameras: next,
        selectedCameraId: state.selectedCameraId || camera.id,
      };
    }),
  updateCamera: (id, partial) =>
    set((state) => ({
      cameras: state.cameras.map((c) => (c.id === id ? { ...c, ...partial } : c)),
    })),
  removeCamera: (id) =>
    set((state) => {
      const next = state.cameras.filter((c) => c.id !== id);
      return {
        cameras: next,
        selectedCameraId: state.selectedCameraId === id ? (next.length > 0 ? next[0].id : '') : state.selectedCameraId,
      };
    }),


  // --- Analytics Actions ---
  setAnalytics: (analytics) => set({ analytics }),

  // --- System Actions ---
  setSystemStatus: (status) =>
    set((state) => ({
      systemStatus: { ...state.systemStatus, ...status },
    })),
  setWsConnected: (wsConnected) =>
    set({ wsConnected }),

  // --- UI Actions ---
  setSelectedCamera: (selectedCameraId) => {
    set({ selectedCameraId });
    if (selectedCameraId) {
      api.getDetections(selectedCameraId, undefined, 100)
        .then((dets) => {
          if (dets && dets.length > 0) {
            set((state) => {
              const existingIds = new Set(state.detections.map((d) => d.id));
              const newDets = dets.filter((d) => !existingIds.has(d.id));
              return { detections: [...newDets, ...state.detections].slice(0, 500) };
            });
          }
        })
        .catch(() => {});
    }
  },
  setSelectedAlert: (selectedAlertId) => set({ selectedAlertId }),
  setUploadProgress: (uploadProgress) => set({ uploadProgress }),
  setUploadStatus: (uploadStatus) => set({ uploadStatus }),
  setActiveVideoUrl: (activeVideoUrl) => set({ activeVideoUrl }),
  setActiveVideoId: (activeVideoId) => {
    try {
      if (activeVideoId) localStorage.setItem('shield_active_video_id', activeVideoId);
      else localStorage.removeItem('shield_active_video_id');
    } catch {}
    set({ activeVideoId });
  },
  setUploadedVideoName: (uploadedVideoName) => {
    try {
      if (uploadedVideoName) localStorage.setItem('shield_uploaded_video_name', uploadedVideoName);
      else localStorage.removeItem('shield_uploaded_video_name');
    } catch {}
    set({ uploadedVideoName });
  },
  setPendingVideoBlob: (pendingVideoBlob) => set({ pendingVideoBlob }),

  // --- Browser Camera Actions ---
  setCameraMode: (cameraMode) => set({ cameraMode }),

  enumerateCameraDevices: async () => {
    if (typeof window === 'undefined' || !navigator.mediaDevices?.enumerateDevices) {
      return [];
    }
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices.filter((d) => d.kind === 'videoinput');
      set({ availableCameraDevices: videoDevices });
      return videoDevices;
    } catch (e) {
      console.warn('[Camera] Failed to enumerate devices:', e);
      return [];
    }
  },

  startDeviceCamera: async (deviceId?: string) => {
    if (typeof window === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      const err = 'Camera access is not supported in this browser environment.';
      set({
        cameraError: err,
        cameraLoading: false,
        cameraMode: true,
        activeCameraStream: null,
        webcamError: err,
        isWebcamActive: false,
        webcamStream: null,
      });
      return false;
    }

    set({ cameraLoading: true, cameraError: null, webcamError: null, cameraMode: true });

    try {
      // Stop previous stream tracks cleanly
      const currentStream = get().activeCameraStream || get().webcamStream;
      if (currentStream) {
        currentStream.getTracks().forEach((t) => {
          try {
            t.stop();
          } catch (err) {
            console.warn('[Camera] Error stopping previous track:', err);
          }
        });
      }

      const constraints: MediaStreamConstraints = {
        video: deviceId
          ? { deviceId: { exact: deviceId } }
          : { width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      };

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (firstErr: any) {
        if (deviceId || constraints.video !== true) {
          // Fallback to minimal video constraints if exact or resolution constraints fail
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        } else {
          throw firstErr;
        }
      }

      const videoTrack = stream.getVideoTracks()[0];
      const settings = videoTrack?.getSettings?.();
      const res = settings?.width && settings?.height ? `${settings.width}x${settings.height}` : '1920x1080';
      const activeDeviceId = settings?.deviceId || deviceId || null;

      // Enumerate devices once permission has been granted
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter((d) => d.kind === 'videoinput');
        set({ availableCameraDevices: videoDevices });
      } catch (e) {
        console.warn('[Camera] Error listing devices:', e);
      }

      set({
        cameraMode: true,
        activeCameraStream: stream,
        cameraLoading: false,
        cameraError: null,
        cameraResolution: res,
        selectedCameraDeviceId: activeDeviceId,
        // Legacy
        isWebcamActive: true,
        webcamStream: stream,
        webcamError: null,
        webcamResolution: res,
      });
      return true;
    } catch (err: any) {
      console.warn('[Camera] Failed to acquire stream:', err);
      let errorMsg = 'Failed to connect to camera device.';
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        errorMsg = 'Camera permission denied. Please allow camera access in your browser settings.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        errorMsg = 'Camera unavailable: No camera device was found on this system.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        errorMsg = 'Camera unavailable: Device is currently in use by another application or tab.';
      } else if (err.name === 'OverconstrainedError') {
        errorMsg = 'Camera unavailable: Requested video resolution or device is not supported.';
      }

      set({
        cameraMode: true,
        activeCameraStream: null,
        cameraLoading: false,
        cameraError: errorMsg,
        // Legacy
        isWebcamActive: false,
        webcamStream: null,
        webcamError: errorMsg,
      });
      return false;
    }
  },

  stopDeviceCamera: () => {
    const stream = get().activeCameraStream || get().webcamStream;
    if (stream) {
      stream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch (e) {
          console.warn('[Camera] Error stopping track:', e);
        }
      });
    }
    set({
      activeCameraStream: null,
      cameraLoading: false,
      cameraError: null,
      cameraResolution: null,
      // Legacy
      webcamStream: null,
      isWebcamActive: false,
      webcamError: null,
      webcamResolution: null,
    });
  },

  switchCameraDevice: async (deviceId: string) => {
    set({ selectedCameraDeviceId: deviceId });
    return get().startDeviceCamera(deviceId);
  },

  setCameraError: (cameraError) => set({ cameraError, webcamError: cameraError }),

  // Legacy wrappers
  startWebcam: async () => get().startDeviceCamera(),
  stopWebcam: () => get().stopDeviceCamera(),
  setWebcamError: (err) => set({ webcamError: err, cameraError: err }),
}));

// ─── Camera Selector Helpers ──────────────────────────────────────────────────

export const isWebcamStreamConnected = (
  isWebcamActive: boolean,
  activeCameraStream: MediaStream | null
): boolean => {
  return Boolean(
    isWebcamActive &&
    activeCameraStream &&
    activeCameraStream.active &&
    activeCameraStream.getVideoTracks().some((t) => t.readyState === 'live')
  );
};

export const getOnlineCamerasCount = (
  cameras: Camera[],
  isWebcamActive: boolean,
  activeCameraStream: MediaStream | null
): number => {
  const webcamConnected = isWebcamStreamConnected(isWebcamActive, activeCameraStream) ? 1 : 0;
  const onlineCctvCount = cameras.filter((c) => c.status === 'ONLINE').length;
  return onlineCctvCount + webcamConnected;
};

export const getActiveCamerasCount = (
  cameras: Camera[],
  isWebcamActive: boolean,
  activeCameraStream: MediaStream | null
): number => {
  const webcamConnected = isWebcamStreamConnected(isWebcamActive, activeCameraStream) ? 1 : 0;
  // A PLAYBACK source serves a pre-analysed recording, so its AI loop is
  // deliberately stopped. It is still an online feed delivering analysed video
  // and belongs in this count.
  const onlineAiCctvCount = cameras.filter(
    (c) => c.status === 'ONLINE' && (c.ai_status === 'RUNNING' || c.source_type === 'PLAYBACK')
  ).length;
  return onlineAiCctvCount + webcamConnected;
};

export const getTotalCamerasCount = (
  cameras: Camera[],
  isWebcamActive: boolean,
  activeCameraStream: MediaStream | null
): number => {
  const webcamConnected = isWebcamStreamConnected(isWebcamActive, activeCameraStream) ? 1 : 0;
  return cameras.length + webcamConnected;
};

