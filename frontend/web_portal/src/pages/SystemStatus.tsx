import { CheckCircle2, XCircle, AlertTriangle, Wifi, WifiOff, Database, HardDrive, Cpu, Clock } from 'lucide-react';
import { useStore } from '../store/useStore';
import { ProgressBar } from '../components/ui/Card';
import { useCameras } from '../hooks/useCameras';
import { useEffect, useState } from 'react';

function ServiceRow({
  icon: Icon,
  service,
  status,
  value,
  sub,
}: {
  icon: typeof Cpu;
  service: string;
  status: 'ok' | 'warn' | 'error' | 'off';
  value: string;
  sub?: string;
}) {
  const StatusIcon =
    status === 'ok'   ? CheckCircle2 :
    status === 'warn' ? AlertTriangle :
    status === 'error'? XCircle :
    XCircle;

  const iconColor =
    status === 'ok'    ? 'text-[#22c55e] light:text-[#15803d]' :
    status === 'warn'  ? 'text-yellow-400 light:text-yellow-600' :
    status === 'error' ? 'text-red-400 light:text-red-600'    :
    'text-[#62697b] light:text-slate-400';

  return (
    <div className="flex items-center justify-between py-3 border-b border-[#272b37] light:border-[#d3d8e3] last:border-0">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-xl bg-[#191c24] light:bg-slate-100 border border-[#272b37] light:border-slate-300 flex items-center justify-center flex-shrink-0">
          <Icon size={15} className="text-[#9aa2b5] light:text-slate-600" />
        </div>
        <div>
          <div className="text-sm font-semibold text-white light:text-slate-900">{service}</div>
          {sub && <div className="text-[11px] text-[#9aa2b5] light:text-slate-500">{sub}</div>}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <span className={`text-xs font-mono font-bold ${iconColor}`}>{value}</span>
        <StatusIcon size={16} className={iconColor} />
      </div>
    </div>
  );
}

export default function SystemStatus() {
  useCameras();
  const sys     = useStore((s) => s.systemStatus);
  const cameras = useStore((s) => s.cameras);
  const isMock  = useStore((s) => s.isMockMode);
  const [uptime, setUptime] = useState(sys.uptime_seconds);

  // Tick uptime in mock mode
  useEffect(() => {
    if (!isMock) return;
    const t = setInterval(() => setUptime((u) => u + 1), 1000);
    return () => clearInterval(t);
  }, [isMock]);

  const online      = cameras.filter((c) => c.status === 'ONLINE').length;
  const aiRunning   = cameras.filter((c) => c.ai_status === 'RUNNING').length;
  const storagePct  = sys.storage_total_mb > 0
    ? (sys.storage_used_mb / sys.storage_total_mb) * 100
    : 0;

  const fmt = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${h}h ${m}m ${sec}s`;
  };

  return (
    <div className="space-y-4">
      {/* Mock mode notice */}
      {isMock && (
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-2xl px-4 py-3 flex items-center gap-3">
          <AlertTriangle size={16} className="text-purple-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-purple-300">Running in Mock Mode</p>
            <p className="text-xs text-purple-400 mt-0.5">
              Status below is simulated. Set VITE_USE_MOCK=false and start the backend to see real data.
            </p>
          </div>
        </div>
      )}

      {/* Services */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
          <h3 className="text-sm font-bold text-white light:text-slate-900 pb-3 border-b border-[#272b37] light:border-[#d3d8e3]">Core Services</h3>
          <ServiceRow
            icon={Cpu}
            service="FastAPI Backend"
            status={sys.backend_status === 'ONLINE' ? 'ok' : 'error'}
            value={sys.backend_status}
            sub="http://localhost:8000"
          />
          <ServiceRow
            icon={Database}
            service="SQLite Database"
            status={sys.database_status === 'OK' ? 'ok' : 'error'}
            value={sys.database_status}
            sub="ibvap.db"
          />
          <ServiceRow
            icon={sys.websocket_connected ? Wifi : WifiOff}
            service="WebSocket"
            status={sys.websocket_connected ? 'ok' : 'error'}
            value={sys.websocket_connected ? 'CONNECTED' : 'DISCONNECTED'}
            sub="ws://localhost:8000/ws/alerts"
          />
          <ServiceRow
            icon={HardDrive}
            service="Storage"
            status={storagePct > 90 ? 'warn' : 'ok'}
            value={`${sys.storage_used_mb} MB`}
            sub={`${storagePct.toFixed(1)}% used`}
          />
        </div>

        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
          <h3 className="text-sm font-bold text-white light:text-slate-900 pb-3 border-b border-[#272b37] light:border-[#d3d8e3]">AI Engine</h3>
          <ServiceRow
            icon={Cpu}
            service="AI Engine Status"
            status={sys.ai_engine_status === 'RUNNING' ? 'ok' : sys.ai_engine_status === 'ERROR' ? 'error' : 'off'}
            value={sys.ai_engine_status}
            sub={sys.model_name}
          />
          <ServiceRow
            icon={Cpu}
            service="Frame Rate"
            status={sys.fps > 20 ? 'ok' : sys.fps > 10 ? 'warn' : 'error'}
            value={`${sys.fps.toFixed(1)} FPS`}
            sub="Target: 25 FPS"
          />
          <ServiceRow
            icon={Cpu}
            service="Processing Time"
            status={sys.processing_time_ms < 50 ? 'ok' : sys.processing_time_ms < 100 ? 'warn' : 'error'}
            value={`${sys.processing_time_ms}ms`}
            sub="Per frame inference"
          />
          <ServiceRow
            icon={Clock}
            service="Cameras w/ AI"
            status={aiRunning > 0 ? 'ok' : 'off'}
            value={`${aiRunning} / ${cameras.length}`}
            sub="AI monitoring active"
          />
        </div>
      </div>

      {/* Storage + Uptime */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 space-y-3 shadow-card transition-colors">
          <h3 className="text-sm font-bold text-white light:text-slate-900">Storage</h3>
          <ProgressBar
            value={storagePct}
            label={`${sys.storage_used_mb} MB / ${sys.storage_total_mb} MB`}
            showValue
          />
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-2">
              <div className="text-[#9aa2b5] light:text-slate-500 mb-0.5">Used</div>
              <div className="font-mono text-white light:text-slate-900 font-bold">{(sys.storage_used_mb / 1024).toFixed(2)} GB</div>
            </div>
            <div className="bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-2">
              <div className="text-[#9aa2b5] light:text-slate-500 mb-0.5">Free</div>
              <div className="font-mono text-white light:text-slate-900 font-bold">
                {((sys.storage_total_mb - sys.storage_used_mb) / 1024).toFixed(2)} GB
              </div>
            </div>
          </div>
        </div>

        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 space-y-3 shadow-card transition-colors">
          <h3 className="text-sm font-bold text-white light:text-slate-900">Runtime Info</h3>
          <div className="space-y-2">
            {[
              { label: 'System Uptime',  value: fmt(uptime), mono: true },
              { label: 'AI Model',       value: sys.model_name, mono: true },
              { label: 'Alerts Today',   value: String(sys.alerts_today), mono: true },
              { label: 'Cameras Online', value: `${online} / ${cameras.length}`, mono: true },
            ].map(({ label, value, mono }) => (
              <div key={label} className="flex justify-between items-center py-2 border-b border-[#272b37] light:border-[#d3d8e3] last:border-0">
                <span className="text-xs text-[#9aa2b5] light:text-slate-500 font-medium">{label}</span>
                <span className={`text-xs text-white light:text-slate-900 font-semibold ${mono ? 'font-mono' : ''}`}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
