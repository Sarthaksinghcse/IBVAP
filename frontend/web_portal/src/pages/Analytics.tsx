import { useMemo } from 'react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Activity, Route, Zap, Compass, AlertTriangle, ShieldCheck, Gauge } from 'lucide-react';
import { useAnalytics } from '../hooks/useAnalytics';
import { useStore } from '../store/useStore';
import { MOCK_CHART_DATA, MOCK_CAMERA_ALERTS } from '../services/mock/mockData';

const COLORS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#64748b'];

// ─── Custom Tooltip ───────────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-2 text-xs shadow-xl font-sans">
      <p className="text-[#9aa2b5] light:text-slate-500 mb-1 font-mono">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color }} className="font-medium">
          {p.name}: <span className="font-bold font-mono">{p.value}</span>
        </p>
      ))}
    </div>
  );
}

// ─── Analytics Page ───────────────────────────────────────────────────────────

export default function Analytics() {
  useAnalytics();
  const analytics  = useStore((s) => s.analytics);
  const alerts     = useStore((s) => s.alerts);
  const detections = useStore((s) => s.detections);
  const cameras    = useStore((s) => s.cameras);
  const isMock     = useStore((s) => s.isMockMode);

  // Dynamic 24h timeline derived from real detection & alert records
  const chartData = useMemo(() => {
    if (isMock) return MOCK_CHART_DATA;
    const now = new Date();
    const buckets = Array.from({ length: 24 }, (_, i) => {
      const d = new Date(now.getTime() - (23 - i) * 3600000);
      const hourStr = d.getHours().toString().padStart(2, '0') + ':00';
      return {
        time: hourStr,
        hourStart: d.getTime() - 1800000,
        hourEnd: d.getTime() + 1800000,
        people: 0,
        vehicles: 0,
        alerts: 0,
      };
    });

    detections.forEach((det) => {
      const t = new Date(det.timestamp).getTime();
      const bucket = buckets.find((b) => t >= b.hourStart && t < b.hourEnd);
      if (bucket) {
        if (det.object_type === 'PERSON') bucket.people += 1;
        if (det.object_type === 'VEHICLE') bucket.vehicles += 1;
      }
    });

    alerts.forEach((a) => {
      const t = new Date(a.created_at).getTime();
      const bucket = buckets.find((b) => t >= b.hourStart && t < b.hourEnd);
      if (bucket) bucket.alerts += 1;
    });

    return buckets.map(({ time, people, vehicles, alerts: aCount }) => ({
      time,
      people,
      vehicles,
      alerts: aCount,
    }));
  }, [isMock, detections, alerts]);

  // Dynamic alert distribution across cameras
  const cameraData = useMemo(() => {
    if (isMock) return MOCK_CAMERA_ALERTS;
    const cameraMap: Record<string, number> = {};
    cameras.forEach((c) => {
      cameraMap[c.id] = 0;
    });
    alerts.forEach((a) => {
      if (a.camera_id) {
        cameraMap[a.camera_id] = (cameraMap[a.camera_id] || 0) + 1;
      }
    });
    return Object.entries(cameraMap).map(([camera, count]) => ({ camera, count }));
  }, [isMock, cameras, alerts]);

  const pieData = analytics
    ? [
        { name: 'Critical', value: analytics.threat_breakdown.critical },
        { name: 'High',     value: analytics.threat_breakdown.high },
        { name: 'Medium',   value: analytics.threat_breakdown.medium },
        { name: 'Low',      value: analytics.threat_breakdown.low },
        { name: 'None',     value: analytics.threat_breakdown.none },
      ]
    : [];

  const behaviourCounts = useMemo(() => {
    const counts = {
      RUNNING: 0,
      CIRCLING: 0,
      PACING: 0,
      ERRATIC_MOVEMENT: 0,
      STATIONARY: 0,
      NORMAL_TRANSIT: 0,
    };
    detections.forEach((d) => {
      if (d.behaviour_label && counts[d.behaviour_label] !== undefined) {
        counts[d.behaviour_label] += 1;
      } else if (d.loitering_duration && d.loitering_duration > 10) {
        counts.STATIONARY += 1;
      } else {
        counts.NORMAL_TRANSIT += 1;
      }
    });
    return counts;
  }, [detections]);

  const activeTrajectories = useMemo(() => {
    return detections.filter((d) => d.trajectory && d.trajectory.length >= 2);
  }, [detections]);

  const maxVelocity = useMemo(() => {
    let max = 0;
    detections.forEach((d) => {
      if (d.velocity && d.velocity > max) max = d.velocity;
    });
    return max;
  }, [detections]);

  const chartStyle = {
    fontSize: 11,
    fontFamily: 'JetBrains Mono, monospace',
    fill: '#8893a7',
  };

  return (
    <div className="space-y-4">
      {/* ── Summary Cards ─────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Total Detections', value: analytics?.total_detections ?? 0, color: 'text-white light:text-slate-900' },
          { label: 'Total Alerts',     value: analytics?.total_alerts ?? 0,      color: 'text-orange-400 light:text-orange-600' },
          { label: 'AI FPS',           value: `${(analytics?.ai_engine_fps ?? 0.0).toFixed(1)} fps`, color: 'text-[#22c55e] light:text-[#15803d]' },
          { label: 'Processing',       value: `${analytics?.processing_time_ms ?? 0}ms`,             color: 'text-white light:text-slate-900' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-4 shadow-card transition-colors">
            <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
            <div className="text-xs text-[#9aa2b5] light:text-slate-500 mt-1 font-medium">{label}</div>
          </div>
        ))}
      </div>

      {/* ── Trajectory & Behavioral Intelligence Analysis (ByteTrack) ─────────── */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <Route className="text-emerald-400 light:text-[#15803d]" size={18} />
            <h3 className="text-sm font-bold text-white light:text-slate-900">
              Trajectory-Based Behavioral Intelligence (ByteTrack Core)
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 light:bg-emerald-50 light:text-emerald-700 border border-emerald-500/30 font-semibold">
              {activeTrajectories.length} Active Tracks
            </span>
            <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-blue-500/15 text-blue-400 light:bg-blue-50 light:text-blue-700 border border-blue-500/30 font-semibold">
              Max Vel: {maxVelocity.toFixed(1)} %/s
            </span>
          </div>
        </div>

        {/* 6 Behavioral Pattern Cards */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 text-xs">
          {[
            { label: 'Running', count: behaviourCounts.RUNNING, weight: '+30 wt', color: 'border-red-500/40 bg-red-500/10 text-red-400', icon: '🏃' },
            { label: 'Circling', count: behaviourCounts.CIRCLING, weight: '+35 wt', color: 'border-orange-500/40 bg-orange-500/10 text-orange-400', icon: '🔄' },
            { label: 'Pacing', count: behaviourCounts.PACING, weight: '+25 wt', color: 'border-yellow-500/40 bg-yellow-500/10 text-yellow-400', icon: '↔️' },
            { label: 'Erratic', count: behaviourCounts.ERRATIC_MOVEMENT, weight: '+20 wt', color: 'border-purple-500/40 bg-purple-500/10 text-purple-400', icon: '⚠️' },
            { label: 'Stationary', count: behaviourCounts.STATIONARY, weight: '+10 wt', color: 'border-slate-500/40 bg-slate-500/10 text-slate-300', icon: '🛑' },
            { label: 'Transit', count: behaviourCounts.NORMAL_TRANSIT, weight: 'Normal', color: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400', icon: '🟢' },
          ].map((item) => (
            <div key={item.label} className={`border rounded-xl p-3 flex flex-col justify-between ${item.color}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-base">{item.icon}</span>
                <span className="text-[9px] font-mono px-1 rounded bg-black/40 text-white/90">{item.weight}</span>
              </div>
              <div className="text-lg font-bold font-mono text-white light:text-slate-900">{item.count}</div>
              <div className="text-[11px] font-semibold opacity-90">{item.label}</div>
            </div>
          ))}
        </div>

        {/* Real-time Trajectory Spatial Radar */}
        <div className="relative h-44 bg-[#0c101c] rounded-xl border border-[#1e2d4a] overflow-hidden p-3 flex items-center justify-center">
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#141e33_1px,transparent_1px),linear-gradient(to_bottom,#141e33_1px,transparent_1px)] bg-[size:24px_24px] opacity-40 pointer-events-none" />
          
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full pointer-events-none p-2">
            {activeTrajectories.map((d) => {
              const b = d.behaviour_label;
              const color =
                b === 'RUNNING' ? '#ef4444' :
                b === 'CIRCLING' ? '#f97316' :
                b === 'PACING' ? '#eab308' :
                b === 'ERRATIC_MOVEMENT' ? '#c084fc' :
                '#10b981';
              const pts = d.trajectory!.map(([x, y]) => `${x},${y}`).join(' ');
              const last = d.trajectory![d.trajectory!.length - 1];
              return (
                <g key={`radar-${d.id}`}>
                  <polyline points={pts} fill="none" stroke={color} strokeWidth="0.8" opacity="0.85" strokeLinecap="round" />
                  <circle cx={last[0]} cy={last[1]} r="1.4" fill={color} />
                  <circle cx={last[0]} cy={last[1]} r="0.6" fill="#fff" />
                </g>
              );
            })}
          </svg>

          {activeTrajectories.length === 0 ? (
            <div className="relative z-10 text-center">
              <Compass className="w-7 h-7 text-slate-500 mx-auto mb-1 animate-pulse" />
              <p className="text-xs text-slate-400 font-mono">Radar Standing By • Tracking active trajectories</p>
            </div>
          ) : (
            <div className="absolute bottom-2 left-3 z-10 flex items-center gap-3 text-[10px] font-mono text-slate-400 bg-black/70 px-2.5 py-1 rounded backdrop-blur-xs border border-white/5">
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> Running</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-orange-500" /> Circling</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-500" /> Pacing</span>
              <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Transit</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Detection Timeline ─────────────────────────────────────── */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
        <h3 className="text-sm font-bold text-white light:text-slate-900 mb-4">Detection Timeline (Last 24h)</h3>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={chartData} margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#272b37" />
            <XAxis dataKey="time" tick={chartStyle} axisLine={false} tickLine={false} />
            <YAxis tick={chartStyle} axisLine={false} tickLine={false} width={25} />
            <Tooltip content={<CustomTooltip />} />
            <Area type="monotone" dataKey="people"   stroke="#22c55e" fill="#22c55e" fillOpacity={0.1} strokeWidth={2} name="People" />
            <Area type="monotone" dataKey="vehicles" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.1} strokeWidth={2} name="Vehicles" />
            <Area type="monotone" dataKey="alerts"   stroke="#ef4444" fill="#ef4444" fillOpacity={0.1} strokeWidth={2} name="Alerts" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* ── Bottom row: Bar + Pie ─────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Alerts by Camera */}
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
          <h3 className="text-sm font-bold text-white light:text-slate-900 mb-4">Alerts by Camera</h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={cameraData} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#272b37" vertical={false} />
              <XAxis dataKey="camera" tick={chartStyle} axisLine={false} tickLine={false} />
              <YAxis tick={chartStyle} axisLine={false} tickLine={false} width={20} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="count" fill="#22c55e" fillOpacity={0.8} radius={[4, 4, 0, 0]} name="Alerts" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Threat Breakdown Pie */}
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
          <h3 className="text-sm font-bold text-white light:text-slate-900 mb-4">Threat Level Breakdown</h3>
          <div className="flex items-center gap-4">
            <ResponsiveContainer width="60%" height={180}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={75} dataKey="value" strokeWidth={0}>
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i]} fillOpacity={0.85} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>

            <div className="flex flex-col gap-2 flex-1">
              {pieData.map((entry, i) => (
                <div key={entry.name} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i] }} />
                    <span className="text-[#9aa2b5] light:text-slate-600 font-medium">{entry.name}</span>
                  </div>
                  <span className="font-mono font-bold" style={{ color: COLORS[i] }}>{entry.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

