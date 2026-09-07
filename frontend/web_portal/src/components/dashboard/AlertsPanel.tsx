import { Link } from 'react-router-dom';
import { AlertTriangle, ChevronRight } from 'lucide-react';
import { useStore } from '../../store/useStore';
import { ThreatBadge, StatusBadge } from '../ui/Badge';
import { formatRelativeTime } from '../../utils/time';
import { useState, useEffect } from 'react';
import type { Alert } from '../../types';

// ─── Individual Alert Row ─────────────────────────────────────────────────────

const EVENT_LABELS: Record<string, string> = {
  ZONE_INTRUSION:      'Zone Breach',
  LOITERING:           'Loitering',
  PERSON_DETECTED:     'Person Detected',
  VEHICLE_DETECTED:    'Vehicle Detected',
  SUSPICIOUS_ACTIVITY: 'Suspicious Activity',
  PERSON_TRACKED:      'Person Tracked',
  VEHICLE_TRACKED:     'Vehicle Tracked',
  THREAT_CORRELATION:  'Threat Correlation',
};

function AlertRow({ alert, isNew }: { alert: Alert; isNew?: boolean }) {
  const borderColor =
    alert.threat_level === 'CRITICAL' ? 'border-l-red-500' :
    alert.threat_level === 'HIGH'     ? 'border-l-orange-500' :
    alert.threat_level === 'MEDIUM'   ? 'border-l-yellow-500' :
    'border-l-green-500';

  return (
    <div
      className={`
        border-l-4 ${borderColor} pl-3 pr-3 py-2.5 rounded-r-xl
        bg-[#191c24] light:bg-[#f8fafc] border-y border-r border-[#272b37] light:border-[#d9dde3] hover:border-slate-500 light:hover:border-slate-400 transition-colors duration-150 shadow-xs
        ${isNew ? 'alert-new-flash' : ''}
      `}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
            <ThreatBadge level={alert.threat_level} />
            <span className="text-xs font-semibold text-white light:text-slate-900 truncate">
              {EVENT_LABELS[alert.event_type] || alert.event_type}
            </span>
          </div>
          <div className="text-[11px] text-[#9aa2b5] light:text-slate-500 truncate">
            {alert.camera_id} · {alert.object_id}
          </div>
        </div>
        <div className="flex-shrink-0 text-right">
          <StatusBadge status={alert.status} />
          <div className="text-[10px] text-[#62697b] light:text-slate-400 mt-0.5 font-mono">
            {formatRelativeTime(alert.created_at)}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Alerts Panel ─────────────────────────────────────────────────────────────

export function AlertsPanel() {
  const alerts           = useStore((s) => s.alerts);
  const activeVideoId    = useStore((s) => s.activeVideoId);
  const uploadStatus     = useStore((s) => s.uploadStatus);
  const cameraMode       = useStore((s) => s.cameraMode);
  const selectedCameraId = useStore((s) => s.selectedCameraId);

  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const isAnalyzing = !cameraMode && !!activeVideoId && !!uploadStatus && uploadStatus !== 'COMPLETED' && uploadStatus !== 'ERROR';
  const isVideoMode = !cameraMode && !!activeVideoId && uploadStatus === 'COMPLETED';

  // Source-Scoped Alerts
  const sourceAlerts = isVideoMode
    ? alerts.filter((a) => a.video_id === activeVideoId)
    : cameraMode
    ? alerts.filter((a) => a.camera_id === 'WEBCAM-01')
    : isAnalyzing
    ? []
    : selectedCameraId
    ? alerts.filter((a) => a.camera_id === selectedCameraId && !a.video_id)
    : alerts;

  const visibleAlerts = sourceAlerts
    .filter((a) => a.status !== 'RESOLVED')
    .slice(0, 8);

  const criticalCount = sourceAlerts.filter(
    (a) => a.threat_level === 'CRITICAL' && a.status === 'NEW'
  ).length;

  const newCount = sourceAlerts.filter((a) => a.status === 'NEW').length;

  return (
    <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl flex flex-col h-full overflow-hidden shadow-card transition-colors">

      <div className="flex items-center justify-between px-4 py-3 border-b border-[#272b37] light:border-[#d9dde3] bg-[#191c24] light:bg-slate-50">
        <div className="flex items-center gap-2">
          <AlertTriangle size={14} className="text-red-400 light:text-red-600" />
          <span className="text-xs font-bold text-white light:text-slate-900">Perimeter Alerts</span>
          {newCount > 0 && (
            <span className="px-1.5 py-0.2 rounded bg-red-600 text-white text-[10px] font-bold font-mono">
              {newCount} NEW
            </span>
          )}
        </div>
        <Link
          to="/alerts"
          className="text-xs text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 flex items-center gap-0.5 transition-colors font-medium"
        >
          View all <ChevronRight size={13} />
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {visibleAlerts.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6">
            <div className="w-10 h-10 rounded-full bg-[#191c24] light:bg-slate-100 flex items-center justify-center mb-2">
              <AlertTriangle size={18} className="text-[#62697b] light:text-slate-400" />
            </div>
            <p className="text-xs font-semibold text-white light:text-slate-900">No active alerts</p>
            <p className="text-[11px] text-[#9aa2b5] light:text-slate-500 mt-0.5">Perimeter status is normal</p>
          </div>
        ) : (
          visibleAlerts.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              isNew={alert.status === 'NEW'}
            />
          ))
        )}
      </div>

      {criticalCount > 0 && (
        <div className="px-4 py-2 border-t border-red-500/20 bg-red-500/10 flex items-center justify-between text-xs text-red-400 light:text-red-700">
          <span className="font-medium">⚠️ {criticalCount} Critical alert{criticalCount > 1 ? 's' : ''} require attention</span>
          <Link to="/alerts" className="font-semibold underline hover:text-white light:hover:text-red-900 text-[11px]">
            Respond →
          </Link>
        </div>
      )}
    </div>
  );
}
