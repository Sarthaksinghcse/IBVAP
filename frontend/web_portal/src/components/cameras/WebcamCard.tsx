import { useRef, useEffect } from 'react';
import { Camera, Video, VideoOff, AlertCircle, ShieldAlert, MonitorPlay } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../../store/useStore';

export function WebcamCard() {
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const isWebcamActive   = useStore((s) => s.isWebcamActive);
  const webcamStream     = useStore((s) => s.webcamStream);
  const webcamError      = useStore((s) => s.webcamError);
  const webcamResolution = useStore((s) => s.webcamResolution);
  const startWebcam      = useStore((s) => s.startWebcam);
  const stopWebcam       = useStore((s) => s.stopWebcam);
  const setCameraMode    = useStore((s) => s.setCameraMode);

  useEffect(() => {
    if (videoRef.current) {
      if (webcamStream) {
        videoRef.current.srcObject = webcamStream;
        videoRef.current.play().catch((err) => console.warn('[WebcamCard] Play error:', err));
      } else {
        videoRef.current.srcObject = null;
      }
    }
  }, [webcamStream, isWebcamActive]);

  const handleConnect = async () => {
    await startWebcam();
  };

  const handleDisconnect = () => {
    stopWebcam();
  };

  const handleViewInMonitor = () => {
    setCameraMode(true);
    navigate('/monitoring');
  };

  return (
    <div className="ibvap-card p-0 overflow-hidden border-[#1e2d4a] light:border-[#d1d5db] hover:border-[#253a5e] light:hover:border-slate-400 transition-all">
      {/* Top Banner / Badge */}
      <div className="px-4 py-2.5 bg-[#080d1c] light:bg-slate-50 border-b border-[#1e2d4a] light:border-[#d1d5db] flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider bg-amber-500/15 border border-amber-500/30 text-amber-400 light:text-amber-700">
            DEMO SOURCE
          </span>
          <span className="text-sm font-semibold text-slate-200 light:text-slate-900">
            Local Laptop Webcam
          </span>
          <span className="text-slate-600 light:text-slate-400">·</span>
          <span className="text-xs text-slate-400 light:text-slate-600">
            Browser MediaStream
          </span>
        </div>

        <div className="flex items-center gap-2">
          {isWebcamActive ? (
            <div className="flex items-center gap-1.5 bg-green-500/10 light:bg-emerald-50 border border-green-500/30 light:border-emerald-300 px-2 py-0.5 rounded text-[11px] font-mono text-green-400 light:text-[#15803d] font-bold">
              <span className="w-2 h-2 rounded-full bg-green-400 light:bg-[#15803d] animate-pulse" />
              CONNECTED / LIVE
            </div>
          ) : (
            <div className="flex items-center gap-1.5 bg-slate-800/60 light:bg-slate-100 border border-slate-700/50 light:border-slate-300 px-2 py-0.5 rounded text-[11px] font-mono text-slate-400 light:text-slate-600">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
              DISCONNECTED
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-0">
        {/* Video Preview Container */}
        <div className="md:col-span-6 lg:col-span-7 relative h-56 md:h-64 cctv-bg flex items-center justify-center overflow-hidden border-b md:border-b-0 md:border-r border-[#1e2d4a] light:border-[#d1d5db]">
          {isWebcamActive && webcamStream ? (
            <>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover z-0"
              />
              <div className="cctv-scanline pointer-events-none" />
              <div className="cctv-vignette pointer-events-none" />

              {/* Watermark badge */}
              <div className="absolute top-2 left-2 flex items-center gap-1 bg-black/70 px-2 py-0.5 rounded border border-white/10 text-[10px] font-mono text-amber-400 z-10">
                <Camera size={11} /> LOCAL WEBCAM
              </div>

              {/* Live indicator */}
              <div className="absolute top-2 right-2 flex items-center gap-1 bg-black/70 px-2 py-0.5 rounded border border-white/10 z-10">
                <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                <span className="text-[9px] font-mono text-red-400 font-bold">LIVE DEMO</span>
              </div>

              {/* Resolution tag */}
              <div className="absolute bottom-2 right-2 bg-black/70 px-2 py-0.5 rounded border border-white/10 text-[9px] font-mono text-slate-400 z-10">
                {webcamResolution || '1920x1080'}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center p-6 text-center z-10">
              <div className="w-12 h-12 rounded-full bg-[#141e33] light:bg-slate-100 border border-[#1e2d4a] light:border-slate-300 flex items-center justify-center text-slate-500 mb-2">
                <Video size={22} className="text-slate-400 light:text-slate-600" />
              </div>
              <p className="text-xs font-medium text-slate-300 light:text-slate-900">Laptop Webcam Disconnected</p>
              <p className="text-[11px] text-slate-500 light:text-slate-600 mt-0.5 max-w-xs">
                Click "Connect Local Webcam" to demonstrate receiving a live camera feed inside the SHIELD interface.
              </p>
            </div>
          )}
        </div>

        {/* Info & Controls Panel */}
        <div className="md:col-span-6 lg:col-span-5 p-4 flex flex-col justify-between space-y-4 bg-[#0a0f1d] light:bg-white">
          <div className="space-y-3">
            <div>
              <h4 className="text-sm font-semibold text-slate-200 light:text-slate-900 flex items-center gap-1.5">
                <Camera size={14} className="text-blue-400 light:text-blue-600" />
                Laptop Built-in Camera Integration
              </h4>
              <p className="text-xs text-slate-400 light:text-slate-600 mt-1 leading-relaxed">
                Demonstrates local browser-based live video streaming without altering backend CCTV telemetry or CCTV recording channels.
              </p>
            </div>

            {/* Error Message Display */}
            {webcamError && (
              <div className="p-2.5 rounded bg-red-500/10 border border-red-500/30 text-red-400 light:text-red-700 text-xs flex items-start gap-2 animate-fadeIn">
                <AlertCircle size={14} className="flex-shrink-0 mt-0.5 text-red-400 light:text-red-600" />
                <div className="flex-1">
                  <span className="font-semibold">Access Error:</span> {webcamError}
                </div>
              </div>
            )}

            {/* Metadata specs */}
            <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
              <div className="bg-[#141e33]/70 light:bg-slate-50 p-2 rounded border border-[#1e2d4a] light:border-slate-200">
                <span className="text-slate-500 light:text-slate-500 block text-[9px] uppercase">Source Type</span>
                <span className="text-slate-300 light:text-slate-900 font-semibold">Local MediaStream</span>
              </div>
              <div className="bg-[#141e33]/70 light:bg-slate-50 p-2 rounded border border-[#1e2d4a] light:border-slate-200">
                <span className="text-slate-500 light:text-slate-500 block text-[9px] uppercase">Resolution</span>
                <span className="text-slate-300 light:text-slate-900 font-semibold">{webcamResolution || 'Auto (1080p)'}</span>
              </div>
              <div className="bg-[#141e33]/70 light:bg-slate-50 p-2 rounded border border-[#1e2d4a] light:border-slate-200">
                <span className="text-slate-500 light:text-slate-500 block text-[9px] uppercase">Audio Access</span>
                <span className="text-green-400 light:text-[#15803d] font-semibold">Disabled (Video Only)</span>
              </div>
              <div className="bg-[#141e33]/70 light:bg-slate-50 p-2 rounded border border-[#1e2d4a] light:border-slate-200">
                <span className="text-slate-500 light:text-slate-500 block text-[9px] uppercase">Storage / Upload</span>
                <span className="text-slate-400 light:text-slate-600 font-semibold">None (Browser Local)</span>
              </div>
            </div>

            <div className="text-[10px] text-slate-500 light:text-slate-600 flex items-start gap-1 bg-[#101726] light:bg-slate-50 p-2 rounded border border-[#1e2d4a]/60 light:border-slate-200">
              <ShieldAlert size={12} className="text-amber-400 light:text-amber-600 flex-shrink-0 mt-0.5" />
              <span>
                <strong className="text-slate-300 light:text-slate-900">Privacy Guard:</strong> Webcam frames remain strictly local in your browser and are never uploaded or recorded to the server.
              </span>
            </div>
          </div>

          {/* Action buttons */}
          <div className="pt-2 border-t border-[#1e2d4a] light:border-slate-200 flex items-center gap-2 flex-wrap">
            {!isWebcamActive ? (
              <button
                onClick={handleConnect}
                className="ibvap-btn-primary text-xs py-2 px-4 flex items-center gap-1.5 flex-1 justify-center shadow-glow-accent cursor-pointer"
              >
                <Video size={14} /> Connect Local Webcam
              </button>
            ) : (
              <>
                <button
                  onClick={handleDisconnect}
                  className="text-xs py-2 px-3 rounded font-medium bg-red-500/20 hover:bg-red-500/30 text-red-300 light:text-red-700 light:bg-red-50 light:border-red-200 border border-red-500/40 transition-all flex items-center gap-1.5 justify-center cursor-pointer"
                >
                  <VideoOff size={14} /> Disconnect Webcam
                </button>
                <button
                  onClick={handleViewInMonitor}
                  className="ibvap-btn-primary text-xs py-2 px-3 flex items-center gap-1.5 flex-1 justify-center cursor-pointer"
                >
                  <MonitorPlay size={14} /> View in Live Monitor
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

