import { useState } from 'react';
import { AlertCard, AlertDetail } from '../components/alerts/AlertCard';
import { useAlerts } from '../hooks/useAlerts';
import { useStore } from '../store/useStore';
import type { ThreatLevel } from '../types';

const LEVELS: (ThreatLevel | 'ALL')[] = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

export default function Alerts() {
  const { alerts, acknowledge, updateStatus } = useAlerts();
  const [filter, setFilter]             = useState<ThreatLevel | 'ALL'>('ALL');
  const [scope, setScope]               = useState<'ACTIVE_SOURCE' | 'ALL_SOURCES'>('ACTIVE_SOURCE');
  const [selectedId, setSelectedId]     = useState<string | null>(null);

  const activeVideoId    = useStore((s) => s.activeVideoId);
  const uploadStatus     = useStore((s) => s.uploadStatus);
  const cameraMode       = useStore((s) => s.cameraMode);
  const selectedCameraId = useStore((s) => s.selectedCameraId);

  // Source modes
  const isAnalyzing = !cameraMode && !!activeVideoId && !!uploadStatus && uploadStatus !== 'COMPLETED' && uploadStatus !== 'ERROR';
  const isVideoMode = !cameraMode && !!activeVideoId && uploadStatus === 'COMPLETED';

  // 1. Isolate active source alerts (no cross-source leaking)
  const scopedAlerts = scope === 'ALL_SOURCES'
    ? alerts
    : isVideoMode
    ? alerts.filter((a) => a.video_id === activeVideoId)
    : cameraMode
    ? alerts.filter((a) => a.camera_id === 'WEBCAM-01')
    : isAnalyzing
    ? []
    : alerts.filter((a) => a.camera_id === selectedCameraId && !a.video_id);

  const filtered = scopedAlerts.filter(
    (a) => a.status !== 'RESOLVED' && (filter === 'ALL' || a.threat_level === filter)
  );

  const selected = scopedAlerts.find((a) => a.id === selectedId) ?? null;

  return (
    <div className="grid grid-cols-12 gap-4 h-full">
      {/* ── Left: Alert List ─────────────────────────────────────── */}
      <div className="col-span-12 lg:col-span-5 flex flex-col gap-3">

        {/* Source Scope Toggle + Threat Filters */}
        <div className="flex flex-col gap-2">
          {/* Scope selection */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1 bg-[#121419] light:bg-[#f2f4f8] p-1 rounded-xl border border-[#272b37] light:border-[#d3d8e3]">
              <button
                type="button"
                onClick={() => setScope('ACTIVE_SOURCE')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  scope === 'ACTIVE_SOURCE'
                    ? 'bg-[#13271d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] shadow-xs'
                    : 'text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900'
                }`}
              >
                Active Source
              </button>
              <button
                type="button"
                onClick={() => setScope('ALL_SOURCES')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  scope === 'ALL_SOURCES'
                    ? 'bg-[#13271d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] shadow-xs'
                    : 'text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900'
                }`}
              >
                All Sources
              </button>
            </div>

            {scope === 'ACTIVE_SOURCE' && (
              <span className="text-[10px] font-mono text-[#9aa2b5] light:text-slate-500 font-medium">
                {isVideoMode ? 'CCTV Clip' : cameraMode ? 'Webcam' : selectedCameraId || 'BOP-07'}
              </span>
            )}
          </div>

          {/* Threat Level Filters */}
          <div className="flex gap-1.5 flex-wrap">
            {LEVELS.map((lvl) => {
              const isActive = filter === lvl;
              const count = scopedAlerts.filter((a) => (lvl === 'ALL' || a.threat_level === lvl) && a.status !== 'RESOLVED').length;
              return (
                <button
                  key={lvl}
                  type="button"
                  onClick={() => setFilter(lvl)}
                  className={`px-3 py-1 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                    isActive
                      ? 'bg-[#13271d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] shadow-xs'
                      : 'bg-[#121419] light:bg-white text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 border border-[#272b37] light:border-[#d3d8e3] hover:border-slate-500'
                  }`}
                >
                  {lvl}
                  <span className="ml-1 font-mono">({count})</span>
                </button>
              );
            })}
          </div>
        </div>


        {/* List */}
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl overflow-hidden flex flex-col shadow-card transition-colors">
          <div className="px-4 py-3 border-b border-[#272b37] light:border-[#d3d8e3] bg-[#191c24] light:bg-slate-50 flex items-center justify-between">
            <span className="text-xs font-bold text-white light:text-slate-900">Active Alerts</span>
            <span className="text-[11px] font-mono text-[#9aa2b5] light:text-slate-500 font-medium">{filtered.length} shown</span>
          </div>
          <div className="overflow-y-auto flex-1 p-3 space-y-2.5 max-h-[620px]">
            {filtered.length === 0 ? (
              <div className="py-16 text-center">
                <div className="w-10 h-10 rounded-full bg-[#191c24] light:bg-slate-100 border border-[#272b37] light:border-slate-300 flex items-center justify-center mx-auto mb-2 text-[#62697b] light:text-slate-400">
                  <span className="text-emerald-400 light:text-[#15803d] font-bold">✓</span>
                </div>
                <p className="text-sm font-semibold text-white light:text-slate-800">No active alerts</p>
                <p className="text-xs text-[#9aa2b5] light:text-slate-500 mt-1 max-w-xs mx-auto">
                  {scope === 'ACTIVE_SOURCE'
                    ? 'No active threats detected for currently active source.'
                    : 'System is all clear — zero active threats detected.'}
                </p>
              </div>
            ) : (
              filtered.map((alert) => (
                <AlertCard
                  key={alert.id}
                  alert={alert}
                  isSelected={alert.id === selectedId}
                  onClick={() => setSelectedId(alert.id === selectedId ? null : alert.id)}
                />
              ))
            )}
          </div>
        </div>
      </div>

      {/* ── Right: Detail Panel ──────────────────────────────────── */}
      <div className="col-span-12 lg:col-span-7">
        {selected ? (
          <AlertDetail
            alert={selected}
            onAcknowledge={() => acknowledge(selected.id)}
            onUpdateStatus={(status) => updateStatus(selected.id, status)}
          />
        ) : (
          <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl h-full min-h-[320px] flex items-center justify-center p-8 shadow-card transition-colors">
            <div className="text-center">
              <div className="text-4xl mb-3 text-[#62697b] light:text-slate-300">⚡</div>
              <p className="text-sm font-semibold text-white light:text-slate-800">Select an alert to view details</p>
              <p className="text-xs text-[#9aa2b5] light:text-slate-500 mt-1">Click any alert from the list</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

