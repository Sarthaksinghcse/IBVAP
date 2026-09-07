import { Cpu, Database, HardDrive, Wifi, Activity } from 'lucide-react';
import { useStore, getActiveCamerasCount, getTotalCamerasCount } from '../../store/useStore';
import { ProgressBar } from '../ui/Card';

// ─── System Health Panel ──────────────────────────────────────────────────────

function StatusRow({
  icon: Icon,
  label,
  value,
  valueClass = 'text-[#22c55e] light:text-[#15803d]',
}: {
  icon: typeof Cpu;
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[#272b37] light:border-[#d9dde3] last:border-0">
      <div className="flex items-center gap-2">
        <Icon size={13} className="text-[#9aa2b5] light:text-slate-500" />
        <span className="text-xs text-[#9aa2b5] light:text-slate-600 font-medium">{label}</span>
      </div>
      <span className={`text-xs font-mono font-semibold ${valueClass}`}>{value}</span>
    </div>
  );
}

export function SystemHealth() {
  const sys                = useStore((s) => s.systemStatus);
  const cameras            = useStore((s) => s.cameras);
  const isWebcamActive     = useStore((s) => s.isWebcamActive);
  const activeCameraStream = useStore((s) => s.activeCameraStream);

  const activeCams = getActiveCamerasCount(cameras, isWebcamActive, activeCameraStream);
  const totalCams  = getTotalCamerasCount(cameras, isWebcamActive, activeCameraStream);
  const storagePct = sys.storage_total_mb > 0
    ? Math.round((sys.storage_used_mb / sys.storage_total_mb) * 100)
    : 0;

  const uptime = (() => {
    const s = sys.uptime_seconds;
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}h ${m}m`;
  })();

  return (
    <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl overflow-hidden shadow-card transition-colors">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#272b37] light:border-[#d9dde3] bg-[#191c24] light:bg-slate-50">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-[#22c55e] light:text-[#15803d]" />
          <span className="text-xs font-bold text-white light:text-slate-900">System Status</span>
        </div>
      </div>




      <div className="px-4 py-1">
        <StatusRow
          icon={Cpu}
          label="AI Engine"
          value={sys.ai_engine_status}
          valueClass={sys.ai_engine_status === 'RUNNING' ? 'text-[#22c55e] light:text-[#15803d]' : 'text-red-400 light:text-red-700'}
        />
        <StatusRow
          icon={Database}
          label="Database"
          value={sys.database_status}
          valueClass={sys.database_status === 'OK' ? 'text-[#22c55e] light:text-[#15803d]' : 'text-red-400 light:text-red-700'}
        />
        <StatusRow
          icon={Wifi}
          label="WebSocket"
          value={sys.websocket_connected ? 'CONNECTED' : 'OFFLINE'}
          valueClass={sys.websocket_connected ? 'text-[#22c55e] light:text-[#15803d]' : 'text-red-400 light:text-red-700'}
        />
        <StatusRow
          icon={Activity}
          label="Cameras Active"
          value={`${activeCams} / ${totalCams}`}
          valueClass="text-white light:text-slate-900"
        />
        <StatusRow
          icon={Activity}
          label="Alerts Today"
          value={String(sys.alerts_today)}
          valueClass="text-orange-400 light:text-orange-700"
        />
        <StatusRow
          icon={Activity}
          label="Uptime"
          value={uptime}
          valueClass="text-[#8e95a5] light:text-slate-600"
        />
      </div>

      <div className="px-4 pb-4 pt-2">
        <ProgressBar
          value={storagePct}
          label="Storage"
          showValue
        />
      </div>
    </div>
  );
}

// ─── AI Detection Summary ─────────────────────────────────────────────────────

export function AIDetectionSummary() {
  const analytics = useStore((s) => s.analytics);

  const stats = [
    { label: 'People',     value: analytics?.people_count    ?? 0, color: 'text-white light:text-slate-900' },
    { label: 'Vehicles',   value: analytics?.vehicle_count   ?? 0, color: 'text-white light:text-slate-900' },
    { label: 'Loitering',  value: analytics?.loitering_count ?? 0, color: 'text-orange-400 light:text-orange-700' },
    { label: 'Intrusions', value: analytics?.intrusion_count ?? 0, color: 'text-red-400 light:text-red-700' },
  ];

  return (
    <div className="bg-[#111215] light:bg-white border border-[#1e2026] light:border-[#e5e7eb] rounded-2xl overflow-hidden shadow-sm transition-colors">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2026] light:border-[#e5e7eb] bg-[#181a1f] light:bg-slate-50">
        <div className="flex items-center gap-2">
          <Cpu size={14} className="text-[#22c55e] light:text-[#15803d]" />
          <span className="text-xs font-bold text-white light:text-slate-900">AI Detection Summary</span>
        </div>
        <span className="text-[10px] text-[#8e95a5] light:text-slate-400 font-mono">Today</span>
      </div>

      <div className="px-4 py-3 grid grid-cols-2 gap-3">
        {stats.map(({ label, value, color }) => (
          <div key={label} className="bg-[#181a1f] light:bg-[#f9fafb] border border-[#1e2026] light:border-[#e5e7eb] rounded-xl px-3 py-2.5">
            <div className={`text-2xl font-bold font-mono ${color}`}>
              {String(value).padStart(2, '0')}
            </div>
            <div className="text-[11px] text-[#8e95a5] light:text-slate-500 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      <div className="px-4 pb-3 flex items-center justify-between">
        <span className="text-[11px] text-[#8e95a5] light:text-slate-500">
          Total detections: <span className="text-white light:text-slate-900 font-mono">{analytics?.total_detections ?? 0}</span>
        </span>
        <span className="text-[11px] text-[#8e95a5] light:text-slate-500">
          FPS: <span className="text-[#22c55e] light:text-[#15803d] font-mono">{analytics?.ai_engine_fps.toFixed(1) ?? '0.0'}</span>
        </span>
      </div>
    </div>
  );
}

// ─── Threat Level Overview ────────────────────────────────────────────────────

export function ThreatOverview() {
  const analytics = useStore((s) => s.analytics);
  const tb = analytics?.threat_breakdown;

  const levels = [
    { label: 'Critical', count: tb?.critical ?? 0, color: '#ef4444', bg: 'bg-red-500' },
    { label: 'High',     count: tb?.high     ?? 0, color: '#f97316', bg: 'bg-orange-500' },
    { label: 'Medium',   count: tb?.medium   ?? 0, color: '#eab308', bg: 'bg-yellow-500' },
    { label: 'Low',      count: tb?.low      ?? 0, color: '#22c55e', bg: 'bg-green-500' },
    { label: 'None',     count: tb?.none     ?? 0, color: '#64748b', bg: 'bg-slate-500' },
  ];

  const total = levels.reduce((s, l) => s + l.count, 0) || 1;

  return (
    <div className="bg-[#111215] light:bg-white border border-[#1e2026] light:border-[#e5e7eb] rounded-2xl overflow-hidden shadow-sm transition-colors">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2026] light:border-[#e5e7eb] bg-[#181a1f] light:bg-slate-50">
        <div className="flex items-center gap-2">
          <HardDrive size={14} className="text-[#22c55e] light:text-[#15803d]" />
          <span className="text-xs font-bold text-white light:text-slate-900">Threat Overview</span>
        </div>
      </div>

      <div className="px-4 py-3 space-y-2.5">
        {levels.map(({ label, count, color, bg }) => {
          const pct = Math.round((count / total) * 100);
          return (
            <div key={label}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-full ${bg}`} />
                  <span className="text-xs text-[#8e95a5] light:text-slate-600">{label}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono" style={{ color }}>{count}</span>
                  <span className="text-[10px] text-[#5a6070] light:text-slate-400 font-mono w-7 text-right">{pct}%</span>
                </div>
              </div>
              <div className="w-full h-1.5 bg-[#181a1f] light:bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${pct}%`, background: color }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── False-Positive Filtering Transparency ────────────────────────────────────

export function FalsePositiveTransparency() {
  const detections = useStore((s) => s.detections);
  const alerts     = useStore((s) => s.alerts);
  const settings   = useStore((s) => s.settings);

  const threshold = settings.aiThreshold || 50;

  // Real Transparency Computations
  const totalDetections = detections.length;
  const filteredLowConf = detections.filter((d) => typeof d.confidence === 'number' && d.confidence < threshold).length;
  const filteredAnimals = detections.filter((d) => d.object_type === 'ANIMAL').length;
  const filteredTotal   = filteredLowConf + filteredAnimals;
  const alertEligible   = Math.max(0, totalDetections - filteredTotal);
  const alertsGenerated = alerts.length;

  const efficiencyPct = totalDetections > 0 ? Math.round((filteredTotal / totalDetections) * 100) : 0;

  return (
    <div className="bg-[#111215] light:bg-white border border-[#1e2026] light:border-[#e5e7eb] rounded-2xl overflow-hidden shadow-sm transition-colors">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1e2026] light:border-[#e5e7eb] bg-[#181a1f] light:bg-slate-50">
        <div className="flex items-center gap-2">
          <Activity size={14} className="text-[#22c55e] light:text-[#15803d]" />
          <span className="text-xs font-bold text-white light:text-slate-900">Filtering Transparency</span>
        </div>
        <span className="text-[10px] text-[#22c55e] light:text-[#15803d] font-mono font-semibold">
          {efficiencyPct}% Noise Reduced
        </span>
      </div>

      <div className="px-4 py-3 space-y-2 text-xs">
        <div className="flex items-center justify-between py-1 border-b border-[#1e2026] light:border-[#e5e7eb]">
          <span className="text-[#8e95a5] light:text-slate-600">Total Detections</span>
          <span className="font-mono font-bold text-white light:text-slate-900">{totalDetections}</span>
        </div>
        <div className="flex items-center justify-between py-1 border-b border-[#1e2026] light:border-[#e5e7eb]">
          <span className="text-[#8e95a5] light:text-slate-600">Filtered Low-Conf (&lt;{threshold}%)</span>
          <span className="font-mono font-bold text-amber-400 light:text-amber-700">{filteredLowConf}</span>
        </div>
        <div className="flex items-center justify-between py-1 border-b border-[#1e2026] light:border-[#e5e7eb]">
          <span className="text-[#8e95a5] light:text-slate-600">Filtered Animal Classes</span>
          <span className="font-mono font-bold text-amber-400 light:text-amber-700">{filteredAnimals}</span>
        </div>
        <div className="flex items-center justify-between py-1 border-b border-[#1e2026] light:border-[#e5e7eb]">
          <span className="text-[#8e95a5] light:text-slate-600">Alert-Eligible Detections</span>
          <span className="font-mono font-bold text-white light:text-slate-900">{alertEligible}</span>
        </div>
        <div className="flex items-center justify-between py-1">
          <span className="text-[#8e95a5] light:text-slate-600">Security Alerts Generated</span>
          <span className="font-mono font-bold text-red-400 light:text-red-700">{alertsGenerated}</span>
        </div>
      </div>
    </div>
  );
}
