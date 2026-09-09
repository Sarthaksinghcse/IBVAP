import { useMemo } from 'react';
import { useStore } from '../../store/useStore';
import type { Detection } from '../../types';
import { Activity, Loader2 } from 'lucide-react';
import { formatEventTime } from '../../utils/time';

// ─── Event type labels & colors ───────────────────────────────────────────────


const EVENT_SHORT: Record<string, { label: string; color: string }> = {
  WATCHLIST_MATCH:     { label: 'WATCHLIST MATCH',     color: 'text-red-500 font-bold' },
  UNKNOWN_FACE:        { label: 'UNKNOWN FACE',        color: 'text-slate-400' },
  FACE_DETECTED:       { label: 'FACE DETECTED',       color: 'text-cyan-400' },
  PLATE_DETECTED:      { label: 'PLATE IDENTIFIED',    color: 'text-indigo-400 font-bold' },
  UNREADABLE_PLATE:    { label: 'PLATE UNREADABLE',    color: 'text-slate-400' },
  ZONE_INTRUSION:      { label: 'ZONE INTRUSION',      color: 'text-red-400 font-bold' },
  LOITERING:           { label: 'LOITERING',           color: 'text-orange-400 font-bold' },

  PERSON_DETECTED:     { label: 'PERSON DETECTED',     color: 'text-green-400 font-semibold' },
  CAR_DETECTED:        { label: 'CAR DETECTED',        color: 'text-blue-400 font-semibold' },
  BICYCLE_DETECTED:    { label: 'BICYCLE DETECTED',    color: 'text-cyan-400 font-semibold' },
  MOTORCYCLE_DETECTED: { label: 'MOTORCYCLE DETECTED', color: 'text-blue-400 font-semibold' },
  BUS_DETECTED:        { label: 'BUS DETECTED',        color: 'text-indigo-400 font-semibold' },
  TRUCK_DETECTED:      { label: 'TRUCK DETECTED',      color: 'text-indigo-400 font-semibold' },
  VEHICLE_DETECTED:    { label: 'VEHICLE DETECTED',    color: 'text-blue-400 font-semibold' },
  DOG_DETECTED:        { label: 'DOG DETECTED',        color: 'text-amber-400 font-semibold' },
  CAT_DETECTED:        { label: 'CAT DETECTED',        color: 'text-amber-400 font-semibold' },
  BIRD_DETECTED:       { label: 'BIRD DETECTED',       color: 'text-cyan-400 font-semibold' },
  HORSE_DETECTED:      { label: 'HORSE DETECTED',      color: 'text-amber-400 font-semibold' },
  COW_DETECTED:        { label: 'COW DETECTED',        color: 'text-amber-400 font-semibold' },
  SHEEP_DETECTED:      { label: 'SHEEP DETECTED',      color: 'text-amber-400 font-semibold' },
  ANIMAL_DETECTED:     { label: 'ANIMAL DETECTED',     color: 'text-amber-400 font-semibold' },
  SUSPICIOUS_ACTIVITY: { label: 'SUSPICIOUS',          color: 'text-orange-400' },
  PERSON_TRACKED:      { label: 'PERSON TRACKED',      color: 'text-teal-400' },
  VEHICLE_TRACKED:     { label: 'VEHICLE TRACKED',     color: 'text-teal-400' },
  OBJECT_TRACKED:      { label: 'OBJECT TRACKED',      color: 'text-teal-400' },
  THREAT_CORRELATION:  { label: 'THREAT CORRELATED',   color: 'text-red-400' },
  THREAT_ESCALATION:   { label: 'THREAT ESCALATION',   color: 'text-red-400' },
};


export interface GroupedEvent {
  id: string;
  camera_id: string;
  video_id?: string;
  object_type: string;
  object_id: string;
  confidence: number;
  event_type: string;
  is_in_restricted_zone?: boolean;
  loitering_duration?: number;
  timestamp: string;
  video_time_sec?: number;
  plate_info?: import('../../types').ANPRPlateInfo | null;
}

// ─── Aggregation Helper ───────────────────────────────────────────────────────

function aggregateDetections(
  rawDetections: Detection[],
  isVideoMode: boolean,
  aiThreshold: number
): GroupedEvent[] {
  // 1. Filter by confidence threshold (preserve ANPR events even if detection conf is near boundary)
  const valid = rawDetections.filter(
    (d) => (typeof d.confidence === 'number' && d.confidence >= aiThreshold) || d.plate_info?.plate_detected
  );

  // 2. Sort chronologically
  const sorted = [...valid].sort((a, b) => {
    if (isVideoMode) {
      const at = a.video_time_sec ?? 0;
      const bt = b.video_time_sec ?? 0;
      return at - bt;
    }
    return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
  });

  const result: GroupedEvent[] = [];
  const lastLoggedTime = new Map<string, number>();
  const lastLoggedState = new Map<string, string>();

  for (const det of sorted) {
    const key = det.object_id || 'UNKNOWN';
    const currentTime = isVideoMode
      ? (det.video_time_sec ?? 0)
      : (new Date(det.timestamp).getTime() / 1000);

    const prevTime = lastLoggedTime.get(key);
    const prevState = lastLoggedState.get(key);

    // Derive or preserve exact event type from runtime inference
    let eventType = det.event_type;
    if (!eventType) {
      if (det.object_type === 'PERSON') eventType = 'PERSON_DETECTED';
      else if (det.object_id && det.object_id.startsWith('Car')) eventType = 'CAR_DETECTED';
      else if (det.object_id && det.object_id.startsWith('Dog')) eventType = 'DOG_DETECTED';
      else if (det.object_id && det.object_id.startsWith('Cat')) eventType = 'CAT_DETECTED';
      else if (det.object_id && det.object_id.startsWith('Truck')) eventType = 'TRUCK_DETECTED';
      else if (det.object_id && det.object_id.startsWith('Bus')) eventType = 'BUS_DETECTED';
      else if (det.object_id && det.object_id.startsWith('Motorcycle')) eventType = 'MOTORCYCLE_DETECTED';
      else if (det.object_id && det.object_id.startsWith('Bicycle')) eventType = 'BICYCLE_DETECTED';
      else if (det.object_type) eventType = `${det.object_type}_DETECTED`;
      else eventType = 'OBJECT_DETECTED';
    }

    let shouldLog = false;

    // Check if detection contains an active ANPR event
    const hasPlate = det.plate_info && det.plate_info.plate_detected;
    if (hasPlate) {
      eventType = det.plate_info?.plate_status === 'READABLE' ? 'PLATE_DETECTED' : 'UNREADABLE_PLATE';
    }

    const isReadablePlate = hasPlate && det.plate_info?.plate_status === 'READABLE' && Boolean(det.plate_info?.plate_text);

    if (prevTime == null) {
      // First time object is observed
      shouldLog = true;
    } else if (isReadablePlate && prevState !== 'PLATE_DETECTED') {
      // Transition to successfully identified plate
      eventType = 'PLATE_DETECTED';
      shouldLog = true;
    } else if (hasPlate && prevState !== 'PLATE_DETECTED' && prevState !== 'UNREADABLE_PLATE') {
      // First plate detection event
      shouldLog = true;
    } else if (det.is_in_restricted_zone && prevState !== 'ZONE_INTRUSION') {
      // Significant event transition to zone intrusion
      eventType = 'ZONE_INTRUSION';
      shouldLog = true;
    } else if (det.loitering_duration && det.loitering_duration > 0 && prevState !== 'LOITERING') {
      // Significant event transition to loitering
      eventType = 'LOITERING';
      shouldLog = true;
    } else if (currentTime - prevTime >= 6.0) {
      // Periodic heartbeat update
      shouldLog = true;
    }

    if (shouldLog) {
      lastLoggedTime.set(key, currentTime);
      lastLoggedState.set(key, eventType);
      result.push({
        id: det.id || `${key}-${currentTime}`,
        camera_id: det.camera_id,
        video_id: det.video_id,
        object_type: det.object_type,
        object_id: det.object_id,
        confidence: det.confidence,
        event_type: eventType,
        is_in_restricted_zone: det.is_in_restricted_zone,
        loitering_duration: det.loitering_duration,
        timestamp: det.timestamp,
        video_time_sec: det.video_time_sec,
        plate_info: det.plate_info,
      });
    }
  }

  // Return newest events first for live camera/webcam, chronological for uploaded video
  return isVideoMode ? result.slice(0, 50) : result.reverse().slice(0, 50);
}

// ─── Detection Row ────────────────────────────────────────────────────────────

function DetectionRow({
  det,
  isVideoMode,
  showConfidence,
}: {
  det: GroupedEvent;
  isVideoMode?: boolean;
  showConfidence?: boolean;
}) {
  const timeZone   = useStore((s) => s.timeZone);
  const timeFormat = useStore((s) => s.timeFormat);
  const meta = EVENT_SHORT[det.event_type] || { label: det.event_type, color: 'text-slate-400' };

  let timeLabel = '00:00:00';
  if (isVideoMode && det.video_time_sec != null) {
    const sec = typeof det.video_time_sec === 'number' ? det.video_time_sec : Number(det.video_time_sec);
    timeLabel = isNaN(sec) ? '00:00:00' : `T+${sec.toFixed(1)}s`;
  } else {
    timeLabel = formatEventTime(det.timestamp, timeZone, timeFormat, true);
  }

  // Specialized High-Visibility ANPR Event Card
  const isAnprEvent = det.event_type === 'PLATE_DETECTED' || det.event_type === 'UNREADABLE_PLATE' || Boolean(det.plate_info?.plate_detected);
  if (isAnprEvent) {
    const isReadable = det.plate_info?.plate_status === 'READABLE' && Boolean(det.plate_info?.plate_text);
    const isReading = det.plate_info?.plate_status === 'READING';
    const plateText = det.plate_info?.plate_text;
    const plateConf = det.plate_info?.plate_confidence;
    const safePlateConf = typeof plateConf === 'number' && !isNaN(plateConf) ? plateConf.toFixed(1) : (plateConf ? String(plateConf) : null);
    const safeDetConf = typeof det.confidence === 'number' && !isNaN(det.confidence) ? det.confidence.toFixed(1) : String(det.confidence ?? 0);

    return (
      <div className="py-2.5 px-2 border-b border-[#1e2d4a]/70 last:border-0 hover:bg-slate-800/30 transition-colors rounded-md my-0.5">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)] animate-pulse" />
            <span className="text-[11px] font-bold text-emerald-300 uppercase tracking-wider">Number Plate Detected</span>
          </div>
          <span className="text-[10px] font-mono text-slate-400">{timeLabel}</span>
        </div>

        <div className="flex items-center justify-between pl-3.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-bold text-slate-100">{det.object_id}</span>
            {isReadable ? (
              <span className="inline-flex items-center gap-1 bg-white text-slate-900 font-mono font-black text-xs px-2 py-0.5 rounded border border-slate-300 shadow-sm tracking-widest">
                <span className="bg-blue-700 text-white text-[8px] font-bold px-1 rounded-xs">IND</span>
                {plateText}
              </span>
            ) : isReading ? (
              <span className="text-[11px] font-mono font-medium text-sky-300 bg-sky-500/15 border border-sky-500/40 px-2 py-0.5 rounded flex items-center gap-1 animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-ping" />
                Reading...
              </span>
            ) : (
              <span className="text-[11px] font-mono font-medium text-amber-300 bg-amber-500/15 border border-amber-500/40 px-2 py-0.5 rounded">
                OCR unreadable
              </span>
            )}
          </div>

          {showConfidence && (
            <span className="text-[10px] font-mono text-slate-400">
              {isReadable && safePlateConf != null ? `OCR: ${safePlateConf}%` : `${safeDetConf}%`}
            </span>
          )}
        </div>
      </div>
    );
  }

  // Standard Target Observation Row
  const safeDetConf = typeof det.confidence === 'number' && !isNaN(det.confidence) ? det.confidence.toFixed(1) : String(det.confidence ?? 0);

  return (
    <div className="flex items-center gap-3 py-1.5 border-b border-[#1e2d4a]/60 last:border-0 transition-colors">
      {/* Timestamp */}
      <span className="text-[10px] font-mono text-slate-500 flex-shrink-0 w-16">
        {timeLabel}
      </span>

      {/* Event */}
      <span className={`text-[11px] font-medium ${meta.color} flex-shrink-0`}>
        {meta.label}
      </span>

      {/* Object */}
      <span className="text-[11px] text-slate-300 font-mono truncate flex-1">{det.object_id}</span>

      {/* Confidence */}
      {showConfidence && (
        <span className="text-[10px] font-mono text-slate-400 flex-shrink-0">
          {safeDetConf}%
        </span>
      )}

      {/* Threat dot */}
      {det.is_in_restricted_zone && (
        <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0 shadow-[0_0_6px_rgba(248,113,113,0.8)]" title="In restricted zone" />
      )}
    </div>
  );
}

// ─── Detection Log Panel ──────────────────────────────────────────────────────

interface DetectionLogProps {
  cameraId?: string;
}

export function DetectionLog({ cameraId }: DetectionLogProps) {
  const detections        = useStore((s) => s.detections);
  const activeVideoId     = useStore((s) => s.activeVideoId);
  const uploadStatus      = useStore((s) => s.uploadStatus);
  const cameraMode        = useStore((s) => s.cameraMode);
  const selectedCameraId  = useStore((s) => s.selectedCameraId);
  const settings          = useStore((s) => s.settings);

  const isAnalyzing = !cameraMode && !!activeVideoId && !!uploadStatus && uploadStatus !== 'COMPLETED' && uploadStatus !== 'ERROR';
  const isVideoMode = !cameraMode && !!activeVideoId && uploadStatus === 'COMPLETED';

  const liveSourceId = cameraMode ? (cameraId || 'WEBCAM-01') : (cameraId || selectedCameraId);

  // 1. Isolate active source detections (no cross-source leaking)
  const sourceDetections = useMemo(() => {
    return (isVideoMode || isAnalyzing)
      ? detections.filter((d) => d.video_id === activeVideoId)
      : cameraMode
      ? detections.filter((d) => d.camera_id === liveSourceId || d.camera_id === 'WEBCAM-01' || d.camera_id === 'webcam')
      : detections.filter((d) => d.camera_id === liveSourceId && !d.video_id);
  }, [detections, isVideoMode, isAnalyzing, activeVideoId, cameraMode, liveSourceId]);

  const cameras           = useStore((s) => s.cameras);
  const activeCam         = cameras.find((c) => c.id === liveSourceId);
  const isLiveStreamActive = cameraMode || Boolean(activeCam && activeCam.status === 'ONLINE');

  // 2. Aggregate frame observations into operator activity events (memoized)
  const aggregated = useMemo(() => {
    return aggregateDetections(
      sourceDetections,
      isVideoMode || isAnalyzing,
      settings.aiThreshold ?? 30
    );
  }, [sourceDetections, isVideoMode, isAnalyzing, settings.aiThreshold]);

  return (
    <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl flex flex-col h-full overflow-hidden shadow-card transition-colors">
      <div className="px-4 py-3 border-b border-[#272b37] light:border-[#d3d8e3] bg-[#191c24] light:bg-slate-50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-white light:text-slate-900">Detection Log</span>
          {isAnalyzing && (
            <span className="text-[9px] font-mono font-bold text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/30 flex items-center gap-1">
              <Loader2 size={9} className="animate-spin" />
              ANALYZING
            </span>
          )}
          {isVideoMode && (
            <span className="text-[9px] font-mono font-bold text-emerald-400 light:text-emerald-700 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/30">
              CCTV CLIP
            </span>
          )}
          {cameraMode && (
            <span className="text-[9px] font-mono font-bold text-emerald-400 light:text-emerald-700 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/30">
              WEBCAM
            </span>
          )}
          {!isAnalyzing && !isVideoMode && isLiveStreamActive && (
            <span className="text-[9px] font-mono font-bold text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded border border-cyan-500/30 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              YOLOv8 LIVE
            </span>
          )}
        </div>
        <span className="text-[10px] font-mono text-[#9aa2b5] light:text-slate-500">
          {isAnalyzing && aggregated.length === 0 ? 'Processing...' : `${aggregated.length} event${aggregated.length !== 1 ? 's' : ''} logged`}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-1">
        {isAnalyzing && aggregated.length === 0 ? (
          <div className="py-12 text-center">
            <div className="w-8 h-8 rounded-full bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center mx-auto mb-2 text-emerald-400">
              <Loader2 size={16} className="animate-spin" />
            </div>
            <p className="text-xs font-semibold text-emerald-400 light:text-emerald-700">Analyzing with YOLOv8...</p>
            <p className="text-[10px] text-[#9aa2b5] light:text-slate-500 mt-1">Extracting events and tracks from video frames</p>
          </div>
        ) : aggregated.length === 0 ? (
          <div className="py-12 text-center">
            <div className={`w-8 h-8 rounded-full ${isLiveStreamActive ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400' : 'bg-[#191c24] light:bg-slate-100 border-[#272b37] light:border-slate-300 text-[#62697b] light:text-slate-400'} border flex items-center justify-center mx-auto mb-2`}>
              <Activity size={16} className={isLiveStreamActive ? 'animate-pulse' : ''} />
            </div>
            <p className="text-xs font-medium text-white light:text-slate-800">
              {isLiveStreamActive ? 'Live AI Surveillance Active' : 'Waiting for AI detection...'}
            </p>
            <p className="text-[10px] text-[#9aa2b5] light:text-slate-500 mt-1">
              {isLiveStreamActive ? 'Continuous inference running — no targets currently in view' : 'No objects currently visible in camera feed'}
            </p>
          </div>
        ) : (
          <>
            {isAnalyzing && (
              <div className="flex items-center gap-2 px-2.5 py-1.5 my-1 bg-amber-500/10 border border-amber-500/30 rounded-lg text-[10px] font-mono text-amber-300">
                <Loader2 size={12} className="animate-spin text-amber-400 flex-shrink-0" />
                <span>Live video analysis in progress — streaming real-time detections</span>
              </div>
            )}
            {aggregated.map((det) => (
              <DetectionRow
                key={det.id}
                det={det}
                isVideoMode={isVideoMode || isAnalyzing}
                showConfidence={settings.showConfidence ?? true}
              />
            ))}
          </>
        )}
      </div>
    </div>
  );

}


