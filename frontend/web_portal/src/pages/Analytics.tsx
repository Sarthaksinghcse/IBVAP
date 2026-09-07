import { useMemo } from 'react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
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

