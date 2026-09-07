import { AlertTriangle, Clock, MapPin, User, Car } from 'lucide-react';
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
};


const ObjectIcon = ({ type }: { type: string }) =>
  type === 'VEHICLE' ? <Car size={12} /> : <User size={12} />;

// ─── Compact Alert Card ───────────────────────────────────────────────────────

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
          {/* Event type */}
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            <ThreatBadge level={alert.threat_level} />
            <span className={`font-semibold text-white light:text-slate-900 truncate ${compact ? 'text-xs' : 'text-sm'}`}>
              {EVENT_LABELS[alert.event_type] || alert.event_type}
            </span>
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

// ─── Alert Detail Card (full) ─────────────────────────────────────────────────

interface AlertDetailProps {
  alert: Alert;
  onAcknowledge?: () => void;
  onUpdateStatus?: (status: Alert['status']) => void;
}

export function AlertDetail({ alert, onAcknowledge, onUpdateStatus }: AlertDetailProps) {
  const timeZone   = useStore((s) => s.timeZone);
  const timeFormat = useStore((s) => s.timeFormat);

  const borderHighlight =
    alert.threat_level === 'CRITICAL' ? 'border-red-500/50 light:border-red-300' :
    alert.threat_level === 'HIGH'     ? 'border-orange-500/50 light:border-orange-300' :
    alert.threat_level === 'MEDIUM'   ? 'border-yellow-500/50 light:border-yellow-300' :
                                        'border-emerald-500/50 light:border-emerald-300';

  return (
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
            <div className="text-sm font-bold text-white light:text-slate-900">
              {EVENT_LABELS[alert.event_type] || alert.event_type}
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

      {/* Actions */}
      <div className="flex items-center gap-2 pt-1">
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
    </div>
  );
}
