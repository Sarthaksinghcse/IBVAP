import { useState } from 'react';
import { AlertTriangle, Clock, MapPin, User, Car, Camera, Maximize2, X, Download, ShieldAlert, Zap } from 'lucide-react';
import { ThreatBadge, StatusBadge } from '../ui/Badge';
import { useStore } from '../../store/useStore';
import { formatRelativeTime, formatEventTime, formatHistoryTimestamp } from '../../utils/time';
import type { Alert } from '../../types';

const EVENT_LABELS: Record<string, string> = {
  WATCHLIST_MATCH:     'Watchlist Target Identified',
  ZONE_INTRUSION:      'Restricted Zone Intrusion',
  LOITERING:           'Loitering Detected',
  PERSON_DETECTED:     'Person Detected',
  VEHICLE_DETECTED:    'Vehicle Detected',
  SUSPICIOUS_ACTIVITY: 'Suspicious Activity',
  PERSON_TRACKED:      'Person Tracked',
  VEHICLE_TRACKED:     'Vehicle Tracked',
  THREAT_CORRELATION:  'Threat Correlation',
  PLATE_DETECTED:      'License Plate Detected',
  UNREADABLE_PLATE:    'Unreadable License Plate',
  WATCHLIST_PLATE_MATCH:'Watchlist Vehicle Breach',
};

export function getSnapshotUrl(path?: string): string | null {
  if (!path) return null;
  if (path.startsWith('data:') || path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const backendBase = window.location.port === '5173' ? 'http://localhost:8000' : '';
  return `${backendBase}${cleanPath}`;
}

const ObjectIcon = ({ type }: { type: string }) =>
  type === 'VEHICLE' ? <Car size={12} /> : <User size={12} />;

// ─── Compact / Standard Alert Card ───────────────────────────────────────────

interface AlertCardProps {
  alert: Alert;
  onClick?: () => void;
  isSelected?: boolean;
  compact?: boolean;
}

export function AlertCard({ alert, onClick, isSelected, compact = false }: AlertCardProps) {
  const timeZone   = useStore((s) => s.timeZone);
  const timeFormat = useStore((s) => s.timeFormat);

  const borderLeftColor =
    alert.threat_level === 'CRITICAL' ? 'border-l-red-500'    :
    alert.threat_level === 'HIGH'     ? 'border-l-orange-500' :
    alert.threat_level === 'MEDIUM'   ? 'border-l-yellow-500' :
                                        'border-l-emerald-500';

  const snapshotUrl = getSnapshotUrl(alert.snapshot_path);

  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        w-full text-left border-l-4 ${borderLeftColor}
        ${compact ? 'p-2.5' : 'p-3.5'}
        rounded-r-xl border-y border-r transition-all duration-150 cursor-pointer shadow-xs
        ${isSelected
          ? 'bg-[#13271d] light:bg-[#ecfdf5] border-y-[#22c55e]/40 border-r-[#22c55e]/40'
          : 'bg-[#121419] light:bg-white border-y-[#272b37] border-r-[#272b37] light:border-y-[#d3d8e3] light:border-r-[#d3d8e3] hover:border-slate-500 light:hover:border-slate-400'
        }
      `}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {/* Event type & Badges */}
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            <ThreatBadge level={alert.threat_level} />
            <span className={`font-semibold text-white light:text-slate-900 truncate ${compact ? 'text-xs' : 'text-sm'}`}>
              {EVENT_LABELS[alert.event_type] || alert.event_type}
            </span>
            {alert.behaviour_label && alert.behaviour_label !== 'NORMAL_TRANSIT' && (
              <span className={`text-[9px] font-mono font-bold px-1.5 py-0.2 rounded-xs flex items-center gap-0.5 ${
                alert.behaviour_label === 'RUNNING' || alert.behaviour_label === 'CIRCLING'
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                  : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
              }`}>
                <Zap size={9} /> {alert.behaviour_label}
              </span>
            )}
            {snapshotUrl && (
              <span className="text-[9px] font-mono text-emerald-400 light:text-emerald-700 bg-emerald-500/15 light:bg-emerald-50 border border-emerald-500/30 px-1 py-0.2 rounded flex items-center gap-1">
                <Camera size={9} /> Snapshot
              </span>
            )}
          </div>

          {/* Meta */}
          <div className={`flex items-center gap-3 text-[#9aa2b5] light:text-slate-500 ${compact ? 'text-[10px]' : 'text-xs'}`}>
            <span className="flex items-center gap-1">
              <MapPin size={10} /> {alert.camera_id}
            </span>
            <span className="flex items-center gap-1">
              <ObjectIcon type={alert.object_type} /> {alert.object_id}
            </span>
          </div>

          {/* Reason preview (non-compact only) */}
          {!compact && (
            <p className="text-[11px] text-[#9aa2b5] light:text-slate-600 mt-1.5 line-clamp-2 leading-relaxed">
              {alert.reason}
            </p>
          )}
        </div>

        {/* Right side */}
        <div className="flex-shrink-0 text-right space-y-1">
          <StatusBadge status={alert.status} />
          <div className="flex items-center gap-1 justify-end text-[10px] text-[#62697b] light:text-slate-400 font-mono">
            <Clock size={9} />
            {formatRelativeTime(alert.created_at)}
          </div>
          {!compact && (
            <div className="text-[10px] text-[#62697b] light:text-slate-400 font-mono">
              {formatEventTime(alert.created_at, timeZone, timeFormat)}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

// ─── Alert Detail Card (with Forensic Snapshot Lightbox) ──────────────────────

interface AlertDetailProps {
  alert: Alert;
  onAcknowledge?: () => void;
  onUpdateStatus?: (status: Alert['status']) => void;
}

export function AlertDetail({ alert, onAcknowledge, onUpdateStatus }: AlertDetailProps) {
  const timeZone   = useStore((s) => s.timeZone);
  const timeFormat = useStore((s) => s.timeFormat);
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);

  const borderHighlight =
    alert.threat_level === 'CRITICAL' ? 'border-red-500/50 light:border-red-300' :
    alert.threat_level === 'HIGH'     ? 'border-orange-500/50 light:border-orange-300' :
    alert.threat_level === 'MEDIUM'   ? 'border-yellow-500/50 light:border-yellow-300' :
                                        'border-emerald-500/50 light:border-emerald-300';

  const snapshotUrl = getSnapshotUrl(alert.snapshot_path);

  return (
    <>
      <div className={`bg-[#121419] light:bg-white border ${borderHighlight} rounded-2xl p-5 space-y-4 shadow-card transition-colors animate-[fadeIn_0.3s_ease-out]`}>
        {/* Alert header */}
        <div className="flex items-start justify-between gap-3 pb-3 border-b border-[#272b37] light:border-[#d3d8e3]">
          <div className="flex items-center gap-2">
            <AlertTriangle
              size={20}
              className={
                alert.threat_level === 'CRITICAL' ? 'text-red-400 light:text-red-600' :
                alert.threat_level === 'HIGH'     ? 'text-orange-400 light:text-orange-600' :
                alert.threat_level === 'MEDIUM'   ? 'text-yellow-400 light:text-yellow-600' :
                                                    'text-emerald-400 light:text-emerald-600'
              }
            />
            <div>
              <div className="text-sm font-bold text-white light:text-slate-900 flex items-center gap-2">
                <span>{EVENT_LABELS[alert.event_type] || alert.event_type}</span>
                {alert.behaviour_label && (
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                    {alert.behaviour_label}
                  </span>
                )}
              </div>
              <div className="text-[11px] font-mono text-[#9aa2b5] light:text-slate-500">{alert.alert_id}</div>
            </div>
          </div>
          <ThreatBadge level={alert.threat_level} size="md" />
        </div>

        {/* Details grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
          {[
            { label: 'Source',     value: alert.video_id ? `Clip · ${alert.camera_id}` : alert.camera_id },
            { label: 'Object',     value: alert.object_id },
            { label: 'Confidence', value: typeof alert.confidence === 'number' ? `${alert.confidence.toFixed(1)}%` : 'AI Confirmed' },
            { label: 'Event',      value: EVENT_LABELS[alert.event_type] || alert.event_type },
            { label: 'Status',     value: <StatusBadge status={alert.status} /> },
            { label: 'Time',       value: formatHistoryTimestamp(alert.created_at, timeZone, timeFormat) },
          ].map(({ label, value }) => (
            <div key={label} className="bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-2">
              <div className="text-[10px] text-[#62697b] light:text-slate-400 uppercase tracking-wide mb-0.5">{label}</div>
              <div className="text-white light:text-slate-900 font-semibold">{value}</div>
            </div>
          ))}
        </div>

        {/* Reason */}
        <div className="bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3.5 py-3">
          <div className="text-[10px] text-[#62697b] light:text-slate-400 uppercase tracking-wide mb-1">Alert Reason</div>
          <p className="text-xs text-white light:text-slate-800 leading-relaxed font-medium">{alert.reason}</p>
        </div>

        {/* ── Captured Evidence Snapshot Section ────────────────────── */}
        {snapshotUrl ? (
          <div className="bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d3d8e3] rounded-xl p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 text-xs font-bold text-white light:text-slate-900">
                <Camera size={13} className="text-emerald-400 light:text-[#15803d]" />
                <span>Forensic Threat Snapshot (Annotated Evidence)</span>
              </div>
              <button
                type="button"
                onClick={() => setIsLightboxOpen(true)}
                className="text-[10px] font-mono text-emerald-400 light:text-[#15803d] hover:underline flex items-center gap-1 cursor-pointer font-semibold"
              >
                <Maximize2 size={11} /> Expand Snapshot
              </button>
            </div>

            <div
              onClick={() => setIsLightboxOpen(true)}
              className="relative rounded-lg overflow-hidden border border-[#272b37] light:border-[#d3d8e3] cursor-pointer group bg-black/60 max-h-64 flex items-center justify-center transition-all"
            >
              <img
                src={snapshotUrl}
                alt={`Evidence snapshot for ${alert.alert_id}`}
                className="w-full h-auto max-h-60 object-contain transition-transform duration-300 group-hover:scale-[1.01]"
                loading="lazy"
              />
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <span className="text-white text-xs font-semibold bg-black/70 px-3 py-1.5 rounded-full backdrop-blur-xs flex items-center gap-1.5 shadow-lg border border-white/10">
                  <Maximize2 size={13} /> Click to Open Lightbox
                </span>
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-[#191c24]/50 border border-dashed border-[#272b37] rounded-xl p-3 text-center">
            <p className="text-[11px] font-mono text-[#62697b]">No forensic snapshot attached for this alert.</p>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-2">
            {alert.status === 'NEW' && onAcknowledge && (
              <button
                type="button"
                onClick={onAcknowledge}
                className="ibvap-btn-primary text-xs cursor-pointer shadow-xs"
              >
                ✓ Acknowledge
              </button>
            )}
            {onUpdateStatus && (
              <>
                {alert.status !== 'UNDER_INVESTIGATION' && alert.status !== 'RESOLVED' && (
                  <button
                    type="button"
                    onClick={() => onUpdateStatus('UNDER_INVESTIGATION')}
                    className="ibvap-btn-ghost text-xs cursor-pointer shadow-xs"
                  >
                    Investigate
                  </button>
                )}
                {alert.status !== 'RESOLVED' && (
                  <button
                    type="button"
                    onClick={() => onUpdateStatus('RESOLVED')}
                    className="ibvap-btn-ghost text-xs cursor-pointer shadow-xs"
                  >
                    Resolve
                  </button>
                )}
              </>
            )}
          </div>

          {snapshotUrl && (
            <a
              href={snapshotUrl}
              download={`evidence_${alert.alert_id}.png`}
              target="_blank"
              rel="noreferrer"
              className="text-xs font-mono text-[#9aa2b5] hover:text-white flex items-center gap-1 border border-[#272b37] px-2.5 py-1.5 rounded-lg transition-colors cursor-pointer"
            >
              <Download size={12} /> Save Snapshot
            </a>
          )}
        </div>
      </div>

      {/* ── High-Resolution Lightbox Modal ──────────────────────────── */}
      {isLightboxOpen && snapshotUrl && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4 animate-[fadeIn_0.2s_ease-out]">
          <div className="relative max-w-4xl w-full bg-[#121419] border border-[#272b37] rounded-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="px-4 py-3 bg-[#191c24] border-b border-[#272b37] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ThreatBadge level={alert.threat_level} size="sm" />
                <span className="text-sm font-bold text-white font-mono">{alert.alert_id}</span>
                <span className="text-xs text-[#9aa2b5]">• {alert.camera_id}</span>
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={snapshotUrl}
                  download={`evidence_${alert.alert_id}.png`}
                  className="p-1.5 rounded-lg bg-[#272b37] hover:bg-[#323746] text-white transition-colors cursor-pointer"
                  title="Download image"
                >
                  <Download size={14} />
                </a>
                <button
                  type="button"
                  onClick={() => setIsLightboxOpen(false)}
                  className="p-1.5 rounded-lg bg-[#272b37] hover:bg-red-500/30 text-white hover:text-red-400 transition-colors cursor-pointer"
                  title="Close modal"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            {/* Modal Image Body */}
            <div className="p-4 flex-1 overflow-auto flex items-center justify-center bg-black/80">
              <img
                src={snapshotUrl}
                alt={`Evidence snapshot ${alert.alert_id}`}
                className="max-w-full max-h-[70vh] object-contain rounded-lg border border-[#272b37] shadow-xl"
              />
            </div>

            {/* Modal Footer Banner */}
            <div className="px-4 py-2.5 bg-[#191c24] border-t border-[#272b37] flex items-center justify-between text-xs text-[#9aa2b5]">
              <span className="truncate max-w-xl font-medium text-white">{alert.reason}</span>
              <span className="font-mono text-[11px]">{formatHistoryTimestamp(alert.created_at, timeZone, timeFormat)}</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
