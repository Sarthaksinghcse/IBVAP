import type { ThreatLevel, AlertStatus, CameraStatus, AIStatus, VideoStatus } from '../../types';

// ─── Threat Level Badge ───────────────────────────────────────────────────────

interface ThreatBadgeProps {
  level: ThreatLevel;
  size?: 'sm' | 'md';
}

const THREAT_STYLES: Record<ThreatLevel, string> = {
  CRITICAL: 'bg-red-500/15 text-red-400 border border-red-500/30 light:bg-red-50 light:text-red-700 light:border-red-200',
  HIGH:     'bg-orange-500/15 text-orange-400 border border-orange-500/30 light:bg-orange-50 light:text-orange-700 light:border-orange-200',
  MEDIUM:   'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 light:bg-amber-50 light:text-amber-700 light:border-amber-200',
  LOW:      'bg-green-500/15 text-green-400 border border-green-500/30 light:bg-emerald-50 light:text-emerald-700 light:border-emerald-200',
  NONE:     'bg-slate-500/15 text-slate-400 border border-slate-500/30 light:bg-slate-100 light:text-slate-700 light:border-slate-300',
};

export function ThreatBadge({ level, size = 'sm' }: ThreatBadgeProps) {
  const sz = size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs';
  return (
    <span className={`inline-flex items-center gap-1 rounded-md font-mono font-bold uppercase tracking-wide ${sz} ${THREAT_STYLES[level]}`}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'currentColor' }} />
      {level}
    </span>
  );
}

// ─── Alert Status Badge ────────────────────────────────────────────────────────

const STATUS_STYLES: Record<AlertStatus, string> = {
  NEW:                 'bg-red-500/10 text-red-400 border border-red-500/25 light:bg-red-50 light:text-red-700 light:border-red-200',
  ACKNOWLEDGED:        'bg-blue-500/10 text-blue-400 border border-blue-500/25 light:bg-blue-50 light:text-blue-700 light:border-blue-200',
  UNDER_INVESTIGATION: 'bg-orange-500/10 text-orange-400 border border-orange-500/25 light:bg-orange-50 light:text-orange-700 light:border-orange-200',
  RESOLVED:            'bg-green-500/10 text-green-400 border border-green-500/25 light:bg-emerald-50 light:text-emerald-700 light:border-emerald-200',
};

const STATUS_LABELS: Record<AlertStatus, string> = {
  NEW: 'New',
  ACKNOWLEDGED: 'Acknowledged',
  UNDER_INVESTIGATION: 'Investigating',
  RESOLVED: 'Resolved',
};

interface StatusBadgeProps { status: AlertStatus; }

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono font-semibold ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}

// ─── Camera Status Badge ───────────────────────────────────────────────────────

const CAM_STATUS: Record<CameraStatus, string> = {
  ONLINE:      'bg-green-500/10 text-green-400 border border-green-500/25 light:bg-emerald-50 light:text-emerald-700 light:border-emerald-200',
  OFFLINE:     'bg-red-500/10 text-red-400 border border-red-500/25 light:bg-red-50 light:text-red-700 light:border-red-200',
  MAINTENANCE: 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/25 light:bg-amber-50 light:text-amber-700 light:border-amber-200',
  ERROR:       'bg-red-500/10 text-red-400 border border-red-500/25 light:bg-red-50 light:text-red-700 light:border-red-200',
};

export function CameraStatusBadge({ status }: { status: CameraStatus }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono font-semibold ${CAM_STATUS[status]}`}>{status}</span>
  );
}

// ─── AI Status Badge ───────────────────────────────────────────────────────────

const AI_STATUS: Record<AIStatus, string> = {
  RUNNING: 'bg-green-500/10 text-green-400 border border-green-500/25 light:bg-emerald-50 light:text-emerald-700 light:border-emerald-200',
  STOPPED: 'bg-slate-500/10 text-slate-400 border border-slate-500/25 light:bg-slate-100 light:text-slate-700 light:border-slate-300',
  ERROR:   'bg-red-500/10 text-red-400 border border-red-500/25 light:bg-red-50 light:text-red-700 light:border-red-200',
};

export function AIStatusBadge({ status }: { status: AIStatus }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono font-semibold ${AI_STATUS[status]}`}>
      {status === 'RUNNING' && (
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-[livePulse_2s_ease-in-out_infinite]" />
      )}
      AI: {status}
    </span>
  );
}

// ─── Video Status Badge ────────────────────────────────────────────────────────

const VID_STATUS: Record<VideoStatus, string> = {
  READY:        'bg-slate-500/10 text-slate-400 border border-slate-500/25 light:bg-slate-100 light:text-slate-700 light:border-slate-300',
  UPLOADING:    'bg-blue-500/10 text-blue-400 border border-blue-500/25 light:bg-blue-50 light:text-blue-700 light:border-blue-200',
  PROCESSING:   'bg-yellow-500/10 text-yellow-400 border border-yellow-500/25 light:bg-amber-50 light:text-amber-700 light:border-amber-200',
  AI_ANALYZING: 'bg-purple-500/10 text-purple-400 border border-purple-500/25 light:bg-purple-50 light:text-purple-700 light:border-purple-200',
  COMPLETED:    'bg-green-500/10 text-green-400 border border-green-500/25 light:bg-emerald-50 light:text-emerald-700 light:border-emerald-200',
  CANCELLED:    'bg-slate-600/10 text-slate-400 border border-slate-600/25 light:bg-slate-100 light:text-slate-600 light:border-slate-300',
  ERROR:        'bg-red-500/10 text-red-400 border border-red-500/25 light:bg-red-50 light:text-red-700 light:border-red-200',
};

export function VideoStatusBadge({ status }: { status: VideoStatus }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-mono font-semibold ${VID_STATUS[status]}`}>{status}</span>
  );
}

// ─── Live Indicator Badge ──────────────────────────────────────────────────────

export function LiveBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[9px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 light:bg-emerald-50 light:text-emerald-700 light:border-emerald-200 uppercase tracking-wider">
      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)] animate-pulse" />
      LIVE
    </span>
  );
}

