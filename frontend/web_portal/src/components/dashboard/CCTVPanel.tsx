import { useState, useRef, useMemo, useEffect, useCallback } from 'react';
import { Loader2, Camera, Video, VideoOff, AlertCircle, RotateCcw, ArrowLeft, ShieldAlert, LayoutGrid, Maximize2, Plus, WifiOff, Route } from 'lucide-react';
import { useStore } from '../../store/useStore';
import { LiveBadge } from '../ui/Badge';
import { ZoneEditorModal } from '../monitoring/ZoneEditorModal';
import { AddCameraModal } from '../cameras/AddCameraModal';
import { MultiCameraGrid } from './MultiCameraGrid';
import * as api from '../../services/api';
import type { Detection, Zone } from '../../types';
import { playRestrictedZonePersonBeep } from '../../utils/audio';

/**
 * Test whether a point (x, y) in percentage [0..100] is inside a polygon.
 */
function isPointInPolygon(point: [number, number], vs: [number, number][]): boolean {
  const x = point[0], y = point[1];
  let inside = false;
  for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
    const xi = vs[i][0], yi = vs[i][1];
    const xj = vs[j][0], yj = vs[j][1];
    const intersect = ((yi > y) !== (yj > y)) &&
      (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

/**
 * Check if two line segments (p1, p2) and (p3, p4) intersect.
 */
function doSegmentsIntersect(
  p1: [number, number],
  p2: [number, number],
  p3: [number, number],
  p4: [number, number]
): boolean {
  const ccw = (a: [number, number], b: [number, number], c: [number, number]) =>
    (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0]);

  return (
    ccw(p1, p3, p4) !== ccw(p2, p3, p4) &&
    ccw(p1, p2, p3) !== ccw(p1, p2, p4)
  );
}

/**
 * Robust spatial overlap test between a bounding box and a polygon.
 * Evaluates:
 * 1. Multiple key human probe points (centroid, chest, head, feet, 4 corners, 4 edge centers).
 * 2. Any polygon vertex residing inside the bounding box.
 * 3. Line segment intersection between any box edge and any polygon edge.
 */
function doesBoxOverlapPolygon(bbox: { x: number; y: number; w: number; h: number }, poly: [number, number][]): boolean {
  if (!poly || poly.length < 3) return false;

  const bx1 = bbox.x;
  const by1 = bbox.y;
  const bx2 = bbox.x + bbox.w;
  const by2 = bbox.y + bbox.h;
  const cx = bbox.x + bbox.w / 2;
  const cy = bbox.y + bbox.h / 2;

  // 1. Check probe points of the detection inside the polygon
  const probePoints: [number, number][] = [
    [cx, cy],                           // Center
    [cx, by2],                          // Feet / bottom-center
    [cx, by1 + bbox.h * 0.3],           // Chest / torso
    [cx, by1 + bbox.h * 0.15],          // Head
    [bx1, by1],                         // Top-Left
    [bx2, by1],                         // Top-Right
    [bx1, by2],                         // Bottom-Left
    [bx2, by2],                         // Bottom-Right
    [bx1, cy],                          // Mid-Left
    [bx2, cy],                          // Mid-Right
  ];

  for (const pt of probePoints) {
    if (isPointInPolygon(pt, poly)) return true;
  }

  // 2. Check if any polygon vertex is contained inside the bounding box
  for (const [px, py] of poly) {
    if (px >= bx1 && px <= bx2 && py >= by1 && py <= by2) {
      return true;
    }
  }

  // 3. Check if any box edge intersects any polygon edge
  const boxEdges: [[number, number], [number, number]][] = [
    [[bx1, by1], [bx2, by1]],
    [[bx2, by1], [bx2, by2]],
    [[bx2, by2], [bx1, by2]],
    [[bx1, by2], [bx1, by1]],
  ];

  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const polyEdgeStart = poly[j];
    const polyEdgeEnd = poly[i];
    for (const [boxStart, boxEnd] of boxEdges) {
      if (doSegmentsIntersect(boxStart, boxEnd, polyEdgeStart, polyEdgeEnd)) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Determine if a detected object is a person located inside the restricted perimeter zone.
 */
function isPersonInRestrictedZone(det: Detection, zone?: Zone | null): boolean {
  if (det.object_type !== 'PERSON') return false;
  // If explicitly flagged by backend AI ThreatEngine or zone event
  if (det.is_in_restricted_zone || det.event_type === 'ZONE_INTRUSION') {
    return true;
  }
  // If active polygon coordinates exist (supports both coordinates & polygon aliases)
  const coords = zone?.coordinates || (zone as unknown as { polygon?: [number, number][] })?.polygon;
  if (zone && zone.enabled !== false && coords && coords.length >= 3) {
    return doesBoxOverlapPolygon(det.bbox, coords);
  }
  return false;
}

// BoundingBox
function BoundingBox({ det, showConfidence = true }: { det: Detection; showConfidence?: boolean }) {
  const isIntrusion = det.is_in_restricted_zone || det.event_type === 'ZONE_INTRUSION';
  const isLoitering = det.loitering_duration && det.loitering_duration > 0;
  const isVehicle   = det.object_type === 'VEHICLE';
  const faceMatch   = det.face_match;
  const isWatchlist = Boolean(faceMatch && faceMatch.is_match);
  const isUnknownFace = Boolean(faceMatch && !faceMatch.is_match && faceMatch.person_name === 'UNKNOWN');
  const plateInfo   = det.plate_info;
  const behaviourLabel = det.behaviour_label;

  const boxClass    = isWatchlist ? 'border-red-600 animate-pulse ring-2 ring-red-500' : isIntrusion ? 'bbox-intrusion' : isLoitering ? 'bbox-loitering' : isVehicle ? 'bbox-vehicle' : 'bbox-person';
  const labelBg     = isWatchlist ? 'bg-red-700' : isIntrusion ? 'bg-red-500' : isLoitering ? 'bg-orange-500' : isVehicle ? 'bg-blue-500' : 'bg-green-600';
  const cornerColor = isWatchlist ? '#dc2626' : isIntrusion ? '#ef4444' : isVehicle ? '#3b82f6' : '#22c55e';

  return (
    <div className={`absolute border-2 ${boxClass} pointer-events-none`} style={{ left: `${det.bbox.x}%`, top: `${det.bbox.y}%`, width: `${det.bbox.w}%`, height: `${det.bbox.h}%` }}>
      {[{top:-1,left:-1,borderTop:`2px solid ${cornerColor}`,borderLeft:`2px solid ${cornerColor}`},{top:-1,right:-1,borderTop:`2px solid ${cornerColor}`,borderRight:`2px solid ${cornerColor}`},{bottom:-1,left:-1,borderBottom:`2px solid ${cornerColor}`,borderLeft:`2px solid ${cornerColor}`},{bottom:-1,right:-1,borderBottom:`2px solid ${cornerColor}`,borderRight:`2px solid ${cornerColor}`}].map((s,i)=>(<span key={i} className="absolute w-2 h-2" style={s}/>))}
      <div className={`absolute -top-5 left-0 ${labelBg} text-white text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-sm whitespace-nowrap flex items-center gap-1 shadow-md`}>
        <span>{isWatchlist && faceMatch ? `🔴 WATCHLIST: ${faceMatch.person_name}` : det.object_id}</span>
        {showConfidence && (
          <>
            <span className="opacity-75">•</span>
            <span>{isWatchlist && faceMatch ? `${faceMatch.similarity.toFixed(1)}% match` : `${typeof det.confidence==='number'?det.confidence.toFixed(1):det.confidence}%`}</span>
          </>
        )}
        {behaviourLabel && behaviourLabel !== 'NORMAL_TRANSIT' && (
          <>
            {(behaviourLabel === 'RUNNING' || behaviourLabel === 'CIRCLING') ? (
              <span className="ml-1 bg-red-600/90 text-white font-bold px-1 rounded-xs text-[8px] flex items-center gap-0.5 animate-pulse border border-red-400/50">
                <span className="w-1.5 h-1.5 rounded-full bg-red-200 animate-ping" />
                🔴 {behaviourLabel}
              </span>
            ) : (
              <span className="ml-1 bg-amber-500/90 text-slate-950 font-bold px-1 rounded-xs text-[8px] flex items-center gap-0.5">
                🟡 {behaviourLabel}
              </span>
            )}
          </>
        )}
        {det.velocity != null && det.velocity > 0 && (
          <span className="ml-0.5 opacity-80 font-mono text-[8px] bg-black/40 px-1 rounded-xs">
            {det.velocity}%/s
          </span>
        )}
        {isIntrusion && <span className="ml-1 bg-red-700/90 px-1 rounded-xs">🚨 ZONE INTRUSION</span>}
        {isUnknownFace && !isWatchlist && <span className="ml-1 bg-slate-700/80 px-1 rounded-xs text-[8px]">👤 FACE: UNKNOWN</span>}
        {isVehicle && plateInfo && plateInfo.plate_status === 'READABLE' && plateInfo.plate_text && (
          <span className="ml-1 bg-white text-slate-900 font-bold px-1.5 py-0.2 rounded-xs text-[8px] flex items-center gap-1 shadow-sm border border-slate-300">
            <span className="bg-blue-700 text-white text-[7px] px-0.5 rounded-xs">IND</span>
            <span>PLATE: {plateInfo.plate_text}</span>
            {plateInfo.plate_confidence != null && <span className="text-slate-600 font-medium">• OCR: {plateInfo.plate_confidence.toFixed(1)}%</span>}
          </span>
        )}
        {isVehicle && plateInfo && (plateInfo.plate_status === 'UNREADABLE' || plateInfo.plate_status === 'UNCERTAIN') && (
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
  const coords = zone?.coordinates || (zone as unknown as { polygon?: [number, number][] })?.polygon;
  if (!zone || !coords || coords.length < 3 || zone.enabled === false) return null;
  const pointsStr = coords.map(([x, y]) => `${x},${y}`).join(' ');

  const minX = Math.min(...coords.map((c) => c[0]));
  const minY = Math.min(...coords.map((c) => c[1]));

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

function TrajectoryOverlay({ detections, showTrajectories }: { detections: Detection[]; showTrajectories: boolean }) {
  if (!showTrajectories || detections.length === 0) return null;

  const tracksWithTraj = detections.filter(
    (d) => d.trajectory && d.trajectory.length >= 2
  );

  if (tracksWithTraj.length === 0) return null;

  return (
    <div className="absolute inset-0 pointer-events-none z-14 overflow-hidden">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
        <defs>
          <filter id="trajGlow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="0.4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>
        {tracksWithTraj.map((det) => {
          const b = det.behaviour_label;
          const color =
            b === 'RUNNING' ? '#ef4444' :
            b === 'CIRCLING' ? '#f97316' :
            b === 'PACING' ? '#eab308' :
            b === 'ERRATIC_MOVEMENT' ? '#c084fc' :
            b === 'STATIONARY' ? '#94a3b8' :
            '#10b981';

          const pointsStr = det.trajectory!.map(([x, y]) => `${x},${y}`).join(' ');
          const firstPoint = det.trajectory![0];
          const lastPoint = det.trajectory![det.trajectory!.length - 1];

          return (
            <g key={`traj-${det.id || det.object_id}`}>
              {/* Diffuse glow line */}
              <polyline
                points={pointsStr}
                fill="none"
                stroke={color}
                strokeWidth="0.8"
                opacity="0.35"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {/* Sharp primary trajectory path */}
              <polyline
                points={pointsStr}
                fill="none"
                stroke={color}
                strokeWidth="0.45"
                strokeDasharray={b === 'ERRATIC_MOVEMENT' ? '1.5,0.8' : undefined}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity="0.9"
                filter="url(#trajGlow)"
              />
              {/* Origin anchor dot */}
              <circle
                cx={firstPoint[0]}
                cy={firstPoint[1]}
                r="0.5"
                fill={color}
                opacity="0.5"
              />
              {/* Target current position dot */}
              <circle
                cx={lastPoint[0]}
                cy={lastPoint[1]}
                r="0.85"
                fill={color}
                opacity="0.9"
              />
              <circle
                cx={lastPoint[0]}
                cy={lastPoint[1]}
                r="0.45"
                fill="#ffffff"
              />
            </g>
          );
        })}
      </svg>
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
  const videoAnalysisMetrics     = useStore((s) => s.videoAnalysisMetrics);




  // Zones State from store
  const zones             = useStore((s) => s.zones);
  const fetchZones        = useStore((s) => s.fetchZones);
  const [isZoneEditorOpen, setIsZoneEditorOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [modalSource, setModalSource] = useState<{ id: string; type: 'CAMERA' | 'WEBCAM' | 'VIDEO' } | null>(null);
  const [viewMode, setViewMode] = useState<'FOCUS' | 'GRID'>('FOCUS');
  const [showTrajectories, setShowTrajectories] = useState(true);


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
  const activeCoords = activeZone?.coordinates || (activeZone as unknown as { polygon?: [number, number][] })?.polygon;
  const hasZoneConfigured = Boolean(activeZone && activeCoords && activeCoords.length >= 3 && activeZone.enabled !== false);
  const showRestrictedZone = settings.showRestrictedZone && hasZoneConfigured;
  const hasIntrusion = activeFrameDetections.some((d) => d.is_in_restricted_zone);

  // Synchronized refs so asynchronous inference intervals & requestAnimationFrames never suffer from stale closures
  const activeZoneRef = useRef<Zone | undefined>(activeZone);
  activeZoneRef.current = activeZone;

  const settingsRef = useRef(settings);
  settingsRef.current = settings;



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

  // Real Laptop Webcam YOLOv8 AI Inference Loop (~8 FPS, 640x360, async lock, sequence ordering)
  useEffect(() => {
    if (!isCameraMode || !activeCameraStream) {
      // Only reset refs — NO Zustand state mutations here (they cause infinite loops)
      setActiveFrameDetections([]);
      frameSeqRef.current = 0;
      latestRenderedSeqRef.current = 0;
      if (webcamAiActiveRef.current) {
        webcamAiActiveRef.current = false;
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
        const currentSettings = settingsRef.current;
        const currentZone = activeZoneRef.current;
        const confThreshold = (currentSettings.aiThreshold || 50) / 100;
        const faceEnabled = currentSettings.faceRecognitionEnabled ?? true;
        const faceThreshold = (currentSettings.faceMatchThreshold ?? 45) / 100;
        const anprEnabled = currentSettings.anprEnabled ?? true;

        const res = await api.inferWebcamFrame(
          base64Data,
          confThreshold,
          currentSeq,
          faceEnabled,
          faceThreshold,
          anprEnabled
        );

        if (!isMounted) return;

        // Mark AI as running on first successful response
        if (!webcamAiActiveRef.current) {
          webcamAiActiveRef.current = true;
          setSystemStatus({ ai_engine_status: 'RUNNING' });
        }

        if (res && res.frame_seq >= latestRenderedSeqRef.current) {
          latestRenderedSeqRef.current = res.frame_seq;
          const allDets = (res.detections || []) as Detection[];
          const threshold = currentSettings.aiThreshold || 50;
          const filtered = allDets.filter(
            (d) => typeof d.confidence === 'number' && d.confidence >= threshold
          );

          // Decorate detections in real-time with restricted zone status
          const decorated = filtered.map((d) => {
            const inZone = isPersonInRestrictedZone(d, currentZone);
            return inZone
              ? {
                  ...d,
                  is_in_restricted_zone: true,
                  event_type: d.event_type === 'WATCHLIST_MATCH' ? d.event_type : ('ZONE_INTRUSION' as const),
                }
              : d;
          });

          // Update bounding boxes (local state only — no Zustand array replacement)
          setActiveFrameDetections(decorated);
          setActiveTracksForSource('WEBCAM-01', decorated);

          // Acoustic Beep when a PERSON enters or is detected inside the restricted zone
          const hasPersonInZone = decorated.some((d) => isPersonInRestrictedZone(d, currentZone));
          if (hasPersonInZone && (currentSettings.personBeep ?? true)) {
            playRestrictedZonePersonBeep();
          }

          // Push significant events into store using addDetection (append, not replace)
          const now = Date.now() / 1000;
          for (const det of decorated) {
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
      } finally {
        inFlightRef.current = false;
      }
    }, 125); // ~8 FPS

    return () => {
      isMounted = false;
      clearInterval(intervalId);
      // Cleanup: NO state mutations — refs only, to avoid triggering re-renders
      webcamAiActiveRef.current = false;
      setActiveTracksForSource('WEBCAM-01', []);
      api.resetWebcamSession().catch(() => {});
    };
  }, [isCameraMode, activeCameraStream, settings.aiThreshold, setSystemStatus, addDetection, setActiveTracksForSource]);

  // Frame sync loop using requestAnimationFrame for Uploaded Videos / CCTV
  useEffect(() => {
    if (isCameraMode) {
      return;
    }

    if (isCctvLive) {
      const currentZone = activeZoneRef.current;
      const currentSettings = settingsRef.current;
      const liveDets = detections.filter((d) => d.camera_id === selectedCamId && !d.video_id).slice(0, 5);
      const decorated = liveDets.map((d) => {
        const inZone = isPersonInRestrictedZone(d, currentZone);
        return inZone
          ? {
              ...d,
              is_in_restricted_zone: true,
              event_type: d.event_type === 'WATCHLIST_MATCH' ? d.event_type : ('ZONE_INTRUSION' as const),
            }
          : d;
      });
      setActiveFrameDetections(decorated);
      if (selectedCamId) setActiveTracksForSource(selectedCamId, decorated);
      const hasPersonInZone = decorated.some((d) => isPersonInRestrictedZone(d, currentZone));
      if (hasPersonInZone && (currentSettings.personBeep ?? true)) {
        playRestrictedZonePersonBeep();
      }
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
          const currentZone = activeZoneRef.current;
          const currentSettings = settingsRef.current;
          const filtered = Array.from(uniqueMap.values()).filter(
            (d) => typeof d.confidence === 'number' && d.confidence >= (currentSettings.aiThreshold || 50)
          );
          const decorated = filtered.map((d) => {
            const inZone = isPersonInRestrictedZone(d, currentZone);
            return inZone
              ? {
                  ...d,
                  is_in_restricted_zone: true,
                  event_type: d.event_type === 'WATCHLIST_MATCH' ? d.event_type : ('ZONE_INTRUSION' as const),
                }
              : d;
          });
          setActiveFrameDetections(decorated);
          if (activeVideoId) {
            setActiveTracksForSource(activeVideoId, decorated);
          }

          // Acoustic Beep when a PERSON enters or is detected inside the restricted zone
          const hasPersonInZone = decorated.some((d) => isPersonInRestrictedZone(d, currentZone));
          if (hasPersonInZone && (currentSettings.personBeep ?? true)) {
            playRestrictedZonePersonBeep();
          }
        }
      }
      animId = requestAnimationFrame(syncLoop);
    };
    animId = requestAnimationFrame(syncLoop);
    return () => cancelAnimationFrame(animId);
  }, [isCctvLive, isCameraMode, isVideoReady, videoDetsSorted, frameDuration, detections, selectedCamId, activeVideoId, settings.aiThreshold, setActiveTracksForSource]);

  const handleResetToLive = async () => {
    setActiveVideoUrl(null);
    setActiveVideoId(null);
    setUploadedName(null);
    setUploadStatus(null);
    setCurrentPlaybackTime(0);
    setVideoDuration(0);
    setActiveFrameDetections([]);
    setCameraMode(false);
    try {
      const liveDets = await api.getDetections(selectedCamId);
      setDetections(liveDets);
    } catch (e) {
      console.warn('[CCTVPanel] Failed to reload live detections:', e);
    }
  };

  const handleEnterCameraMode = async () => {
    setCameraMode(true);
    await startDeviceCamera();
    enumerateCameraDevices().catch(() => {});
  };

  const handleExitCameraMode = () => {
    stopDeviceCamera();
    setCameraMode(false);
    setActiveFrameDetections([]);
  };

  const handleStopCamera = () => {
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
                Browser Device Camera
              </span>
              <span className="text-[#62697b] light:text-slate-400">•</span>
              <span className="text-xs text-[#9aa2b5] light:text-slate-600">
                {cameraResolution || 'Webcam Stream'}
              </span>
              <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 light:bg-emerald-100 light:text-emerald-700 text-[10px] font-mono font-bold uppercase flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                DEVICE INPUT
              </span>
            </>
          ) : (
            <>
              <span className="text-sm font-semibold text-white light:text-slate-900">{selectedCamId}</span>
              <span className="text-[#62697b] light:text-slate-400">•</span>
              <span className="text-xs text-[#9aa2b5] light:text-slate-600">
                {(isAnalyzing||isVideoReady)&&uploadedVideoName ? uploadedVideoName : (selectedCam?.location||'Unknown')}
              </span>
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

              {/* Trajectory Motion Trails Toggle Button */}
              <button
                type="button"
                onClick={() => setShowTrajectories((prev) => !prev)}
                className={`text-[10px] font-mono px-2 py-1 rounded-lg border transition-all flex items-center gap-1.5 cursor-pointer shadow-xs font-semibold ${
                  showTrajectories
                    ? 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 light:text-emerald-700 border-emerald-500/30 light:border-emerald-200 light:bg-emerald-50'
                    : 'bg-[#191c24] light:bg-slate-100 hover:bg-slate-700 light:hover:bg-slate-200 text-[#9aa2b5] light:text-slate-700 border-[#272b37] light:border-[#d9dde3]'
                }`}
                title="Toggle real-time trajectory motion breadcrumbs"
              >
                <Route size={12} className={showTrajectories ? 'text-emerald-400 light:text-emerald-600' : 'text-[#9aa2b5] light:text-slate-500'} />
                <span>Trails {showTrajectories ? 'ON' : 'OFF'}</span>
              </button>

              <span className="text-[10px] font-mono text-[#9aa2b5] light:text-slate-500 font-medium">{systemStatus.fps.toFixed(1)} FPS • {systemStatus.processing_time_ms}ms</span>
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
                      onPlaying={() => requestAnimationFrame(() => updateContentRect())}
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
                src={`/api/cameras/${selectedCamId}/stream`}
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
                  SHIELD starts with zero predefined cameras. Connect a CCTV camera via RTSP, a phone camera over Wi-Fi, or your laptop webcam.
                </p>
                <div className="flex items-center gap-2 flex-wrap justify-center">
                  <button
                    onClick={handleEnterCameraMode}
                    className="text-xs py-1.5 px-3 rounded font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-all flex items-center gap-1 cursor-pointer"
                  >
                    <Camera size={13} /> Use Laptop Webcam
                  </button>
                  <button
                    onClick={() => setIsAddModalOpen(true)}
                    className="text-xs py-1.5 px-3 rounded font-medium bg-[#1d6af5] hover:bg-[#1655c7] text-white transition-all flex items-center gap-1 cursor-pointer"
                  >
                    <Video size={13} /> + Add Camera Feed
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
                <TrajectoryOverlay detections={activeFrameDetections} showTrajectories={showTrajectories} />
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
            {isCameraMode ? 'Local MediaStream (Direct Camera)' : systemStatus.model_name}
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
      />
    </div>
  );
}

