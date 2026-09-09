import { useState } from 'react';
import { Camera, Maximize2, ShieldAlert, Wifi, WifiOff, Cpu, Video, Smartphone, Plus, Usb } from 'lucide-react';
import type { Camera as CameraType, Detection, Zone, AppSettings } from '../../types';

interface MultiCameraGridProps {
  cameras: CameraType[];
  selectedCamId: string;
  onSelectCamera: (camId: string) => void;
  onConfigureZone: (sourceId: string, sourceType: 'CAMERA' | 'WEBCAM') => void;
  zones: Record<string, Zone>;
  detections: Detection[];
  webcamDetections: Detection[];
  cameraVideoRef: any;
  isCameraMode: boolean;
  activeCameraStream: MediaStream | null;
  settings: AppSettings;
  onStartDeviceCamera: () => void;
  onOpenAddCamera?: () => void;
}

export function MultiCameraGrid({
  cameras,
  selectedCamId,
  onSelectCamera,
  onConfigureZone,
  zones,
  detections,
  webcamDetections,
  cameraVideoRef,
  isCameraMode,
  activeCameraStream,
  settings,
  onStartDeviceCamera,
  onOpenAddCamera,
}: MultiCameraGridProps) {
  // Collect actual live connected sources (online CCTV cameras + active webcam)
  const onlineCameras = cameras.filter((c) => c.status === 'ONLINE');

  // Determine grid columns dynamically based on active count (N real sources -> N real screens)
  const totalActive = onlineCameras.length + (isCameraMode && activeCameraStream ? 1 : 0);

  const gridClass =
    totalActive <= 1
      ? 'grid-cols-1'
      : totalActive === 2
      ? 'grid-cols-1 md:grid-cols-2'
      : totalActive <= 4
      ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2'
      : totalActive <= 6
      ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
      : 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4';

  return (
    <div className={`grid ${gridClass} gap-3 p-3 overflow-y-auto max-h-[500px] h-full w-full`}>
      {/* ── 1. REAL BROWSER DEVICE WEBCAM TILE (If Connected) ── */}
      {isCameraMode && activeCameraStream && (
        <div
          onClick={() => onSelectCamera('WEBCAM-01')}
          className={`relative rounded-md border overflow-hidden transition-all duration-200 cursor-pointer flex flex-col bg-[#0b1222] ${
            selectedCamId === 'WEBCAM-01'
              ? 'border-emerald-500 ring-1 ring-emerald-500/30'
              : 'border-[#1e2d4a] hover:border-emerald-500/50'
          }`}
          style={{ minHeight: totalActive <= 2 ? '250px' : '200px' }}
        >
          {/* Tile Header */}
          <div className="flex items-center justify-between px-3 py-2 bg-[#0a1020] border-b border-[#1e2d4a] z-10">
            <div className="flex items-center gap-2 min-w-0">
              <Camera size={13} className="text-emerald-400 flex-shrink-0" />
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-mono font-bold text-emerald-300">WEBCAM-01</span>
                  <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-950/80 border border-emerald-500/30 text-emerald-300 font-semibold">
                    LAPTOP WEBCAM
                  </span>
                </div>
                <p className="text-[10px] text-slate-400 truncate">Built-in MediaStream</p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              <span className="flex items-center gap-1 bg-emerald-950/80 border border-emerald-500/30 px-1.5 py-0.5 rounded text-[8px] font-mono text-emerald-300 font-bold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                LIVE
              </span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onConfigureZone('WEBCAM-01', 'WEBCAM');
                }}
                className={`p-1 transition-colors ${
                  zones['WEBCAM-01'] && zones['WEBCAM-01'].enabled ? 'text-red-400' : 'text-slate-500 hover:text-slate-300'
                }`}
                title="Configure Webcam Zone"
              >
                <ShieldAlert size={13} />
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectCamera('WEBCAM-01');
                }}
                className="p-1 text-slate-400 hover:text-blue-400 transition-colors"
                title="Focus / Enlarge"
              >
                <Maximize2 size={13} />
              </button>
            </div>
          </div>

          {/* Video Viewport with Live Stream */}
          <div className="relative flex-1 bg-black flex items-center justify-center overflow-hidden">
            <video
              ref={cameraVideoRef}
              autoPlay
              playsInline
              muted
              className="w-full h-full object-cover z-0"
            />

            {/* Webcam Specific Restricted Zone */}
            {settings.showRestrictedZone &&
              zones['WEBCAM-01'] &&
              zones['WEBCAM-01'].coordinates &&
              zones['WEBCAM-01'].coordinates.length >= 3 &&
              zones['WEBCAM-01'].enabled && (
                <div className="absolute inset-0 pointer-events-none z-10">
                  <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
                    <polygon
                      points={zones['WEBCAM-01'].coordinates.map(([x, y]) => `${x},${y}`).join(' ')}
                      fill="rgba(239, 68, 68, 0.16)"
                      stroke="#ef4444"
                      strokeWidth="1.2"
                      strokeDasharray="3,2"
                    />
                  </svg>
                  <div className="absolute top-2 left-2 bg-red-500/90 text-white text-[8px] font-mono font-bold px-1.5 py-0.5 rounded shadow">
                    {zones['WEBCAM-01'].name}
                  </div>
                </div>
              )}

            {/* Webcam Real YOLO Detections */}
            {settings.showBoundingBoxes &&
              webcamDetections
                .filter((d) => d?.bbox && typeof d.bbox.x === 'number' && typeof d.bbox.y === 'number' && typeof d.bbox.w === 'number' && typeof d.bbox.h === 'number')
                .map((det) => (
                <div
                  key={det.id}
                  className={`absolute border-2 pointer-events-none z-15 ${
                    det.is_in_restricted_zone ? 'border-red-500 bg-red-500/10' : 'border-green-500 bg-green-500/5'
                  }`}
                  style={{
                    left: `${det.bbox.x}%`,
                    top: `${det.bbox.y}%`,
                    width: `${det.bbox.w}%`,
                    height: `${det.bbox.h}%`,
                  }}
                >
                  <div
                    className={`absolute -top-4 left-0 text-[8px] font-mono font-bold px-1.5 py-0.2 rounded text-white shadow-sm flex items-center gap-1 ${
                      det.is_in_restricted_zone ? 'bg-red-500' : 'bg-green-600'
                    }`}
                  >
                    <span>{det.object_id}</span>
                    {settings.showConfidence && <span>• {typeof det.confidence === 'number' ? det.confidence.toFixed(1) : det.confidence}%</span>}
                    {det.is_in_restricted_zone && <span className="text-[7px]">🚨 ZONE</span>}
                  </div>
                </div>
              ))}

            {/* Mode & Stats Tag */}
            <div className="absolute bottom-1.5 left-2 text-[8px] font-mono text-emerald-300/90 bg-black/70 px-1.5 py-0.5 rounded pointer-events-none border border-emerald-500/20">
              YOLOv8 AI • ~8.0 FPS
            </div>
          </div>
        </div>
      )}

      {/* ── 2. REAL ONLINE CCTV & PHONE CAMERA TILES ── */}
      {onlineCameras.map((cam) => {
        const camZone = zones[cam.id];
        const hasZone = Boolean(camZone && camZone.coordinates && camZone.coordinates.length >= 3 && camZone.enabled);
        const camDets = detections.filter((d) => d.camera_id === cam.id && !d.video_id);
        const isSelected = cam.id === selectedCamId && !isCameraMode;
        const isUsb = cam.source_type === 'USB_PHONE';
        const isPhone = cam.source_type === 'PHONE';

        return (
          <div
            key={cam.id}
            onClick={() => onSelectCamera(cam.id)}
            className={`relative rounded-md border overflow-hidden transition-all duration-200 cursor-pointer flex flex-col bg-[#0b1222] ${
              isSelected
                ? 'border-[#1d6af5] ring-1 ring-[#1d6af5]/30'
                : 'border-[#1e2d4a] hover:border-[#253a5e]'
            }`}
            style={{ minHeight: totalActive <= 2 ? '250px' : '200px' }}
          >
            {/* Tile Header */}
            <div className="flex items-center justify-between px-3 py-2 bg-[#0a1020] border-b border-[#1e2d4a] z-10">
              <div className="flex items-center gap-2 min-w-0">
                {isUsb ? (
                  <Usb size={13} className="text-cyan-400 flex-shrink-0" />
                ) : isPhone ? (
                  <Smartphone size={13} className="text-purple-400 flex-shrink-0" />
                ) : (
                  <Video size={13} className="text-blue-400 flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-mono font-bold text-slate-200 truncate">{cam.name || cam.id}</span>
                    <span
                      className={`text-[9px] font-mono px-1.5 py-0.2 rounded font-semibold ${
                        isUsb
                          ? 'bg-cyan-950/80 border border-cyan-500/30 text-cyan-300'
                          : isPhone
                          ? 'bg-purple-950/80 border border-purple-500/30 text-purple-300'
                          : 'bg-blue-950/80 border border-blue-500/30 text-blue-300'
                      }`}
                    >
                      {isUsb ? 'USB PHONE' : isPhone ? 'PHONE / WIFI' : 'CCTV / RTSP'}
                    </span>
                  </div>
                  <p className="text-[10px] text-slate-400 truncate">{cam.location || cam.id}</p>
                </div>
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                <span className="flex items-center gap-1 bg-green-950/80 border border-green-500/30 px-1.5 py-0.5 rounded text-[8px] font-mono text-green-300 font-bold">
                  <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-[livePulse_1.5s_ease-in-out_infinite]" />
                  LIVE
                </span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onConfigureZone(cam.id, 'CAMERA');
                  }}
                  className={`p-1 transition-colors ${hasZone ? 'text-red-400' : 'text-slate-500 hover:text-slate-300'}`}
                  title="Configure Camera Zone"
                >
                  <ShieldAlert size={13} />
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectCamera(cam.id);
                  }}
                  className="p-1 text-slate-400 hover:text-blue-400 transition-colors"
                  title="Focus / Enlarge"
                >
                  <Maximize2 size={13} />
                </button>
              </div>
            </div>

            {/* Video Viewport Area */}
            <div className="relative flex-1 cctv-bg flex items-center justify-center overflow-hidden">
              {cam.stream_url ? (
                <img
                  src={`/api/cameras/${cam.id}/stream?conf=${(settings.aiThreshold || 50) / 100}`}
                  alt={cam.name}
                  className="w-full h-full object-cover z-0"
                  onError={(e) => {
                    (e.currentTarget as HTMLElement).style.display = 'none';
                  }}
                />
              ) : null}
              <div className="cctv-scanline pointer-events-none" />
              <div className="cctv-vignette pointer-events-none" />

              {/* Camera-Specific Polygon Zone Overlay */}
              {settings.showRestrictedZone && hasZone && (
                <div className="absolute inset-0 pointer-events-none z-10">
                  <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="w-full h-full">
                    <polygon
                      points={camZone.coordinates.map(([x, y]) => `${x},${y}`).join(' ')}
                      fill="rgba(239, 68, 68, 0.16)"
                      stroke="#ef4444"
                      strokeWidth="1.2"
                      strokeDasharray="3,2"
                    />
                  </svg>
                  <div className="absolute top-2 left-2 bg-red-500/90 text-white text-[8px] font-mono font-bold px-1.5 py-0.5 rounded shadow">
                    {camZone.name}
                  </div>
                </div>
              )}

              {/* Camera-Specific YOLO Bounding Boxes */}
              {settings.showBoundingBoxes &&
                camDets
                  .filter((d) => d?.bbox && typeof d.bbox.x === 'number' && typeof d.bbox.y === 'number' && typeof d.bbox.w === 'number' && typeof d.bbox.h === 'number')
                  .map((det) => (
                  <div
                    key={det.id}
                    className={`absolute border-2 pointer-events-none z-15 ${
                      det.is_in_restricted_zone ? 'border-red-500 bg-red-500/10' : 'border-green-500 bg-green-500/5'
                    }`}
                    style={{
                      left: `${det.bbox.x}%`,
                      top: `${det.bbox.y}%`,
                      width: `${det.bbox.w}%`,
                      height: `${det.bbox.h}%`,
                    }}
                  >
                    <div
                      className={`absolute -top-4 left-0 text-[8px] font-mono font-bold px-1.5 py-0.2 rounded text-white shadow-sm flex items-center gap-1 ${
                        det.is_in_restricted_zone ? 'bg-red-500' : 'bg-green-600'
                      }`}
                    >
                      <span>{det.object_id}</span>
                      {settings.showConfidence && <span>• {typeof det.confidence === 'number' ? det.confidence.toFixed(1) : det.confidence}%</span>}
                      {det.is_in_restricted_zone && <span className="text-[7px]">🚨 ZONE</span>}
                    </div>
                  </div>
                ))}

              {/* Resolution & Camera Tag */}
              <div className="absolute bottom-1.5 left-2 text-[8px] font-mono text-slate-300 bg-black/70 px-1.5 py-0.5 rounded pointer-events-none border border-white/10">
                {cam.resolution || '1080p'} • {cam.fps || 25.0} FPS
              </div>
            </div>
          </div>
        );
      })}

      {/* ── Empty State: 0 Active Cameras Connected ── */}
      {totalActive === 0 && (
        <div className="col-span-full py-12 text-center flex flex-col items-center justify-center">
          <div className="w-14 h-14 rounded-full bg-[#141e33] border border-[#1e2d4a] flex items-center justify-center mx-auto mb-3 text-slate-400">
            <WifiOff size={24} />
          </div>
          <h4 className="text-sm font-semibold text-slate-200">No Live Cameras Active</h4>
          <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto mb-5 leading-relaxed">
            The grid dynamically scales to match the exact number of active cameras. Connect a CCTV camera via RTSP, a phone camera over Wi-Fi, or your laptop webcam.
          </p>
          <div className="flex items-center gap-2.5 flex-wrap justify-center">
            <button
              onClick={onStartDeviceCamera}
              className="text-xs py-2 px-3.5 rounded font-medium bg-emerald-600 hover:bg-emerald-500 text-white transition-all flex items-center gap-1.5 cursor-pointer shadow-sm"
            >
              <Camera size={13} /> Connect Laptop Webcam
            </button>
            {onOpenAddCamera && (
              <button
                onClick={onOpenAddCamera}
                className="text-xs py-2 px-3.5 rounded font-medium bg-[#1d6af5] hover:bg-[#1655c7] text-white transition-all flex items-center gap-1.5 cursor-pointer shadow-sm"
              >
                <Plus size={13} /> + Add Camera Feed
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

