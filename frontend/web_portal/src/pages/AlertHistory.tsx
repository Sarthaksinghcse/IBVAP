import { useState, useMemo } from 'react';
import { Search, Filter, ChevronLeft, ChevronRight } from 'lucide-react';
import { useAlerts } from '../hooks/useAlerts';
import { useStore } from '../store/useStore';
import { ThreatBadge, StatusBadge } from '../components/ui/Badge';
import { formatHistoryTimestamp } from '../utils/time';
import type { ThreatLevel, AlertStatus } from '../types';

const PAGE_SIZE = 10;

const EVENT_LABELS: Record<string, string> = {
  ZONE_INTRUSION:      'Zone Intrusion',
  LOITERING:           'Loitering',
  PERSON_DETECTED:     'Person Detected',
  VEHICLE_DETECTED:    'Vehicle Detected',
  SUSPICIOUS_ACTIVITY: 'Suspicious Activity',
  THREAT_CORRELATION:  'Threat Correlation',
};

export default function AlertHistory() {
  useAlerts();
  const alerts     = useStore((s) => s.alerts);
  const timeZone   = useStore((s) => s.timeZone);
  const timeFormat = useStore((s) => s.timeFormat);

  const [search, setSearch]     = useState('');
  const [levelFilter, setLevel] = useState<ThreatLevel | 'ALL'>('ALL');
  const [statusFilter, setStatus] = useState<AlertStatus | 'ALL'>('ALL');
  const [camFilter, setCam]     = useState('ALL');
  const [page, setPage]         = useState(1);

  const cameras = [...new Set(alerts.map((a) => a.camera_id))].sort();

  const filtered = useMemo(() => {
    return alerts.filter((a) => {
      if (levelFilter  !== 'ALL' && a.threat_level !== levelFilter) return false;
      if (statusFilter !== 'ALL' && a.status !== statusFilter) return false;
      if (camFilter    !== 'ALL' && a.camera_id !== camFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (!a.alert_id.toLowerCase().includes(q) &&
            !a.object_id.toLowerCase().includes(q) &&
            !a.camera_id.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [alerts, levelFilter, statusFilter, camFilter, search]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageAlerts = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const select = (items: string[], val: string, set: (v: string) => void) => (
    <select
      value={val}
      onChange={(e) => { set(e.target.value); setPage(1); }}
      className="bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-2.5 py-1.5 text-xs text-white light:text-slate-900 focus:outline-none focus:border-[#22c55e] cursor-pointer"
    >
      {items.map((i) => (
        <option key={i} value={i} className="bg-[#121419] light:bg-white text-white light:text-slate-900">{i}</option>
      ))}
    </select>
  );

  return (
    <div className="space-y-4">
      {/* ── Filters ──────────────────────────────────────────────── */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-4 flex flex-wrap items-center gap-3 shadow-card transition-colors">
        {/* Search */}
        <div className="flex items-center gap-2 bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-1.5 flex-1 min-w-48">
          <Search size={13} className="text-[#62697b] light:text-slate-400 flex-shrink-0" />
          <input
            type="text"
            placeholder="Search alert ID, camera, object…"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="bg-transparent text-xs text-white light:text-slate-900 placeholder-[#62697b] light:placeholder-slate-400 outline-none w-full"
          />
        </div>

        {/* Level filter */}
        {select(['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'], levelFilter, (v) => setLevel(v as ThreatLevel | 'ALL'))}

        {/* Status filter */}
        {select(['ALL', 'NEW', 'ACKNOWLEDGED', 'UNDER_INVESTIGATION', 'RESOLVED'], statusFilter, (v) => setStatus(v as AlertStatus | 'ALL'))}

        {/* Camera filter */}
        {select(['ALL', ...cameras], camFilter, setCam)}

        <div className="flex items-center gap-1.5 text-xs text-[#9aa2b5] light:text-slate-500 font-medium">
          <Filter size={12} />
          <span>{filtered.length} results</span>
        </div>
      </div>

      {/* ── Table ────────────────────────────────────────────────── */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl overflow-hidden shadow-card transition-colors">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-[#272b37] light:border-[#d3d8e3] bg-[#191c24] light:bg-slate-50 text-[#9aa2b5] light:text-slate-600 font-semibold">
              <th className="px-4 py-3 text-left">Threat</th>
              <th className="px-4 py-3 text-left">Event</th>
              <th className="px-4 py-3 text-left">Camera</th>
              <th className="px-4 py-3 text-left">Object</th>
              <th className="px-4 py-3 text-left hidden sm:table-cell">Reason</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-right">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#272b37] light:divide-[#d3d8e3]">
            {pageAlerts.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-[#62697b] light:text-slate-400">
                  No alerts match your filter criteria
                </td>
              </tr>
            ) : (
              pageAlerts.map((alert) => (
                <tr
                  key={alert.id}
                  className="hover:bg-[#191c24]/60 light:hover:bg-slate-50 transition-colors"
                >
                  <td className="px-4 py-3">
                    <ThreatBadge level={alert.threat_level} />
                  </td>
                  <td className="px-4 py-3 font-semibold text-white light:text-slate-900">
                    {EVENT_LABELS[alert.event_type] || alert.event_type}
                  </td>
                  <td className="px-4 py-3 font-mono text-[#9aa2b5] light:text-slate-600">
                    {alert.video_id ? `Clip · ${alert.camera_id}` : alert.camera_id}
                  </td>
                  <td className="px-4 py-3 font-mono text-white light:text-slate-900">
                    {alert.object_id}
                  </td>
                  <td className="px-4 py-3 text-[#9aa2b5] light:text-slate-600 max-w-xs truncate hidden sm:table-cell">
                    {alert.reason}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={alert.status} />
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[11px] text-[#9aa2b5] light:text-slate-500 whitespace-nowrap">
                    {formatHistoryTimestamp(alert.created_at, timeZone, timeFormat)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* ── Pagination ───────────────────────────────────────────── */}
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-[#272b37] light:border-[#d3d8e3] bg-[#191c24] light:bg-slate-50 flex items-center justify-between">
            <span className="text-xs text-[#9aa2b5] light:text-slate-500 font-mono">
              Page {page} of {totalPages} ({filtered.length} total)
            </span>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 rounded-lg text-[#9aa2b5] hover:text-white light:hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="p-1.5 rounded-lg text-[#9aa2b5] hover:text-white light:hover:text-slate-900 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
