import { useState, useRef, useMemo, useEffect, useCallback } from 'react';
import { Loader2, Camera, Video, VideoOff, AlertCircle, RotateCcw, ArrowLeft, ShieldAlert, LayoutGrid, Maximize2, Plus, WifiOff, Usb } from 'lucide-react';
import { useStore } from '../../store/useStore';
import { LiveBadge } from '../ui/Badge';
import { ZoneEditorModal } from '../monitoring/ZoneEditorModal';
import { AddCameraModal } from '../cameras/AddCameraModal';
import { MultiCameraGrid } from './MultiCameraGrid';
import * as api from '../../services/api';
import type { Detection, Zone, CameraSourceType } from '../../types';



// BoundingBox
function BoundingBox({ det, showConfidence = true }: { det: Detection; showConfidence?: boolean }) {
  const isIntrusion = det.is_in_restricted_zone;
  const isLoitering = det.loitering_duration && det.loitering_duration > 0;
  const isVehicle   = ['VEHICLE', 'CAR', 'TRUCK', 'BUS', 'MOTORCYCLE', 'BICYCLE'].includes(det.object_type);
  const isAnimal    = ['ANIMAL', 'DOG', 'CAT', 'BIRD', 'HORSE', 'COW', 'SHEEP'].includes(det.object_type);
  const faceMatch   = det.face_match;
  const isWatchlist = Boolean(faceMatch && faceMatch.is_match);
  const isUnknownFace = Boolean(faceMatch && !faceMatch.is_match && faceMatch.person_name === 'UNKNOWN');
  const plateInfo   = det.plate_info;

  const boxClass    = isWatchlist ? 'border-red-600 animate-pulse ring-2 ring-red-500' : isIntrusion ? 'bbox-intrusion' : isLoitering ? 'bbox-loitering' : isVehicle ? 'bbox-vehicle' : isAnimal ? 'border-amber-400 bg-amber-500/10' : 'bbox-person';
  const labelBg     = isWatchlist ? 'bg-red-700' : isIntrusion ? 'bg-red-500' : isLoitering ? 'bg-orange-500' : isVehicle ? 'bg-blue-600' : isAnimal ? 'bg-amber-600' : 'bg-green-600';
  const cornerColor = isWatchlist ? '#dc2626' : isIntrusion ? '#ef4444' : isVehicle ? '#3b82f6' : isAnimal ? '#d97706' : '#22c55e';

  return (
    <div className={`absolute border-2 ${boxClass} pointer-events-none`} style={{ left: `${det.bbox.x}%`, top: `${det.bbox.y}%`, width: `${det.bbox.w}%`, height: `${det.bbox.h}%` }}>
      {[{top:-1,left:-1,borderTop:`2px solid ${cornerColor}`,borderLeft:`2px solid ${cornerColor}`},{top:-1,right:-1,borderTop:`2px solid ${cornerColor}`,borderRight:`2px solid ${cornerColor}`},{bottom:-1,left:-1,borderBottom:`2px solid ${cornerColor}`,borderLeft:`2px solid ${cornerColor}`},{bottom:-1,right:-1,borderBottom:`2px solid ${cornerColor}`,borderRight:`2px solid ${cornerColor}`}].map((s,i)=>(<span key={i} className="absolute w-2 h-2" style={s}/>))}
      <div className={`absolute -top-5 left-0 ${labelBg} text-white text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-sm whitespace-nowrap flex items-center gap-1 shadow-md`}>
        <span>{isWatchlist && faceMatch ? `🔴 WATCHLIST: ${faceMatch.person_name}` : (det.object_id || 'OBJECT').toUpperCase()}</span>
        {showConfidence && (
          <>
            <span className="opacity-75">—</span>
            <span>{isWatchlist && faceMatch ? `${faceMatch.similarity.toFixed(1)}% match` : `${typeof det.confidence==='number'?det.confidence.toFixed(1):det.confidence}%`}</span>
          </>
        )}
        {isIntrusion && <span className="ml-1 bg-red-700/90 px-1 rounded-xs">🚨 [RESTRICTED]</span>}
        {isUnknownFace && !isWatchlist && <span className="ml-1 bg-slate-700/80 px-1 rounded-xs text-[8px]">👤 FACE: UNKNOWN</span>}
        {isVehicle && plateInfo && plateInfo.plate_status === 'READABLE' && plateInfo.plate_text && (
          <span className="ml-1 bg-white text-slate-900 font-bold px-1.5 py-0.2 rounded-xs text-[8px] flex items-center gap-1 shadow-sm border border-slate-300">
            <span className="bg-blue-700 text-white text-[7px] px-0.5 rounded-xs">IND</span>
            <span>PLATE: {plateInfo.plate_text}</span>
            {plateInfo.plate_confidence != null && <span className="text-slate-600 font-medium">• OCR: {plateInfo.plate_confidence.toFixed(1)}%</span>}
          </span>
        )}
        {isVehicle && plateInfo && plateInfo.plate_status === 'READING' && (
          <span className="ml-1 bg-sky-500/20 text-sky-300 border border-sky-500/50 px-1 rounded-xs text-[8px] flex items-center gap-1 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-ping" />
            <span>Plate: Reading...</span>
          </span>
        )}
        {isVehicle && plateInfo && plateInfo.plate_status === 'UNREADABLE' && (
          <span className="ml-1 bg-amber-500/20 text-amber-300 border border-amber-500/50 px-1 rounded-xs text-[8px]">
            🏷️ PLATE: UNREADABLE
          </span>
        )}
      </div>
      {isLoitering && (<div className="absolute -bottom-5 left-0 bg-orange-500 text-white text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-sm whitespace-nowrap shadow-md">LOITERING • {det.loitering_duration}s</div>)}

      {/* Real Localized License Plate Bounding Box with Genuine Number & OCR Confidence */}
      {isVehicle && plateInfo?.plate_bbox && det.bbox.w > 0 && det.bbox.h > 0 && (
        <div
          className="absolute border-2 border-emerald-400 bg-emerald-500/20 pointer-events-none rounded-xs shadow-[0_0_8px_rgba(52,211,153,0.8)] z-10"
          style={{
            left: `${Math.max(0, ((plateInfo.plate_bbox.x - det.bbox.x) / det.bbox.w) * 100)}%`,
            top: `${Math.max(0, ((plateInfo.plate_bbox.y - det.bbox.y) / det.bbox.h) * 100)}%`,
            width: `${Math.min(100, (plateInfo.plate_bbox.w / det.bbox.w) * 100)}%`,
            height: `${Math.min(100, (plateInfo.plate_bbox.h / det.bbox.h) * 100)}%`,
          }}
        >
          <div className="absolute -bottom-5 left-0 flex items-center gap-1 bg-slate-950/90 backdrop-blur-xs border border-emerald-500/60 text-white text-[8px] font-mono font-bold px-1.5 py-0.5 rounded shadow-lg whitespace-nowrap">
            {plateInfo.plate_status === 'READABLE' && plateInfo.plate_text ? (
              <>
                <span className="bg-blue-700 text-white text-[7px] px-0.5 rounded-xs">IND</span>
                <span className="text-emerald-300 font-bold">PLATE: {plateInfo.plate_text}</span>
                {plateInfo.plate_confidence != null && (
                  <span className="text-slate-300 text-[7px]">OCR: {plateInfo.plate_confidence.toFixed(1)}%</span>
                )}
              </>
            ) : plateInfo.plate_status === 'READING' ? (
              <span className="text-sky-300 text-[7px] flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-sky-400 animate-ping" />
                Plate: Reading...
              </span>
            ) : (
              <span className="text-amber-300 text-[7px]">PLATE: UNREADABLE</span>
            )}
          </div>
        </div>
      )}
    </div>
  );

}




function RestrictedZoneOverlay({ zone }: { zone?: Zone }) {
  if (!zone || !zone.coordinates || zone.coordinates.length < 3 || !zone.enabled) return null;
  const pointsStr = zone.coordinates.map(([x, y]) => `${x},${y}`).join(' ');

  const minX = Math.min(...zone.coordinates.map((c) => c[0]));
  const minY = Math.min(...zone.coordinates.map((c) => c[1]));

  return (
    <div className="absolute inset-0 pointer-events-none z-15">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
        <polygon
          points={pointsStr}
          fill="rgba(239, 68, 68, 0.16)"
          stroke="#ef4444"
          strokeWidth="0.8"
          strokeDasharray="2.5,1.5"
        />
      </svg>
      <div
        className="absolute bg-red-500/90 text-white text-[8px] font-mono font-bold px-1.5 py-0.5 rounded-sm uppercase tracking-wide shadow-md flex items-center gap-1 pointer-events-none"
        style={{ left: `${Math.max(1, Math.min(80, minX))}%`, top: `${Math.max(1, Math.min(90, minY))}%` }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
        <span>{zone.name || 'Restricted Zone A'}</span>
      </div>
    </div>
  );
}

function CameraThumbnail({ cameraId, location, isActive, isOnline, onClick }: { cameraId:string;location:string;isActive:boolean;isOnline:boolean;onClick:()=>void }) {
  return (
    <div onClick={onClick} className={`flex-shrink-0 w-24 rounded-xl cursor-pointer border transition-all duration-150 ${isActive?'border-[#22c55e] bg-[#13271d] light:bg-[#ecfdf5] light:border-[#86efac]':'border-[#272b37] light:border-[#d3d8e3] bg-[#191c24] light:bg-slate-50 hover:border-slate-500'}`}>
      <div className={`w-full h-12 rounded-t-xl ${isActive?'bg-emerald-950/40 light:bg-emerald-50':'bg-[#121419] light:bg-slate-100'} flex items-center justify-center relative`}>
        <span className={`text-[10px] font-mono font-bold ${isActive?'text-[#22c55e] light:text-[#15803d]':'text-[#9aa2b5] light:text-slate-600'}`}>{cameraId}</span>
        <div className={`absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full ${isOnline?'bg-green-400':'bg-slate-500'}`}/>
      </div>
      <div className="px-1.5 py-1 bg-[#121419] light:bg-white rounded-b-xl border-t border-[#272b37] light:border-[#d3d8e3]">
        <p className="text-[8px] font-mono text-[#9aa2b5] light:text-slate-500 truncate text-center">{location.split('-')[0].trim()}</p>
      </div>
    </div>
  );
}



export function CCTVPanel() {
  const cameras           = useStore((s) => s.cameras);
  const detections        = useStore((s) => s.detections);
  const selectedCamId     = useStore((s) => s.selectedCameraId);
  const setSelectedCam    = useStore((s) => s.setSelectedCamera);
  const systemStatus      = useStore((s) => s.systemStatus);
  const settings          = useStore((s) => s.settings);
  const activeVideoUrl    = useStore((s) => s.activeVideoUrl);
  const activeVideoId     = useStore((s) => s.activeVideoId);
  const uploadedVideoName = useStore((s) => s.uploadedVideoName);
  const setUploadedName   = useStore((s) => s.setUploadedVideoName);
  const uploadStatus      = useStore((s) => s.uploadStatus);
  const setUploadStatus   = useStore((s) => s.setUploadStatus);
  const pendingVideoBlob  = useStore((s) => s.pendingVideoBlob);
  const setActiveVideoUrl = useStore((s) => s.setActiveVideoUrl);
  const setActiveVideoId  = useStore((s) => s.setActiveVideoId);
  const setDetections     = useStore((s) => s.setDetections);
  const setActiveTracksForSource = useStore((s) => s.setActiveTracksForSource);
  const updateCamera             = useStore((s) => s.updateCamera);
  const videoAnalysisMetrics     = useStore((s) => s.videoAnalysisMetrics);
  const [streamVersion, setStreamVersion] = useState(0);




  // Zones State from store
  const zones             = useStore((s) => s.zones);
  const fetchZones        = useStore((s) => s.fetchZones);
  const [isZoneEditorOpen, setIsZoneEditorOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [addModalSourceType, setAddModalSourceType] = useState<CameraSourceType>('CCTV');
  const [modalSource, setModalSource] = useState<{ id: string; type: 'CAMERA' | 'WEBCAM' | 'VIDEO' } | null>(null);
  const [viewMode, setViewMode] = useState<'FOCUS' | 'GRID'>('FOCUS');


  useEffect(() => {
    fetchZones();
  }, [fetchZones]);

  // Camera Input State & Actions
  const cameraMode              = useStore((s) => s.cameraMode);
  const activeCameraStream      = useStore((s) => s.activeCameraStream);
  const cameraLoading           = useStore((s) => s.cameraLoading);
  const cameraError             = useStore((s) => s.cameraError);
  const cameraResolution        = useStore((s) => s.cameraResolution);
  const availableCameraDevices  = useStore((s) => s.availableCameraDevices);
  const selectedCameraDeviceId  = useStore((s) => s.selectedCameraDeviceId);
  const setCameraMode           = useStore((s) => s.setCameraMode);
  const startDeviceCamera       = useStore((s) => s.startDeviceCamera);
  const stopDeviceCamera        = useStore((s) => s.stopDeviceCamera);
  const switchCameraDevice      = useStore((s) => s.switchCameraDevice);
  const enumerateCameraDevices  = useStore((s) => s.enumerateCameraDevices);

  const containerRef   = useRef<HTMLDivElement|null>(null);
  const videoRef       = useRef<HTMLVideoElement|null>(null);
  const cameraVideoRef = useRef<HTMLVideoElement|null>(null);
  const roRef          = useRef<ResizeObserver|null>(null);

  // Real Webcam AI Inference Refs
  const inFlightRef            = useRef<boolean>(false);
  const frameSeqRef            = useRef<number>(0);
  const latestRenderedSeqRef   = useRef<number>(0);

  const [contentRect, setContentRect] = useState({ left:0, top:0, width:0, height:0 });
  const [currentPlaybackTime, setCurrentPlaybackTime] = useState(0);
  const [videoDuration, setVideoDuration]             = useState(0);
  const [activeFrameDetections, setActiveFrameDetections] = useState<Detection[]>([]);

  const selectedCam = cameras.find((c) => c.id === selectedCamId);

  // State machine
  const isAnalyzing   = !cameraMode && !!activeVideoId && !!uploadStatus && uploadStatus !== 'COMPLETED' && uploadStatus !== 'ERROR';
  const isVideoReady  = !cameraMode && !!activeVideoId && uploadStatus === 'COMPLETED' && !!activeVideoUrl;
  const isCameraMode  = cameraMode;
  const isCctvLive    = !cameraMode && !activeVideoId;

  // Active Source Identity & Zone Configuration
  const activeSourceId = isCameraMode ? 'WEBCAM-01' : (activeVideoId ? activeVideoId : selectedCamId);
  const activeSourceType: 'CAMERA' | 'WEBCAM' | 'VIDEO' = isCameraMode ? 'WEBCAM' : (activeVideoId ? 'VIDEO' : 'CAMERA');
  const activeZone = zones[activeSourceId];
  const hasZoneConfigured = Boolean(activeZone && activeZone.coordinates && activeZone.coordinates.length >= 3 && activeZone.enabled);
  const showRestrictedZone = settings.showRestrictedZone && hasZoneConfigured;
  const hasIntrusion = activeFrameDetections.some((d) => d.is_in_restricted_zone);



  // Pixel-accurate video content rect for uploaded videos and live webcam
  const updateContentRect = useCallback(() => {
    if (!containerRef.current) return;
    const c = containerRef.current;
    const cW = c.clientWidth, cH = c.clientHeight;
    if (cW === 0 || cH === 0) return;
    const targetVideo = isCameraMode ? cameraVideoRef.current : (isVideoReady ? videoRef.current : null);
    if (targetVideo && targetVideo.videoWidth > 0 && targetVideo.videoHeight > 0) {
      const vAR = targetVideo.videoWidth / targetVideo.videoHeight;
      const cAR = cW / cH;
      let rW = cW, rH = cH, oX = 0, oY = 0;
      if (cAR > vAR) { rW = cH * vAR; oX = (cW - rW) / 2; }
      else            { rH = cW / vAR; oY = (cH - rH) / 2; }
      setContentRect({ left:Math.round(oX), top:Math.round(oY), width:Math.round(rW), height:Math.round(rH) });
    } else {
      setContentRect({ left:0, top:0, width:cW, height:cH });
    }
  }, [isVideoReady, isCameraMode]);

  useEffect(() => {
    updateContentRect();
    if (containerRef.current) {
      roRef.current = new ResizeObserver(() => updateContentRect());
      roRef.current.observe(containerRef.current);
    }
    return () => { roRef.current?.disconnect(); roRef.current = null; };
  }, [updateContentRect]);

  // Video detections sorted by video_time_sec (ground truth)
  const videoDetsSorted = useMemo(() => {
    if (!isVideoReady || !activeVideoId) return [];
    const vDets = detections.filter((d) => d.video_id === activeVideoId);
    return [...vDets].sort((a, b) => {
      const at = a.video_time_sec ?? (new Date(a.timestamp).getTime() / 1000);
      const bt = b.video_time_sec ?? (new Date(b.timestamp).getTime() / 1000);
      return at - bt;
    });
  }, [detections, activeVideoId, isVideoReady]);

  // Infer frame duration from minimum gap between consecutive video_time_sec values
  const frameDuration = useMemo(() => {
    const withTime = videoDetsSorted.filter((d) => d.video_time_sec != null);
    if (withTime.length < 2) return 1 / 30;
    let minGap = Infinity;
    for (let i = 1; i < withTime.length; i++) {
      const gap = withTime[i].video_time_sec! - withTime[i-1].video_time_sec!;
      if (gap > 0 && gap < minGap) minGap = gap;
    }
    return minGap < Infinity ? minGap : 1 / 30;
  }, [videoDetsSorted]);

  // Bind live camera MediaStream to video element
  useEffect(() => {
    if (isCameraMode && cameraVideoRef.current) {
      if (activeCameraStream) {
        cameraVideoRef.current.srcObject = activeCameraStream;
        cameraVideoRef.current.play().catch((err) => {
          console.warn('[CCTVPanel] Camera stream play error:', err);
        });
      } else {
        cameraVideoRef.current.srcObject = null;
      }
    }
  }, [isCameraMode, activeCameraStream]);

  // Ref to track webcam AI status (to avoid triggering re-renders on every status check)
  const webcamAiActiveRef = useRef<boolean>(false);
  const setSystemStatus   = useStore((s) => s.setSystemStatus);
  const addDetection      = useStore((s) => s.addDetection);

  // Connection and Live AI State
  const [liveAiState, setLiveAiState] = useState<'IDLE' | 'PROCESSING' | 'OFFLINE'>('IDLE');

  const cameraConnectionState = useMemo<
    'CONNECTING' | 'CONNECTED' | 'AI PROCESSING' | 'AI OFFLINE' | 'DISCONNECTED' | 'ERROR'
  >(() => {
    if (cameraLoading) return 'CONNECTING';
    if (cameraError) return 'ERROR';
    if (!activeCameraStream) return 'DISCONNECTED';
    if (liveAiState === 'PROCESSING') return 'AI PROCESSING';
    if (liveAiState === 'OFFLINE') return 'AI OFFLINE';
    return 'CONNECTED';
  }, [cameraLoading, cameraError, activeCameraStream, liveAiState]);

  // Live Camera Runtime Metrics (Camera FPS, AI FPS, Latency ms)
  const [liveCamMetrics, setLiveCamMetrics] = useState<{
    camera_fps: number;
    ai_fps: number;
    latency_ms: number;
    dropped_stale_frames: number;
    active_tracks: number;
    ai_status: string;
    rotation?: number;
  } | null>(null);

  const currentRotation = selectedCam?.rotation ?? liveCamMetrics?.rotation ?? 0;

  const handleCycleRotation = async () => {
    if (!selectedCamId) return;
    const nextRot = (currentRotation + 90) % 360;
    try {
      updateCamera(selectedCamId, { rotation: nextRot });
      await api.setCameraRotation(selectedCamId, nextRot);
      setStreamVersion((v) => v + 1);
    } catch (err) {
      console.warn('[CCTVPanel] Error rotating camera:', err);
    }
  };

  useEffect(() => {
    if (!isCctvLive || !selectedCamId || isCameraMode || isVideoReady) {
      setLiveCamMetrics(null);
      return;
    }
    let isMounted = true;
    const fetchMetrics = async () => {
      try {
        const res = await fetch(`/api/cameras/${selectedCamId}/metrics`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted) setLiveCamMetrics(data);
        }
      } catch (e) {
        // network or server starting
      }
    };
    fetchMetrics();
    const timer = setInterval(fetchMetrics, 1500);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, [isCctvLive, selectedCamId, isCameraMode, isVideoReady]);

  // Bind live camera MediaStream to video element
  useEffect(() => {
    if (isCameraMode && cameraVideoRef.current) {
      if (activeCameraStream) {
        console.log('[LIVE] Camera connected', {
          id: activeCameraStream.id,
          tracks: activeCameraStream.getVideoTracks().map((t) => t.label),
        });
        cameraVideoRef.current.srcObject = activeCameraStream;
        cameraVideoRef.current.play().catch((err) => {
          console.warn('[CCTVPanel] Camera stream play error:', err);
        });
      } else {
        cameraVideoRef.current.srcObject = null;
        setLiveAiState('IDLE');
      }
    }
  }, [isCameraMode, activeCameraStream]);

  // Real Live Camera YOLOv8 AI Inference Loop (~8 FPS, 640x360, async lock, sequence ordering)
  useEffect(() => {
    if (!isCameraMode || !activeCameraStream) {
      // Only reset refs — NO Zustand state mutations here (they cause infinite loops)
      setActiveFrameDetections([]);
      frameSeqRef.current = 0;
      latestRenderedSeqRef.current = 0;
      if (webcamAiActiveRef.current) {
        webcamAiActiveRef.current = false;
        setSystemStatus({ ai_engine_status: 'STOPPED' });
      }
      return;
    }

    let isMounted = true;
    const captureCanvas = document.createElement('canvas');
    captureCanvas.width = 640;
    captureCanvas.height = 360;
    const ctx = captureCanvas.getContext('2d');

    // Per-session dedup state (lives inside the closure, not in React state)
    const seenObjectKeys = new Set<string>();
    const lastLoggedTime = new Map<string, number>();

    const intervalId = setInterval(async () => {
      if (!isMounted || inFlightRef.current || !cameraVideoRef.current) return;
      const v = cameraVideoRef.current;
      if (v.paused || v.ended || v.readyState < 2) return;

      inFlightRef.current = true;
      try {
        // Capture frame
        ctx?.drawImage(v, 0, 0, 640, 360);
        const base64Data = captureCanvas.toDataURL('image/jpeg', 0.7);

        frameSeqRef.current += 1;
        const currentSeq = frameSeqRef.current;
        console.log('[LIVE] Frame captured', { width: 640, height: 360, seq: currentSeq });

        const confThreshold = (settings.aiThreshold || 50) / 100;
        const faceEnabled = settings.faceRecognitionEnabled ?? true;
        const faceThreshold = (settings.faceMatchThreshold ?? 45) / 100;
        const anprEnabled = settings.anprEnabled ?? true;

        console.log('[LIVE] Frame sent for inference', { seq: currentSeq, camera_id: activeSourceId });

        const res = await api.inferWebcamFrame(
          base64Data,
          confThreshold,
          currentSeq,
          faceEnabled,
          faceThreshold,
          anprEnabled,
          activeSourceId
        );

        if (!isMounted) return;

        if (res && res.error) {
          console.warn('[YOLO] Inference error:', res.error);
          setLiveAiState('OFFLINE');
        } else if (res) {
          setLiveAiState('PROCESSING');
          // Mark AI as running on first successful response
          if (!webcamAiActiveRef.current) {
            webcamAiActiveRef.current = true;
            setSystemStatus({ ai_engine_status: 'RUNNING' });
          }
        }

        if (res && res.frame_seq >= latestRenderedSeqRef.current) {
          latestRenderedSeqRef.current = res.frame_seq;
          const allDets = (res.detections || []) as Detection[];
          console.log('[UI] Detection received', { count: allDets.length, camera_id: activeSourceId, seq: res.frame_seq });

          const threshold = settings.aiThreshold || 50;
          const filtered = allDets.filter(
            (d) => typeof d.confidence === 'number' && d.confidence >= threshold
          );

          // Update bounding boxes (local state only — no Zustand array replacement)
          setActiveFrameDetections(filtered);
          setActiveTracksForSource(activeSourceId, filtered);

          // Push significant events into store using addDetection (append, not replace)
          const now = Date.now() / 1000;
          for (const det of filtered) {
            const key = det.object_id || det.camera_id;
            const prevTime = lastLoggedTime.get(key);

            const isFirstSeen      = !seenObjectKeys.has(key);
            const isNewIntrusion   = !!det.is_in_restricted_zone && !seenObjectKeys.has(key + ':zone');
            const isNewLoitering   = (det.loitering_duration ?? 0) > 0 && !seenObjectKeys.has(key + ':loiter');
            const isPeriodicUpdate = prevTime != null && (now - prevTime) >= 3.0;

            if (isFirstSeen || isNewIntrusion || isNewLoitering || isPeriodicUpdate) {
              seenObjectKeys.add(key);
              if (isNewIntrusion) seenObjectKeys.add(key + ':zone');
              if (isNewLoitering) seenObjectKeys.add(key + ':loiter');
              lastLoggedTime.set(key, now);

              // addDetection prepends to store array (bounded to 500 by store action)
              addDetection({
                ...det,
                video_id: undefined,
                video_time_sec: undefined,
              });
            }
          }
        }
      } catch (err) {
        console.warn('[WebcamAI] Inference loop error:', err);
        if (isMounted) setLiveAiState('OFFLINE');
      } finally {
        inFlightRef.current = false;
      }
    }, 125); // ~8 FPS

    return () => {
      isMounted = false;
      clearInterval(intervalId);
      // Cleanup: NO state mutations — refs only, to avoid triggering re-renders
      webcamAiActiveRef.current = false;
      setLiveAiState('IDLE');
      setActiveTracksForSource(activeSourceId, []);
      api.resetWebcamSession(activeSourceId).catch(() => {});
    };
  }, [isCameraMode, activeCameraStream, activeSourceId, settings.aiThreshold, settings.faceRecognitionEnabled, settings.faceMatchThreshold, settings.anprEnabled, setSystemStatus, addDetection, setActiveTracksForSource]);

  // Frame sync loop using requestAnimationFrame for Uploaded Videos / CCTV
  useEffect(() => {
    if (isCameraMode) {
      return;
    }

    if (isCctvLive) {
      const nowMs = Date.now();
      // Only consider real detections within the last 3.5s as currently visible/active
      const recentLiveDets = detections.filter(
        (d) => d.camera_id === selectedCamId && !d.video_id && (nowMs - new Date(d.timestamp).getTime()) < 3500
      );
      setActiveFrameDetections([]); // Live MJPEG stream paints bounding boxes directly on video canvas
      if (selectedCamId) setActiveTracksForSource(selectedCamId, recentLiveDets);
      return;
    }

    if (!isVideoReady) {
      setActiveFrameDetections([]);
      return;
    }

    let animId: number;
    const syncLoop = () => {
      if (videoRef.current && videoDetsSorted.length > 0) {
        const curr = videoRef.current.currentTime;
        setCurrentPlaybackTime(curr);

        const hasFrameTime = videoDetsSorted.some((d) => d.video_time_sec != null);
        if (hasFrameTime) {
          const tolerance = frameDuration * 0.6;
          const matching = videoDetsSorted.filter(
            (d) => d.video_time_sec != null && Math.abs(d.video_time_sec - curr) <= tolerance
          );
          const uniqueMap = new Map<string, Detection>();
          for (const det of matching) {
            const existing = uniqueMap.get(det.object_id);
            if (!existing || Math.abs(det.video_time_sec! - curr) < Math.abs(existing.video_time_sec! - curr)) {
              uniqueMap.set(det.object_id, det);
            }
          }
          const filtered = Array.from(uniqueMap.values()).filter(
            (d) => typeof d.confidence === 'number' && d.confidence >= (settings.aiThreshold || 50)
          );
          setActiveFrameDetections(filtered);
          if (activeVideoId) {
            setActiveTracksForSource(activeVideoId, filtered);
          }
        }
      }
      animId = requestAnimationFrame(syncLoop);
    };
    animId = requestAnimationFrame(syncLoop);
    return () => cancelAnimationFrame(animId);
  }, [isCctvLive, isCameraMode, isVideoReady, videoDetsSorted, frameDuration, detections, selectedCamId, activeVideoId, settings.aiThreshold, setActiveTracksForSource]);

  const handleResetToLive = () => {
    setActiveVideoUrl(null);
    setActiveVideoId(null);
    setUploadedName(null);
    setUploadStatus(null);
    setCurrentPlaybackTime(0);
    setVideoDuration(0);
    setActiveFrameDetections([]);
    setCameraMode(false);
    setDetections([]); // Zero preloaded detections for clean live start
  };

  const handleEnterCameraMode = async () => {
    setCameraMode(true);
    setDetections([]);
    await startDeviceCamera();
    enumerateCameraDevices().catch(() => {});
  };

  const handleExitCameraMode = () => {
    setSystemStatus({ ai_engine_status: 'STOPPED' });
    stopDeviceCamera();
    setCameraMode(false);
    setActiveFrameDetections([]);
    setActiveTracksForSource('WEBCAM-01', []);
    setDetections([]);
  };

  const handleStopCamera = () => {
    setSystemStatus({ ai_engine_status: 'STOPPED' });
    stopDeviceCamera();
    setActiveFrameDetections([]);
  };

  const handleStartCamera = async () => {
    await startDeviceCamera(selectedCameraDeviceId || undefined);
  };

  // For both uploaded video and webcam: use pixel-accurate rect when video is loaded.
  const overlayStyle = contentRect.width > 0 && contentRect.height > 0
    ? { left: contentRect.left, top: contentRect.top, width: contentRect.width, height: contentRect.height }
    : { left: 0, top: 0, width: '100%', height: '100%' };

  return (
    <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl overflow-hidden flex flex-col h-full shadow-card">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#272b37] light:border-[#d3d8e3] bg-[#191c24] light:bg-slate-50 flex-wrap gap-2">
        <div className="flex items-center gap-2 flex-wrap">
          {isCameraMode ? (
            <>
              <span className="text-sm font-semibold text-white light:text-slate-900 flex items-center gap-1.5">
                <Camera size={15} className="text-emerald-400 light:text-[#15803d]" />
                Live Camera ({activeSourceId})
              </span>
              <span className="text-[#62697b] light:text-slate-400">•</span>
              <span className="text-xs text-[#9aa2b5] light:text-slate-600">
                {cameraResolution || 'Webcam Stream'}
              </span>
              <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold uppercase flex items-center gap-1.5 ${
                cameraConnectionState === 'AI PROCESSING'
                  ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400 light:bg-emerald-100 light:text-emerald-700'
                  : cameraConnectionState === 'AI OFFLINE'
                  ? 'bg-amber-500/20 border-amber-500/50 text-amber-400 light:bg-amber-100 light:text-amber-700'
                  : cameraConnectionState === 'CONNECTING'
                  ? 'bg-blue-500/20 border-blue-500/50 text-blue-400 light:bg-blue-100 light:text-blue-700'
                  : cameraConnectionState === 'ERROR'
                  ? 'bg-red-500/20 border-red-500/50 text-red-400 light:bg-red-100 light:text-red-700'
                  : 'bg-slate-800/40 border-slate-700 text-slate-400 light:bg-slate-100 light:text-slate-600'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full ${
                  cameraConnectionState === 'AI PROCESSING' ? 'bg-emerald-400 animate-pulse' :
                  cameraConnectionState === 'AI OFFLINE' ? 'bg-amber-400' :
                  cameraConnectionState === 'CONNECTING' ? 'bg-blue-400 animate-pulse' :
                  cameraConnectionState === 'ERROR' ? 'bg-red-400' : 'bg-slate-400'
                }`} />
                {cameraConnectionState}
              </span>
            </>
          ) : (
            <>
              <span className="text-sm font-semibold text-white light:text-slate-900">{selectedCamId}</span>
              <span className="text-[#62697b] light:text-slate-400">•</span>
              <span className="text-xs text-[#9aa2b5] light:text-slate-600">
                {(isAnalyzing||isVideoReady)&&uploadedVideoName ? uploadedVideoName : (selectedCam?.location||'Unknown')}
              </span>
              {selectedCam?.source_type === 'USB_PHONE' && !isAnalyzing && !isVideoReady && (
                <span className="px-1.5 py-0.5 rounded bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 light:bg-cyan-100 light:text-cyan-800 text-[10px] font-mono font-bold uppercase flex items-center gap-1">
                  <Usb size={10} /> USB PHONE
                </span>
              )}
              {isAnalyzing&&(<span className="px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-400 light:bg-amber-100 light:text-amber-700 text-[10px] font-mono font-bold uppercase flex items-center gap-1"><Loader2 size={9} className="animate-spin"/>ANALYZING</span>)}
              {isVideoReady&&(<span className="px-1.5 py-0.5 rounded bg-blue-500/20 border border-blue-500/40 text-blue-400 light:bg-blue-100 light:text-blue-700 text-[10px] font-mono font-bold uppercase">CCTV CLIP</span>)}
              {hasIntrusion&&(<span className="px-1.5 py-0.5 rounded bg-red-500/15 border border-red-500/30 text-red-400 light:bg-red-100 light:text-red-700 text-[10px] font-mono font-bold uppercase animate-pulse">🚨 INTRUSION</span>)}
            </>
          )}
        </div>


        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {/* Mode Switcher / Camera Controls */}
          {isCameraMode ? (
            <div className="flex items-center gap-2">
              {/* Device Selector (if multiple devices) */}
              {availableCameraDevices.length > 1 && (
                <select
                  value={selectedCameraDeviceId || ''}
                  onChange={(e) => switchCameraDevice(e.target.value)}
                  className="text-[10px] font-mono bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] text-white light:text-slate-900 rounded-lg px-2 py-1 focus:outline-none focus:border-[#22c55e]"
                >
                  {availableCameraDevices.map((dev, idx) => (
                    <option key={dev.deviceId || idx} value={dev.deviceId}>
                      {dev.label || `Camera ${idx + 1}`}
                    </option>
                  ))}
                </select>
              )}

              {/* Start / Stop Toggle */}
              {activeCameraStream ? (
                <button
                  type="button"
                  onClick={handleStopCamera}
                  className="text-[10px] font-semibold text-red-400 light:text-red-700 px-2.5 py-1 rounded-lg bg-red-500/15 light:bg-red-50 hover:bg-red-500/25 border border-red-500/30 light:border-red-200 transition-all flex items-center gap-1 cursor-pointer"
                >
                  <VideoOff size={11} /> Stop Camera
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleStartCamera}
                  className="text-[10px] font-semibold text-white px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 transition-all flex items-center gap-1 cursor-pointer shadow-xs"
                >
                  <Video size={11} /> Start Camera
                </button>
              )}

              {/* Return to CCTV */}
              <button
                type="button"
                onClick={handleExitCameraMode}
                className="text-[10px] font-semibold text-[#9aa2b5] light:text-slate-700 hover:text-white light:hover:text-slate-900 px-2.5 py-1 rounded-lg bg-[#191c24] light:bg-slate-100 hover:bg-slate-700 light:hover:bg-slate-200 border border-[#272b37] light:border-[#d9dde3] transition-all flex items-center gap-1 cursor-pointer"
              >
                <ArrowLeft size={11} /> Return to CCTV
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              {(isAnalyzing || isVideoReady) ? (
                <button
                  type="button"
                  onClick={handleResetToLive}
                  className="text-[10px] font-semibold text-[#9aa2b5] light:text-slate-700 hover:text-white light:hover:text-slate-900 px-2.5 py-1 rounded-lg bg-[#191c24] light:bg-slate-100 hover:bg-slate-700 light:hover:bg-slate-200 border border-[#272b37] light:border-[#d9dde3] transition-all cursor-pointer"
                >
                  Reset to Live Feed
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => setIsAddModalOpen(true)}
                    className="text-[10px] font-semibold text-white light:text-slate-800 px-2.5 py-1 rounded-lg bg-slate-800 light:bg-slate-100 hover:bg-slate-700 light:hover:bg-slate-200 border border-slate-700 light:border-[#d9dde3] transition-all flex items-center gap-1 cursor-pointer shadow-xs"
                  >
                    <Plus size={11} /> Add Camera
                  </button>

                  <button
                    type="button"
                    onClick={handleEnterCameraMode}
                    className="text-[10px] font-semibold text-emerald-400 light:text-emerald-700 hover:text-emerald-300 px-2.5 py-1 rounded-lg bg-emerald-500/15 light:bg-emerald-50 hover:bg-emerald-500/25 border border-emerald-500/30 light:border-emerald-200 transition-all flex items-center gap-1 cursor-pointer shadow-xs"
                  >
                    <Camera size={11} /> Use Device Camera
                  </button>
                </>
              )}

              {/* View Mode Toggle: Focus vs Grid */}
              {!isAnalyzing && !isVideoReady && (
                <div className="flex items-center bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] rounded-lg p-0.5">
                  <button
                    type="button"
                    onClick={() => setViewMode('FOCUS')}
                    className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
                      viewMode === 'FOCUS'
                        ? 'bg-[#22c55e] text-white font-bold shadow-xs'
                        : 'text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 font-medium'
                    }`}
                    title="Focus View (Single Feed)"
                  >
                    <Maximize2 size={11} /> Single
                  </button>
                  <button
                    type="button"
                    onClick={() => setViewMode('GRID')}
                    className={`px-2 py-0.5 rounded text-[10px] font-mono flex items-center gap-1 transition-all cursor-pointer ${
                      viewMode === 'GRID'
                        ? 'bg-[#22c55e] text-white font-bold shadow-xs'
                        : 'text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 font-medium'
                    }`}
                    title="Dynamic Multi-Camera Grid"
                  >
                    <LayoutGrid size={11} /> Grid
                  </button>
                </div>
              )}

              {/* Camera Orientation / Rotation Toggle Button */}
              {isCctvLive && selectedCam && (
                <button
                  type="button"
                  onClick={handleCycleRotation}
                  className="text-[10px] font-mono px-2.5 py-1 rounded-lg border transition-all flex items-center gap-1.5 cursor-pointer shadow-xs font-semibold bg-[#191c24] light:bg-slate-100 hover:bg-slate-700 light:hover:bg-slate-200 text-slate-300 light:text-slate-700 border-[#272b37] light:border-[#d9dde3]"
                  title="Rotate Camera Stream 90° (0°, 90°, 180°, 270°)"
                >
                  <RotateCcw size={12} className="text-cyan-400" />
                  <span>{currentRotation}°</span>
                </button>
              )}

              {/* Zone Configuration Button */}
              <button
                type="button"
                onClick={() => {
                  setModalSource(null);
                  setIsZoneEditorOpen(true);
                }}
                className={`text-[10px] font-mono px-2.5 py-1 rounded-lg border transition-all flex items-center gap-1.5 cursor-pointer shadow-xs font-semibold ${
                  hasZoneConfigured
                    ? 'bg-red-500/15 hover:bg-red-500/25 text-red-400 light:text-red-700 border-red-500/30 light:border-red-200 light:bg-red-50'
                    : 'bg-[#191c24] light:bg-slate-100 hover:bg-slate-700 light:hover:bg-slate-200 text-[#9aa2b5] light:text-slate-700 border-[#272b37] light:border-[#d9dde3]'
                }`}
                title="Configure restricted zone for this camera"
              >
                <ShieldAlert size={12} className={hasZoneConfigured ? 'text-red-400 light:text-red-600' : 'text-[#9aa2b5] light:text-slate-500'} />
                <span>{hasZoneConfigured ? activeZone.name : 'Configure Zone'}</span>
              </button>

              {isCctvLive && liveCamMetrics ? (
                <span className="text-[10px] font-mono text-cyan-400 light:text-cyan-600 font-medium">
                  {liveCamMetrics.ai_status === 'RUNNING' ? (
                    <>CAM: {liveCamMetrics.camera_fps.toFixed(1)} FPS • AI: {liveCamMetrics.ai_fps.toFixed(1)} FPS • {liveCamMetrics.latency_ms.toFixed(0)}ms</>
                  ) : (
                    <span className="text-amber-400">AI PROCESSING: OFFLINE</span>
                  )}
                </span>
              ) : (
                <span className="text-[10px] font-mono text-[#9aa2b5] light:text-slate-500 font-medium">{systemStatus.fps.toFixed(1)} FPS • {systemStatus.processing_time_ms}ms</span>
              )}
              <LiveBadge/>
            </div>
          )}
        </div>
      </div>



      {/* Video Viewport Area */}
      <div ref={containerRef} className="relative flex-1 cctv-bg overflow-hidden flex items-center justify-center min-h-[340px] max-h-[500px]">
        {/* ================= DYNAMIC MULTI-CAMERA GRID VIEW ================= */}
        {viewMode === 'GRID' && !isAnalyzing && !isVideoReady ? (
          <MultiCameraGrid
            cameras={cameras}
            selectedCamId={selectedCamId}
            onSelectCamera={(id) => {
              if (id === 'WEBCAM-01') {
                if (!isCameraMode) handleEnterCameraMode();
              } else {
                if (isCameraMode) handleExitCameraMode();
                setSelectedCam(id);
              }
              setViewMode('FOCUS');
            }}
            onConfigureZone={(sourceId, sourceType) => {
              setModalSource({ id: sourceId, type: sourceType });
              setIsZoneEditorOpen(true);
            }}
            zones={zones}
            detections={detections}
            webcamDetections={activeFrameDetections}
            cameraVideoRef={cameraVideoRef}
            isCameraMode={isCameraMode}
            activeCameraStream={activeCameraStream}
            settings={settings}
            onStartDeviceCamera={handleEnterCameraMode}
            onOpenAddCamera={() => setIsAddModalOpen(true)}
          />

        ) : (
          <>
            {/* ================= MODE 1: DEVICE CAMERA ================= */}
            {isCameraMode && (
              <>
                {/* Camera Loading State */}
                {cameraLoading && (
                  <div className="absolute inset-0 bg-black/75 flex flex-col items-center justify-center z-25">
                    <Loader2 size={32} className="text-emerald-400 animate-spin mb-3" />
                    <p className="text-emerald-400 font-mono text-sm font-semibold">Starting camera...</p>
                    <p className="text-slate-500 font-mono text-xs mt-1">Requesting browser camera permission & initializing feed</p>
                  </div>
                )}

                {/* Camera Error / Permission Denied State */}
                {!cameraLoading && cameraError && (
                  <div className="flex flex-col items-center justify-center p-6 text-center z-20 max-w-md animate-fadeIn">
                    <div className="w-14 h-14 rounded-full bg-red-500/15 border border-red-500/40 flex items-center justify-center text-red-400 mb-3">
                      <AlertCircle size={26} />
                    </div>
                    <h4 className="text-sm font-semibold text-red-300">
                      {cameraError.includes('denied') ? 'Camera Permission Denied' : 'Camera Unavailable'}
                    </h4>
                    <p className="text-xs text-slate-400 mt-1.5 mb-4 leading-relaxed">
                      {cameraError}
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleStartCamera}
                        className="ibvap-btn-primary text-xs py-1.5 px-3 flex items-center gap-1.5"
                      >
                        <RotateCcw size={12} /> Retry Camera
                      </button>
                      <button
                        onClick={handleExitCameraMode}
                        className="text-xs py-1.5 px-3 rounded font-medium bg-[#141e33] hover:bg-[#1e2d4a] text-slate-300 border border-[#1e2d4a] transition-all flex items-center gap-1"
                      >
                        Return to CCTV
                      </button>
                    </div>
                  </div>
                )}

                {/* Camera Active Live Video */}
                {!cameraLoading && !cameraError && activeCameraStream && (
                  <>
                    <video
                      ref={cameraVideoRef}
                      autoPlay
                      playsInline
                      muted
                      onLoadedMetadata={() => requestAnimationFrame(() => updateContentRect())}
                      onLoadedData={() => requestAnimationFrame(() => updateContentRect())}
                      onPlaying={() => requestAnimationFrame(() => updateContentRect())}
                      onResize={() => requestAnimationFrame(() => updateContentRect())}
                      className="w-full h-full object-contain z-0"
                    />
                    <div className="absolute top-3 left-3 flex items-center gap-1.5 bg-black/75 backdrop-blur-sm px-2.5 py-1 rounded border border-white/10 text-[10px] font-mono text-emerald-400 z-30 pointer-events-none">
                      <Camera size={11} /> LIVE DEVICE WEBCAM
                    </div>
                    <div className="absolute bottom-3 right-3 text-[10px] font-mono text-slate-400 bg-black/70 px-2 py-0.5 rounded border border-white/10 z-30 pointer-events-none">
                      {cameraResolution || '1080p'} • BROWSER LOCAL FEED
                    </div>
                  </>
                )}

                {/* Camera Stopped / Standby */}
                {!cameraLoading && !cameraError && !activeCameraStream && (
                  <div className="flex flex-col items-center justify-center p-6 text-center z-20 max-w-md">
                    <div className="w-14 h-14 rounded-full bg-[#141e33] border border-[#1e2d4a] flex items-center justify-center text-slate-400 mb-3">
                      <VideoOff size={24} className="text-slate-400" />
                    </div>
                    <h4 className="text-sm font-semibold text-slate-200">Device Camera Standby</h4>
                    <p className="text-xs text-slate-400 mt-1 mb-4">
                      Camera stream is currently stopped. Click below to start the camera or return to standard CCTV live monitoring.
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleStartCamera}
                        className="ibvap-btn-primary text-xs py-1.5 px-4 flex items-center gap-1.5"
                      >
                        <Video size={13} /> Start Camera
                      </button>
                      <button
                        onClick={handleExitCameraMode}
                        className="text-xs py-1.5 px-3 rounded font-medium bg-[#141e33] hover:bg-[#1e2d4a] text-slate-300 border border-[#1e2d4a] transition-all flex items-center gap-1"
                      >
                        Return to CCTV
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ================= MODE 2: UPLOADED VIDEO ================= */}
            {/* Analyzing state thumbnail */}
            {isAnalyzing && pendingVideoBlob && (
              <video src={pendingVideoBlob} muted playsInline className="w-full h-full object-contain z-0"/>
            )}

            {/* Completed playback video */}
            {isVideoReady && (
              <video
                ref={videoRef} src={activeVideoUrl!} muted playsInline controls
                onLoadedMetadata={(e)=>{setVideoDuration(e.currentTarget.duration);requestAnimationFrame(()=>updateContentRect());}}
                onPlay={()=>requestAnimationFrame(()=>updateContentRect())}
                onSeeked={()=>requestAnimationFrame(()=>updateContentRect())}
                onTimeUpdate={(e)=>setCurrentPlaybackTime(e.currentTarget.currentTime)}
                className="w-full h-full object-contain z-0"
              />
            )}

            {/* ================= MODE 3: LIVE CCTV / PHONE STREAM PROXY ================= */}
            {isCctvLive && selectedCam?.stream_url && (
              <img
                key={`${selectedCamId}-${streamVersion}-${currentRotation}`}
                src={`/api/cameras/${selectedCamId}/stream?conf=${(settings.aiThreshold ?? 30) / 100}&rotate=${currentRotation}&v=${streamVersion}`}
                alt={selectedCam.name}
                className="w-full h-full object-contain z-0"
                onError={(e) => {
                  (e.currentTarget as HTMLElement).style.display = 'none';
                }}
              />
            )}

            {/* No cameras configured empty state */}
            {cameras.length === 0 && !isCameraMode && !isAnalyzing && !isVideoReady && (
              <div className="flex flex-col items-center justify-center p-6 text-center z-20 max-w-md animate-fadeIn">
                <div className="w-14 h-14 rounded-full bg-[#141e33] border border-[#1e2d4a] flex items-center justify-center text-slate-400 mb-3">
                  <Video size={24} className="text-slate-400" />
                </div>
                <h4 className="text-sm font-semibold text-slate-200">No Cameras Connected</h4>
                <p className="text-xs text-slate-400 mt-1 mb-4 leading-relaxed">
                  SHIELD starts with zero predefined cameras. Connect an Android phone via USB cable, physical CCTV via RTSP, or your laptop webcam.
                </p>
                <div className="flex items-center gap-2 flex-wrap justify-center">
                  <button
                    onClick={() => {
                      setAddModalSourceType('USB_PHONE');
                      setIsAddModalOpen(true);
                    }}
                    className="text-xs py-1.5 px-3 rounded font-medium bg-cyan-600 hover:bg-cyan-500 text-white transition-all flex items-center gap-1 cursor-pointer"
                  >
                    <Usb size={13} /> + Connect USB Phone
                  </button>
                  <button
                    onClick={handleEnterCameraMode}
                    className="text-xs py-1.5 px-3 rounded font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-all flex items-center gap-1 cursor-pointer"
                  >
                    <Camera size={13} /> Use Laptop Webcam
                  </button>
                  <button
                    onClick={() => {
                      setAddModalSourceType('CCTV');
                      setIsAddModalOpen(true);
                    }}
                    className="text-xs py-1.5 px-3 rounded font-medium bg-[#1d6af5] hover:bg-[#1655c7] text-white transition-all flex items-center gap-1 cursor-pointer"
                  >
                    <Video size={13} /> + Add CCTV Feed
                  </button>
                </div>
              </div>
            )}

            {/* CCTV Styling Overlay (Scanlines & Vignette) */}
            <div className="cctv-scanline z-10 pointer-events-none"/>
            <div className="cctv-vignette z-10 pointer-events-none"/>

            {/* Analyzing overlay for uploaded video */}
            {isAnalyzing && (
              <div className="absolute inset-0 bg-black/65 flex flex-col items-center justify-center z-25 pointer-events-none p-6 text-center">
                <Loader2 size={32} className="text-blue-400 animate-spin mb-3"/>
                <p className="text-blue-400 font-mono text-sm font-bold">
                  Analyzing with YOLOv8 & Tracker... {videoAnalysisMetrics?.progress ?? 0}%
                </p>
                {videoAnalysisMetrics && videoAnalysisMetrics.totalFrames > 0 ? (
                  <p className="text-slate-300 font-mono text-xs mt-1.5">
                    Frame {videoAnalysisMetrics.currentFrame} / {videoAnalysisMetrics.totalFrames} • {videoAnalysisMetrics.detections} objects ({videoAnalysisMetrics.tracks} tracks)
                  </p>
                ) : (
                  <p className="text-slate-400 font-mono text-xs mt-1.5">
                    Extracting video stream & running YOLOv8 pipeline...
                  </p>
                )}
                <div className="w-64 h-1.5 bg-[#1e2d4a] rounded-full overflow-hidden mt-3">
                  <div
                    className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 rounded-full transition-all duration-300"
                    style={{ width: `${Math.max(4, videoAnalysisMetrics?.progress ?? 0)}%` }}
                  />
                </div>
              </div>
            )}


            {/* Bounding box & Zone overlay for live CCTV, analyzed video clips, and live laptop webcam */}
            {overlayStyle && (isVideoReady || isCctvLive || isCameraMode) && (
              <div className="absolute z-20 pointer-events-none" style={overlayStyle}>
                {showRestrictedZone && <RestrictedZoneOverlay zone={activeZone} />}
                {settings.showBoundingBoxes &&
                  activeFrameDetections.map((det) => (
                    <BoundingBox key={det.id} det={det} showConfidence={settings.showConfidence} />
                  ))}
              </div>
            )}
          </>
        )}



        {/* Corner timestamp */}
        <div className="absolute top-3 right-3 text-[10px] font-mono text-slate-400 bg-black/70 px-2 py-0.5 rounded border border-white/10 z-30 pointer-events-none">
          {isVideoReady
            ? `T+${currentPlaybackTime.toFixed(2)}s / ${videoDuration?videoDuration.toFixed(1)+'s':'-'}`
            : isCameraMode
            ? `WEBCAM • ${new Date().toLocaleTimeString('en-IN',{hour12:false})}`
            : `${new Date().toLocaleTimeString('en-IN',{hour12:false})} • ${selectedCamId}`}
        </div>

        {/* Model name / Mode indicator */}
        <div className="absolute bottom-3 left-3 z-30 pointer-events-none">
          <span className="text-[9px] font-mono text-slate-300 bg-black/70 px-2 py-0.5 rounded border border-white/10">
            {isCameraMode
              ? 'Local MediaStream (Direct Camera)'
              : isCctvLive && liveCamMetrics
              ? liveCamMetrics.ai_status === 'RUNNING'
                ? `YOLOv8n Live • ${liveCamMetrics.active_tracks} Track${liveCamMetrics.active_tracks === 1 ? '' : 's'} • Latency ${liveCamMetrics.latency_ms.toFixed(0)}ms`
                : 'AI PROCESSING: OFFLINE'
              : systemStatus.model_name}
          </span>
        </div>

        {/* Object count for uploaded video */}
        {isVideoReady && (
          <div className="absolute bottom-3 right-3 text-[10px] font-mono text-slate-300 bg-black/70 px-2 py-0.5 rounded border border-white/10 z-30 pointer-events-none">
            {activeFrameDetections.length} object{activeFrameDetections.length!==1?'s':''} detected
          </div>
        )}
      </div>

      {/* AI Pipeline Strip */}
      <div className="px-4 py-2 border-t border-[#272b37] light:border-[#d3d8e3] bg-[#121419] light:bg-slate-50">
        <div className="flex items-center gap-1 text-[9px] font-mono text-[#62697b] light:text-slate-500 overflow-x-auto">
          {['Frame Capture','YOLOv8 Detection','Tracking','Zone Analysis','Threat Engine','Alert Broadcast'].map((step,i,arr)=>(
            <span key={step} className="flex items-center gap-1 flex-shrink-0">
              <span className={`px-1.5 py-0.5 rounded border ${isCameraMode ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 light:bg-emerald-100 light:text-emerald-800 light:border-emerald-300' : 'bg-slate-800/60 border-slate-700 text-slate-300 light:bg-slate-200 light:border-slate-300 light:text-slate-800'}`}>
                {step}
              </span>
              {i<arr.length-1&&<span className="text-[#62697b] light:text-slate-400 opacity-60">›</span>}
            </span>
          ))}
        </div>
      </div>

      {/* Camera Thumbnails */}
      <div className="px-4 py-3 border-t border-[#272b37] light:border-[#d3d8e3] bg-[#121419] light:bg-white">
        <div className="flex gap-2 overflow-x-auto pb-1 items-center">
          {/* Dedicated Device Camera Thumbnail Selector */}
          <div
            onClick={() => {
              if (!isCameraMode) {
                handleEnterCameraMode();
              }
            }}
            className={`flex-shrink-0 w-24 rounded-xl cursor-pointer border transition-all duration-150 ${isCameraMode ? 'border-emerald-500 bg-[#13271d] light:bg-[#ecfdf5] light:border-[#86efac]' : 'border-[#272b37] light:border-[#d3d8e3] bg-[#191c24] light:bg-slate-50 hover:border-slate-500'}`}
          >
            <div className={`w-full h-12 rounded-t-xl ${isCameraMode ? 'bg-emerald-950/40 light:bg-emerald-50' : 'bg-[#121419] light:bg-slate-100'} flex flex-col items-center justify-center relative`}>
              <Camera size={14} className={isCameraMode ? 'text-emerald-400 light:text-[#15803d]' : 'text-[#9aa2b5] light:text-slate-500'} />
              <span className={`text-[8px] font-mono mt-0.5 font-bold ${isCameraMode ? 'text-emerald-300 light:text-[#15803d]' : 'text-[#9aa2b5] light:text-slate-500'}`}>WEBCAM</span>
              <div className={`absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full ${activeCameraStream ? 'bg-emerald-400' : 'bg-slate-500'}`}/>
            </div>
            <div className="px-1.5 py-1 bg-[#121419] light:bg-white rounded-b-xl border-t border-[#272b37] light:border-[#d3d8e3]">
              <p className="text-[7px] font-mono text-emerald-400 light:text-[#15803d] truncate text-center font-semibold">Device Camera</p>
            </div>
          </div>

          <div className="h-10 w-px bg-[#272b37] light:bg-[#d3d8e3] mx-1 flex-shrink-0" />

          {/* Standard CCTV Camera Thumbnails */}
          {cameras.slice(0,7).map((cam)=>(
            <CameraThumbnail
              key={cam.id}
              cameraId={cam.id}
              location={cam.location}
              isActive={cam.id===selectedCamId && isCctvLive}
              isOnline={cam.status==='ONLINE'}
              onClick={()=>{
                if (isCameraMode) {
                  handleExitCameraMode();
                } else if (!isCctvLive) {
                  handleResetToLive();
                }
                setSelectedCam(cam.id);
              }}
            />
          ))}
        </div>
      </div>


      {/* Spatial Restricted Zone Configuration Modal */}
      <ZoneEditorModal
        sourceId={modalSource?.id || activeSourceId}
        sourceType={modalSource?.type || activeSourceType}
        sourceLabel={
          modalSource?.id
            ? `${modalSource.id} (${modalSource.type === 'WEBCAM' ? 'Webcam' : 'CCTV Camera'})`
            : isCameraMode
            ? 'Local Browser Webcam'
            : activeVideoId
            ? uploadedVideoName || `Video Clip ${activeVideoId.slice(0, 8)}`
            : `${selectedCamId} (${selectedCam?.location || 'CCTV Stream'})`
        }
        isOpen={isZoneEditorOpen}
        onClose={() => {
          setIsZoneEditorOpen(false);
          setModalSource(null);
        }}
      />
      {/* Add Camera Modal */}
      <AddCameraModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        initialSourceType={addModalSourceType}
      />
    </div>
  );
}

