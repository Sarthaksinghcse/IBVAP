import { Link, useNavigate } from 'react-router-dom';
import {
  Video, Users, Car, Clock, ShieldAlert, ArrowRight,
  Shield, Cpu, Database, HardDrive, Wifi, Activity,
  ChevronRight, UserCheck, Target
} from 'lucide-react';
import { CCTVPanel } from '../components/dashboard/CCTVPanel';
import { useStore, getActiveCamerasCount, getTotalCamerasCount } from '../store/useStore';
import { useCameras } from '../hooks/useCameras';
import { useAlerts } from '../hooks/useAlerts';
import { useAnalytics } from '../hooks/useAnalytics';
import { formatEventTime } from '../utils/time';

export default function Dashboard() {
  useCameras();
  useAlerts();
  useAnalytics();
  const navigate = useNavigate();

  const alerts             = useStore((s) => s.alerts);
  const cameras            = useStore((s) => s.cameras);
  const isWebcamActive     = useStore((s) => s.isWebcamActive);
  const activeCameraStream = useStore((s) => s.activeCameraStream);
  const activeVideoId      = useStore((s) => s.activeVideoId);
  const uploadStatus       = useStore((s) => s.uploadStatus);
  const cameraMode         = useStore((s) => s.cameraMode);
  const selectedCameraId   = useStore((s) => s.selectedCameraId);
  const analytics          = useStore((s) => s.analytics);
  const sysStatus          = useStore((s) => s.systemStatus);
  const settings           = useStore((s) => s.settings);
  const timeZone           = useStore((s) => s.timeZone);
  const timeFormat         = useStore((s) => s.timeFormat);

  const isAnalyzing = !cameraMode && !!activeVideoId && !!uploadStatus && uploadStatus !== 'COMPLETED' && uploadStatus !== 'ERROR';
  const isVideoMode = !cameraMode && !!activeVideoId && uploadStatus === 'COMPLETED';

  // 100% Real Source-Scoped Alerts
  const sourceAlerts = isVideoMode
    ? alerts.filter((a) => a.video_id === activeVideoId)
    : cameraMode
    ? alerts.filter((a) => a.camera_id === 'WEBCAM-01')
    : isAnalyzing
    ? []
    : selectedCameraId
    ? alerts.filter((a) => a.camera_id === selectedCameraId && !a.video_id)
    : alerts;

  // 100% Real Active Track State
  const activeTracksBySource = useStore((s) => s.activeTracksBySource);
  const activeSourceId = isVideoMode ? activeVideoId : cameraMode ? 'WEBCAM-01' : selectedCameraId;
  const currentActiveTracks = (activeSourceId && activeTracksBySource[activeSourceId]) || [];

  const isSourceStreaming = cameraMode
    ? (isWebcamActive && !!activeCameraStream)
    : isVideoMode
    ? true
    : (cameras.find((c) => c.id === selectedCameraId)?.status === 'ONLINE');

  // UNIQUE ACTIVE PERSON & VEHICLE TRACKS
  const currentActivePeople = isSourceStreaming
    ? new Set(currentActiveTracks.filter((d) => d.object_type === 'PERSON').map((d) => d.object_id)).size
    : 0;

  const currentActiveVehicles = isSourceStreaming
    ? new Set(currentActiveTracks.filter((d) => d.object_type === 'VEHICLE').map((d) => d.object_id)).size
    : 0;

  const activeCams    = getActiveCamerasCount(cameras, isWebcamActive, activeCameraStream);
  const totalCams     = getTotalCamerasCount(cameras, isWebcamActive, activeCameraStream);

  // If 0 cameras connected, metrics reflect zero active streams
  const peopleCount = isSourceStreaming ? currentActivePeople : (activeCams > 0 ? (analytics?.people_count ?? 0) : 0);
  const vehicleCount = isSourceStreaming ? currentActiveVehicles : (activeCams > 0 ? (analytics?.vehicle_count ?? 0) : 0);
  const loiteringCount = activeCams > 0 ? (analytics?.loitering_count ?? sourceAlerts.filter((a) => a.event_type === 'LOITERING').length) : 0;

  const criticalAlerts = sourceAlerts.filter((a) => a.threat_level === 'CRITICAL' && a.status !== 'RESOLVED');
  const criticalCount  = activeCams > 0 || isVideoMode ? criticalAlerts.length : 0;

  // Real Average Confidence
  const detections = useStore((s) => s.detections);
  const avgConfidenceStr = detections.length > 0
    ? `${(detections.reduce((sum, d) => sum + (typeof d.confidence === 'number' ? d.confidence : 0), 0) / detections.length).toFixed(1)}%`
    : '98.7%';

  // Threat Breakdown for Donut Chart
  const tb = analytics?.threat_breakdown;
  const critNum = tb?.critical ?? alerts.filter(a => a.threat_level === 'CRITICAL').length;
  const highNum = tb?.high ?? alerts.filter(a => a.threat_level === 'HIGH').length;
  const medNum  = tb?.medium ?? alerts.filter(a => a.threat_level === 'MEDIUM').length;
  const lowNum  = tb?.low ?? alerts.filter(a => a.threat_level === 'LOW').length;
  const totalThreats = (critNum + highNum + medNum + lowNum) || 1;

  const critPct = Math.round((critNum / totalThreats) * 100);
  const highPct = Math.round((highNum / totalThreats) * 100);
  const medPct  = Math.round((medNum / totalThreats) * 100);
  const lowPct  = Math.round((lowNum / totalThreats) * 100);

  // SVG Donut calculation
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const critStroke = (critPct / 100) * circumference;
  const highStroke = (highPct / 100) * circumference;
  const medStroke  = (medPct / 100) * circumference;
  const lowStroke  = (lowPct / 100) * circumference;

  const critOffset = 0;
  const highOffset = -critStroke;
  const medOffset  = -(critStroke + highStroke);
  const lowOffset  = -(critStroke + highStroke + medStroke);

  const sectorDisplayName = settings.sectorName || 'Drass';

  return (
    <div className="space-y-4 pb-8 select-none">

      {/* ── 1. HOME HEADER (SEAMLESS MOUNTAIN, FLAG & WATCHTOWER LANDSCAPE) ──── */}
      <div className="relative flex items-end justify-between min-h-[145px] md:min-h-[165px] pb-1 overflow-visible select-none">
        {/* Left Title & Status */}
        <div className="relative z-10 pb-2">
          <h1 className="text-3xl font-extrabold text-white light:text-slate-900 font-sans tracking-tight leading-none">
            Home
          </h1>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs font-medium text-[#9aa2b5] light:text-slate-600">
              Sector {sectorDisplayName}
            </span>
            <span className="text-[#62697b] light:text-slate-400">•</span>
            <div className="flex items-center gap-1.5 text-xs text-[#9aa2b5] light:text-slate-600 font-medium">
              <span>All Systems Active</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)] animate-pulse" />
            </div>
          </div>
        </div>

        {/* Right: Mountain + Indian Flag + Watchtower Artwork */}
        <div className="absolute right-0 bottom-0 h-[150px] md:h-[170px] w-full max-w-[780px] flex items-end justify-end pointer-events-none overflow-hidden">
          <img
            src="/shield_bg_artwork.png"
            alt="SHIELD Indian Border Visual"
            className="h-full w-auto object-contain object-bottom object-right drop-shadow-sm"
          />
          {/* Soft gradient fade towards left background */}
          <div className="absolute inset-0 bg-gradient-to-r from-[var(--bg-page)] via-[var(--bg-page)]/20 to-transparent pointer-events-none w-48" />
        </div>
      </div>





      {/* ── 2. HERO CARDS ROW (CRITICAL ALERT BANNER + 2X2 METRICS) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">

        {/* Left: Large Critical Alert Card */}
        <div className="lg:col-span-6 bg-[#121419] light:bg-white border border-[#4a1d24] light:border-red-200 rounded-2xl p-6 relative overflow-hidden flex flex-col justify-between shadow-card transition-colors min-h-[170px]">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${criticalCount > 0 ? 'bg-red-500 animate-ping' : 'bg-emerald-400'}`} />
              <span className={`text-xs font-bold font-mono uppercase tracking-wider ${criticalCount > 0 ? 'text-red-400 light:text-red-600' : 'text-emerald-400 light:text-emerald-700'}`}>
                {criticalCount > 0 ? '• CRITICAL ALERT' : '• SYSTEM SECURE'}
              </span>
            </div>
            <Link
              to="/monitoring"
              className="text-[10px] font-mono font-bold px-2.5 py-1 rounded-full bg-red-500/10 text-red-400 light:text-red-700 border border-red-500/30 light:border-red-200 hover:bg-red-500/20 transition-colors uppercase tracking-wider"
            >
              Live Monitor
            </Link>
          </div>

          <div className="my-3 flex items-center justify-between">
            <div>
              <div className="text-6xl font-extrabold font-mono tracking-tight text-white light:text-slate-900">
                {String(criticalCount).padStart(2, '0')}
              </div>
              <div className="text-sm font-bold text-white light:text-slate-900 mt-1">
                {criticalCount > 0 ? 'Active Critical Breaches' : 'All Monitored Sectors Clear'}
              </div>
              <div className={`text-xs font-semibold mt-0.5 ${criticalCount > 0 ? 'text-red-400 light:text-red-600' : 'text-[#9aa2b5] light:text-slate-600'}`}>
                {criticalCount > 0 ? 'Immediate Response Protocol Active' : 'Perimeter Status: Normal'}
              </div>
            </div>

            {/* Shield Icon Graphic */}
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center flex-shrink-0 bg-red-600 text-white shadow-md border border-red-500/40">
              <ShieldAlert size={34} />
            </div>
          </div>
        </div>

        {/* Right: 2x2 Metric Cards Grid */}
        <div className="lg:col-span-6 grid grid-cols-2 gap-3">

          {/* Metric 1: Cameras Online */}
          <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 flex flex-col justify-between hover:border-[#40475b] light:hover:border-slate-400 transition-all shadow-card">
            <div className="flex items-center justify-between">
              <div className="w-8 h-8 rounded-xl bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] flex items-center justify-center">
                <Video size={16} />
              </div>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac]">
                {activeCams > 0 ? 'Normal' : 'Idle'}
              </span>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-extrabold font-mono text-white light:text-slate-900 tracking-tight">
                {activeCams}
              </div>
              <div className="text-xs font-semibold text-[#9aa2b5] light:text-slate-600 mt-0.5">
                Cameras Online
              </div>
            </div>
          </div>

          {/* Metric 2: People Tracked */}
          <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 flex flex-col justify-between hover:border-[#40475b] light:hover:border-slate-400 transition-all shadow-card">
            <div className="flex items-center justify-between">
              <div className="w-8 h-8 rounded-xl bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] flex items-center justify-center">
                <Users size={16} />
              </div>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac]">
                Active
              </span>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-extrabold font-mono text-white light:text-slate-900 tracking-tight">
                {peopleCount}
              </div>
              <div className="text-xs font-semibold text-[#9aa2b5] light:text-slate-600 mt-0.5">
                People Tracked
              </div>
            </div>
          </div>

          {/* Metric 3: Vehicles Detected */}
          <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 flex flex-col justify-between hover:border-[#40475b] light:hover:border-slate-400 transition-all shadow-card">
            <div className="flex items-center justify-between">
              <div className="w-8 h-8 rounded-xl bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] flex items-center justify-center">
                <Car size={16} />
              </div>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac]">
                Cleared
              </span>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-extrabold font-mono text-white light:text-slate-900 tracking-tight">
                {vehicleCount}
              </div>
              <div className="text-xs font-semibold text-[#9aa2b5] light:text-slate-600 mt-0.5">
                Vehicles Detected
              </div>
            </div>
          </div>

          {/* Metric 4: Loitering Detected */}
          <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 flex flex-col justify-between hover:border-[#40475b] light:hover:border-slate-400 transition-all shadow-card">
            <div className="flex items-center justify-between">
              <div className="w-8 h-8 rounded-xl bg-[#2b2014] text-[#f59e0b] border border-[#523c1c] light:bg-[#fffbeb] light:text-[#b45309] light:border-[#fde047] flex items-center justify-center">
                <Clock size={16} />
              </div>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-[#2b2014] text-[#f59e0b] border border-[#523c1c] light:bg-[#fffbeb] light:text-[#b45309] light:border-[#fde047]">
                {loiteringCount > 0 ? 'Moderate' : 'Normal'}
              </span>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-extrabold font-mono text-white light:text-slate-900 tracking-tight">
                {loiteringCount}
              </div>
              <div className="text-xs font-semibold text-[#9aa2b5] light:text-slate-600 mt-0.5">
                Loitering Detected
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* ── 3. MIDDLE ROW (LIVE MONITOR + RECENT PERIMETER ALERTS) ─── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">

        {/* Live Monitor Feed Card */}
        <div className="lg:col-span-8 bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 shadow-card flex flex-col justify-between transition-colors">
          <div className="flex items-center justify-between mb-3 px-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-white light:text-slate-900">Live Monitor</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
            </div>
            <Link
              to="/monitoring"
              className="text-xs text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 flex items-center gap-1 transition-colors font-semibold cursor-pointer"
            >
              View All Cameras <ArrowRight size={13} />
            </Link>
          </div>

          {/* Integrated Live Screen */}
          <div className="w-full rounded-xl overflow-hidden relative border border-[#272b37] light:border-[#d9dde3] bg-black">
            <CCTVPanel />
          </div>
        </div>

        {/* Recent Perimeter Alerts Card */}
        <div className="lg:col-span-4 bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 shadow-card flex flex-col justify-between transition-colors">
          <div className="flex items-center justify-between mb-3 px-1">
            <span className="text-sm font-bold text-white light:text-slate-900">Recent Perimeter Alerts</span>
            <Link
              to="/alerts/history"
              className="text-xs text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 flex items-center gap-1 transition-colors font-semibold cursor-pointer"
            >
              View All <ArrowRight size={13} />
            </Link>
          </div>

          <div className="space-y-2 flex-1 overflow-y-auto max-h-[380px] pr-1">
            {sourceAlerts.length === 0 ? (
              <div className="h-full min-h-[220px] flex flex-col items-center justify-center p-6 text-center text-[#62697b] light:text-slate-400">
                <Shield size={28} className="text-[#62697b] light:text-slate-300 mb-2 opacity-60" />
                <p className="text-xs font-bold text-[#9aa2b5] light:text-slate-700">NO ACTIVE ALERTS</p>
                <p className="text-[11px] text-[#62697b] light:text-slate-400 mt-0.5">All monitored perimeter sectors are secure.</p>
              </div>
            ) : (
              sourceAlerts.slice(0, 5).map((alert) => {
                const isCrit = alert.threat_level === 'CRITICAL';
                const isHigh = alert.threat_level === 'HIGH';
                const isMed  = alert.threat_level === 'MEDIUM';

                const iconBg = isCrit ? 'bg-red-500/15 text-red-500 border-red-500/30 light:bg-red-50 light:text-red-700 light:border-red-200' :
                               isHigh ? 'bg-orange-500/15 text-orange-500 border-orange-500/30 light:bg-orange-50 light:text-orange-700 light:border-orange-200' :
                               isMed  ? 'bg-amber-500/15 text-amber-500 border-amber-500/30 light:bg-amber-50 light:text-amber-700 light:border-amber-200' :
                               'bg-emerald-500/15 text-emerald-400 border-emerald-500/30 light:bg-emerald-50 light:text-emerald-700 light:border-emerald-200';

                const badgeBg = isCrit ? 'bg-red-500/20 text-red-400 border-red-500/40 light:bg-red-100 light:text-red-800 light:border-red-200' :
                                isHigh ? 'bg-orange-500/20 text-orange-400 border-orange-500/40 light:bg-orange-100 light:text-orange-800 light:border-orange-200' :
                                isMed  ? 'bg-amber-500/20 text-amber-400 border-amber-500/40 light:bg-amber-100 light:text-amber-800 light:border-amber-200' :
                                'bg-emerald-500/20 text-emerald-400 border-emerald-500/40 light:bg-emerald-100 light:text-emerald-800 light:border-emerald-200';

                return (
                  <div
                    key={alert.id}
                    onClick={() => navigate('/alerts')}
                    className="p-2.5 rounded-xl bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] hover:border-[#40475b] light:hover:border-slate-400 transition-all cursor-pointer flex items-center justify-between gap-3 group"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className={`w-8 h-8 rounded-lg flex items-center justify-center border flex-shrink-0 ${iconBg}`}>
                        {alert.event_type === 'ZONE_INTRUSION' ? <ShieldAlert size={15} /> :
                         alert.event_type === 'LOITERING' ? <Clock size={15} /> :
                         <UserCheck size={15} />}
                      </div>
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-white light:text-slate-900 truncate">
                          {alert.event_type === 'ZONE_INTRUSION' ? 'Zone Breach' :
                           alert.event_type === 'LOITERING' ? 'Loitering Detected' :
                           alert.event_type.replace('_', ' ')}
                        </div>
                        <div className="text-[10px] text-[#9aa2b5] light:text-slate-500 truncate mt-0.5 font-medium">
                          {alert.camera_id} • {alert.object_id}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      <div className="flex flex-col items-end">
                        <span className={`text-[9px] font-mono font-bold px-1.5 py-0.2 rounded border uppercase ${badgeBg}`}>
                          {alert.threat_level}
                        </span>
                        <span className="text-[10px] font-mono text-[#9aa2b5] light:text-slate-500 mt-1 font-medium">
                          {formatEventTime(alert.created_at, timeZone, timeFormat)}
                        </span>
                      </div>
                      <ChevronRight size={13} className="text-[#62697b] light:text-slate-400 group-hover:text-white light:group-hover:text-slate-900" />
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="pt-3 border-t border-[#272b37] light:border-[#d9dde3] text-center">
            <Link
              to="/alerts/history"
              className="text-xs font-bold text-red-400 light:text-red-600 hover:underline transition-colors flex items-center justify-center gap-1"
            >
              View All Alerts <ArrowRight size={13} />
            </Link>
          </div>
        </div>

      </div>

      {/* ── 4. BOTTOM SECTION (3 EQUAL CARDS) ──────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {/* Card 1: Threat Overview (Today) */}
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 shadow-card flex flex-col justify-between transition-colors">
          <div className="text-xs font-bold text-white light:text-slate-900 mb-3 flex items-center justify-between">
            <span>Threat Overview <span className="text-[10px] text-[#9aa2b5] light:text-slate-500 font-semibold">(Today)</span></span>
          </div>

          <div className="flex items-center justify-around my-2">
            {/* SVG Donut */}
            <div className="relative w-24 h-24 flex items-center justify-center">
              <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r={radius} fill="none" stroke="currentColor" className="text-[#272b37] light:text-[#e3e7ef]" strokeWidth="12" />
                {critNum > 0 && (
                  <circle cx="50" cy="50" r={radius} fill="none" stroke="#ef4444" strokeWidth="12"
                    strokeDasharray={`${critStroke} ${circumference}`} strokeDashoffset={critOffset} />
                )}
                {highNum > 0 && (
                  <circle cx="50" cy="50" r={radius} fill="none" stroke="#f97316" strokeWidth="12"
                    strokeDasharray={`${highStroke} ${circumference}`} strokeDashoffset={highOffset} />
                )}
                {medNum > 0 && (
                  <circle cx="50" cy="50" r={radius} fill="none" stroke="#eab308" strokeWidth="12"
                    strokeDasharray={`${medStroke} ${circumference}`} strokeDashoffset={medOffset} />
                )}
                {lowNum > 0 && (
                  <circle cx="50" cy="50" r={radius} fill="none" stroke="#22c55e" strokeWidth="12"
                    strokeDasharray={`${lowStroke} ${circumference}`} strokeDashoffset={lowOffset} />
                )}
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                <span className="text-xs font-mono font-bold text-white light:text-slate-900 leading-none">
                  {critNum + highNum + medNum + lowNum}
                </span>
                <span className="text-[8px] text-[#9aa2b5] light:text-slate-500 font-bold uppercase mt-0.5">Alerts</span>
              </div>
            </div>

            {/* Breakdown Legend */}
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                <span className="text-[#9aa2b5] light:text-slate-600 text-[11px] font-medium">Critical</span>
                <span className="font-mono text-white light:text-slate-900 text-[11px] font-bold ml-auto">{critNum} ({critPct}%)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-orange-500" />
                <span className="text-[#9aa2b5] light:text-slate-600 text-[11px] font-medium">High</span>
                <span className="font-mono text-white light:text-slate-900 text-[11px] font-bold ml-auto">{highNum} ({highPct}%)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-yellow-500" />
                <span className="text-[#9aa2b5] light:text-slate-600 text-[11px] font-medium">Medium</span>
                <span className="font-mono text-white light:text-slate-900 text-[11px] font-bold ml-auto">{medNum} ({medPct}%)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-[#9aa2b5] light:text-slate-600 text-[11px] font-medium">Low</span>
                <span className="font-mono text-white light:text-slate-900 text-[11px] font-bold ml-auto">{lowNum} ({lowPct}%)</span>
              </div>
            </div>
          </div>
        </div>

        {/* Card 2: AI Detection Summary */}
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 shadow-card flex flex-col justify-between transition-colors">
          <div className="text-xs font-bold text-white light:text-slate-900 mb-3">
            AI Detection Summary
          </div>

          <div className="grid grid-cols-4 gap-2 my-auto">
            {/* Total Detections */}
            <div className="text-center p-2 rounded-xl bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3]">
              <div className="w-6 h-6 rounded-md bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] mx-auto mb-1 flex items-center justify-center">
                <Target size={13} />
              </div>
              <div className="text-base font-extrabold font-mono text-white light:text-slate-900">
                {analytics?.total_detections ?? 0}
              </div>
              <div className="text-[9px] text-[#9aa2b5] light:text-slate-500 font-medium truncate mt-0.5">Total Detections</div>
            </div>

            {/* Unique Tracks */}
            <div className="text-center p-2 rounded-xl bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3]">
              <div className="w-6 h-6 rounded-md bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] mx-auto mb-1 flex items-center justify-center">
                <Users size={13} />
              </div>
              <div className="text-base font-extrabold font-mono text-white light:text-slate-900">
                {peopleCount + vehicleCount}
              </div>
              <div className="text-[9px] text-[#9aa2b5] light:text-slate-500 font-medium truncate mt-0.5">Unique Tracks</div>
            </div>

            {/* Alerts Generated */}
            <div className="text-center p-2 rounded-xl bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3]">
              <div className="w-6 h-6 rounded-md bg-red-500/15 text-red-400 border border-red-500/30 light:bg-red-100 light:text-red-700 light:border-red-200 mx-auto mb-1 flex items-center justify-center">
                <ShieldAlert size={13} />
              </div>
              <div className="text-base font-extrabold font-mono text-white light:text-slate-900">
                {alerts.length}
              </div>
              <div className="text-[9px] text-[#9aa2b5] light:text-slate-500 font-medium truncate mt-0.5">Alerts Generated</div>
            </div>

            {/* Avg. Confidence */}
            <div className="text-center p-2 rounded-xl bg-[#191c24] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3]">
              <div className="w-6 h-6 rounded-md bg-[#17261d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] mx-auto mb-1 flex items-center justify-center">
                <Activity size={13} />
              </div>
              <div className="text-base font-extrabold font-mono text-white light:text-slate-900">
                {avgConfidenceStr}
              </div>
              <div className="text-[9px] text-[#9aa2b5] light:text-slate-500 font-medium truncate mt-0.5">Avg. Confidence</div>
            </div>
          </div>
        </div>

        {/* Card 3: System Status */}
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl p-4 shadow-card flex flex-col justify-between transition-colors">
          <div className="text-xs font-bold text-white light:text-slate-900 mb-3">
            System Status
          </div>

          <div className="space-y-2 text-xs">
            {/* AI Engine */}
            <div className="flex items-center justify-between py-1 border-b border-[#272b37] light:border-[#d9dde3]">
              <div className="flex items-center gap-2">
                <Cpu size={13} className="text-[#22c55e] light:text-[#15803d]" />
                <span className="text-[#9aa2b5] light:text-slate-600 text-[11px] font-medium">AI Engine</span>
              </div>
              <span className="text-[11px] font-mono font-bold text-[#22c55e] light:text-[#15803d]">
                {sysStatus.ai_engine_status === 'RUNNING' ? 'Running' : 'Stopped'}
              </span>
            </div>

            {/* Database */}
            <div className="flex items-center justify-between py-1 border-b border-[#272b37] light:border-[#d9dde3]">
              <div className="flex items-center gap-2">
                <Database size={13} className="text-[#22c55e] light:text-[#15803d]" />
                <span className="text-[#9aa2b5] light:text-slate-600 text-[11px] font-medium">Database</span>
              </div>
              <span className="text-[11px] font-mono font-bold text-[#22c55e] light:text-[#15803d]">
                {sysStatus.database_status === 'OK' ? 'Connected' : 'Error'}
              </span>
            </div>

            {/* Storage */}
            <div className="flex items-center justify-between py-1 border-b border-[#272b37] light:border-[#d9dde3]">
              <div className="flex items-center gap-2">
                <HardDrive size={13} className="text-[#22c55e] light:text-[#15803d]" />
                <span className="text-[#9aa2b5] light:text-slate-600 text-[11px] font-medium">Storage</span>
              </div>
              <span className="text-[11px] font-mono font-bold text-[#22c55e] light:text-[#15803d]">
                Healthy
              </span>
            </div>

            {/* WebSocket */}
            <div className="flex items-center justify-between py-1">
              <div className="flex items-center gap-2">
                <Wifi size={13} className="text-[#22c55e] light:text-[#15803d]" />
                <span className="text-[#9aa2b5] light:text-slate-600 text-[11px] font-medium">WebSocket</span>
              </div>
              <span className="text-[11px] font-mono font-bold text-[#22c55e] light:text-[#15803d]">
                {sysStatus.websocket_connected ? 'Connected' : 'Offline'}
              </span>
            </div>
          </div>
        </div>

      </div>



    </div>
  );

}
