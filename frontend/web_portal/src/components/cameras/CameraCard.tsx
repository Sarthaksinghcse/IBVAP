import { format } from 'date-fns';
import { useNavigate } from 'react-router-dom';
import { Camera, WifiOff, Cpu, Clock, ShieldAlert, Video, Smartphone, Trash2, Radio, Usb, Play } from 'lucide-react';
import { CameraStatusBadge, AIStatusBadge } from '../ui/Badge';
import { useStore } from '../../store/useStore';
import type { Camera as CameraType } from '../../types';

interface CameraCardProps {
  camera: CameraType;
  isSelected?: boolean;
  onClick?: () => void;
  onConfigureZone?: () => void;
  onDelete?: () => void;
  onTest?: () => void;
}

export function CameraCard({ camera, isSelected, onClick, onConfigureZone, onDelete, onTest }: CameraCardProps) {
  const navigate = useNavigate();
  const isOnline = camera.status === 'ONLINE';
  const isRunning = camera.ai_status === 'RUNNING';
  const zones = useStore((s) => s.zones);
  const setSelectedCamera = useStore((s) => s.setSelectedCamera);
  const setCameraMode = useStore((s) => s.setCameraMode);
  const setActiveVideoId = useStore((s) => s.setActiveVideoId);

  const handleWatchStream = (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setSelectedCamera(camera.id);
    setCameraMode(false);
    setActiveVideoId(null);
    if (onClick) onClick();
    navigate('/');
  };

  const cameraZone = zones[camera.id];
  const hasZone = Boolean(
    cameraZone && cameraZone.coordinates && cameraZone.coordinates.length >= 3 && cameraZone.enabled
  );

  const zonePointsStr = hasZone ? cameraZone.coordinates.map(([x, y]) => `${x},${y}`).join(' ') : '';
  const sourceType = camera.source_type || 'CCTV';

  return (
    <div
      className={`
        w-full text-left bg-[#121419] light:bg-white border rounded-2xl overflow-hidden transition-all duration-200 flex flex-col justify-between shadow-card
        ${isSelected
          ? 'border-[#22c55e] shadow-[0_0_12px_rgba(34,197,94,0.25)]'
          : 'border-[#272b37] light:border-[#d3d8e3] hover:border-[#40475b] light:hover:border-slate-400'
        }
      `}
    >
      {/* Camera "thumbnail" / Live stream preview */}
      <div
        onClick={handleWatchStream}
        className="relative h-32 bg-black flex items-center justify-center cursor-pointer select-none overflow-hidden group"
        title="Click to Watch Live Stream"
      >

        {/* Status overlay for offline/maintenance */}
        {!isOnline ? (
          <div className="absolute inset-0 bg-[#0a0e1a]/85 flex flex-col items-center justify-center gap-1 z-10">
            <WifiOff size={22} className="text-slate-600" />
            <span className="text-[10px] font-mono text-slate-500 uppercase font-semibold">
              {camera.status}
            </span>
          </div>
        ) : (
          <>
            {/* Live stream preview proxy if network camera */}
            {camera.stream_url ? (
              <img
                src={`/api/cameras/${camera.id}/stream`}
                alt={camera.name}
                className="w-full h-full object-cover z-0"
                onError={(e) => {
                  (e.currentTarget as HTMLElement).style.display = 'none';
                }}
              />
            ) : null}

            <div className="cctv-vignette pointer-events-none" />
            <div className="cctv-scanline pointer-events-none" />

            {/* Hover Play Overlay */}
            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center z-15 pointer-events-none">
              <div className="w-10 h-10 rounded-full bg-[#22c55e]/90 text-white flex items-center justify-center shadow-lg">
                <Play size={18} className="fill-white ml-0.5" />
              </div>
            </div>

            {/* Render real zone geometry if configured */}
            {hasZone && (
              <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 w-full h-full pointer-events-none z-5">
                <polygon
                  points={zonePointsStr}
                  fill="rgba(239, 68, 68, 0.22)"
                  stroke="#ef4444"
                  strokeWidth="1.2"
                  strokeDasharray="3,2"
                />
              </svg>
            )}
          </>
        )}

        {/* Top-left Badges: Source Type & AI Status */}
        <div className="absolute top-2 left-2 flex items-center gap-1.5 z-10">
          <span
            className={`px-1.5 py-0.5 rounded text-[8px] font-mono font-bold uppercase border flex items-center gap-1 ${
              sourceType === 'USB_PHONE'
                ? 'bg-cyan-500/20 border-cyan-500/40 text-cyan-300'
                : sourceType === 'WEBCAM'
                ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400'
                : sourceType === 'PHONE'
                ? 'bg-amber-500/20 border-amber-500/40 text-amber-400'
                : 'bg-blue-500/20 border-blue-500/40 text-blue-400'
            }`}
          >
            {sourceType === 'USB_PHONE' ? (
              <Usb size={9} />
            ) : sourceType === 'WEBCAM' ? (
              <Camera size={9} />
            ) : sourceType === 'PHONE' ? (
              <Smartphone size={9} />
            ) : (
              <Video size={9} />
            )}
            {sourceType === 'USB_PHONE'
              ? 'USB PHONE'
              : sourceType === 'PHONE'
              ? 'PHONE / WIFI'
              : sourceType === 'WEBCAM'
              ? 'LAPTOP WEBCAM'
              : sourceType === 'PLAYBACK'
              ? 'RECORDED FEED'
              : 'CCTV'}
          </span>

          {isOnline && isRunning && (
            <div className="flex items-center gap-1 bg-emerald-950/90 border border-emerald-500/40 px-1.5 py-0.5 rounded">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[8px] font-mono text-emerald-300 font-bold">AI RUNNING</span>
            </div>
          )}
        </div>

        {/* Live indicator */}
        {isOnline && (
          <div className="absolute top-2 right-2 flex items-center gap-1 bg-black/60 px-1.5 py-0.5 rounded z-10">
            <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-[livePulse_1.5s_ease-in-out_infinite]" />
            <span className="text-[9px] font-mono text-red-400 font-bold">LIVE</span>
          </div>
        )}

        {/* Camera name overlay */}
        <div className="absolute bottom-2 left-2 font-mono text-xs text-slate-200 bg-black/75 px-2 py-0.5 rounded border border-white/10 z-10 truncate max-w-[70%]">
          {camera.name}
        </div>

        {/* FPS */}
        {isOnline && (
          <div className="absolute bottom-2 right-2 font-mono text-[9px] text-slate-400 bg-black/70 px-1.5 py-0.5 rounded border border-white/10 z-10">
            {camera.fps != null && camera.fps > 0 ? `${camera.fps} FPS` : '25 FPS'}
          </div>
        )}
      </div>

      {/* Card info */}
      <div className="p-3.5 space-y-2.5 flex-1 flex flex-col justify-between">
        <div className="space-y-2">
          {/* Header row */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-200 light:text-slate-900 truncate">{camera.name}</span>
            <CameraStatusBadge status={camera.status} />
          </div>

          {/* Location */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400 light:text-slate-600">
            <Camera size={11} className="flex-shrink-0" />
            <span className="truncate">{camera.location}</span>
          </div>

          {/* Stream URL (if available) */}
          {camera.stream_url && (
            <div className="text-[10px] font-mono text-slate-500 light:text-slate-600 truncate bg-[#141e33] light:bg-slate-50 px-2 py-1 rounded border border-[#1e2d4a] light:border-slate-200">
              {camera.stream_url}
            </div>
          )}

          {/* AI status */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400 light:text-slate-600">
            <Cpu size={11} className="flex-shrink-0" />
            <AIStatusBadge status={camera.ai_status} />
          </div>

          {/* Zone status */}
          <div className="flex items-center justify-between text-xs pt-1.5 border-t border-[#1e2d4a]/70 light:border-slate-200">
            <div className="flex items-center gap-1.5 text-slate-400 light:text-slate-600">
              <ShieldAlert size={12} className={hasZone ? 'text-red-400' : 'text-slate-500 light:text-slate-400'} />
              <span className={`text-[11px] font-mono ${hasZone ? 'text-red-400 light:text-red-600 font-medium' : 'text-slate-500 light:text-slate-600'}`}>
                {hasZone ? cameraZone.name : 'No Zone Configured'}
              </span>
            </div>
            {onConfigureZone && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onConfigureZone();
                }}
                className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#141e33] light:bg-blue-50 hover:bg-[#1e2d4a] light:hover:bg-blue-100 text-blue-400 light:text-blue-700 border border-[#1e2d4a] light:border-blue-200 transition-all cursor-pointer font-semibold"
              >
                {hasZone ? 'Edit Zone' : 'Configure'}
              </button>
            )}
          </div>
        </div>

        {/* Footer & Actions */}
        <div className="flex items-center justify-between text-[10px] text-slate-500 light:text-slate-600 pt-2 border-t border-[#1e2d4a] light:border-slate-200">
          <div className="flex items-center gap-1 font-mono">
            <Clock size={10} />
            <span>{camera.last_activity ? format(new Date(camera.last_activity), 'HH:mm:ss') : 'Active'}</span>
            {camera.resolution && <span className="text-slate-600 light:text-slate-400">• {camera.resolution}</span>}
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleWatchStream}
              title="Watch Live Stream"
              className="px-2 py-1 rounded bg-[#22c55e]/15 light:bg-emerald-50 hover:bg-[#22c55e]/25 light:hover:bg-emerald-100 text-[#22c55e] light:text-[#15803d] border border-[#22c55e]/30 light:border-emerald-300 transition-all cursor-pointer font-mono text-[10px] font-semibold flex items-center gap-1"
            >
              <Video size={11} />
              <span>Watch Stream</span>
            </button>

            {onTest && camera.stream_url && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onTest();
                }}
                title="Test Stream Reachability"
                className="p-1 rounded bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 text-slate-400 light:text-slate-700 hover:text-emerald-400 border border-[#1e2d4a] light:border-slate-300 transition-all cursor-pointer"
              >
                <Radio size={11} />
              </button>
            )}

            {onDelete && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                }}
                title="Delete Camera"
                className="p-1 rounded bg-[#141e33] light:bg-red-50 hover:bg-red-500/20 light:hover:bg-red-100 text-slate-500 light:text-red-700 hover:text-red-400 border border-[#1e2d4a] light:border-red-200 transition-all cursor-pointer"
              >
                <Trash2 size={11} />
              </button>
            )}
          </div>
        </div>
      </div>

    </div>
  );
}


