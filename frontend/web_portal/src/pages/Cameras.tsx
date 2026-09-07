import React, { useState, useEffect } from 'react';
import { CameraCard } from '../components/cameras/CameraCard';
import { WebcamCard } from '../components/cameras/WebcamCard';
import { ZoneEditorModal } from '../components/monitoring/ZoneEditorModal';
import { AddCameraModal } from '../components/cameras/AddCameraModal';
import { useCameras } from '../hooks/useCameras';
import {
  useStore,
  getActiveCamerasCount,
  getOnlineCamerasCount,
  getTotalCamerasCount,
  isWebcamStreamConnected,
} from '../store/useStore';
import { Camera as CameraIcon, WifiOff, Video, Smartphone, Plus, Radio, ShieldAlert } from 'lucide-react';
import * as api from '../services/api';
import type { CameraSourceType } from '../types';

export default function Cameras() {
  useCameras();
  const cameras            = useStore((s) => s.cameras);
  const isWebcamActive     = useStore((s) => s.isWebcamActive);
  const activeCameraStream = useStore((s) => s.activeCameraStream);
  const fetchZones         = useStore((s) => s.fetchZones);
  const fetchCameras       = useStore((s) => s.fetchCameras);
  const removeCamera       = useStore((s) => s.removeCamera);

  const [selected, setSelected] = useState<string | null>(null);
  const [editingCameraId, setEditingCameraId] = useState<string | null>(null);
  const [editingSourceType, setEditingSourceType] = useState<'CAMERA' | 'WEBCAM' | 'VIDEO'>('CAMERA');

  // Add Camera Modal State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [modalSourceType, setModalSourceType] = useState<CameraSourceType>('CCTV');

  // Test Notification
  const [testNotice, setTestNotice] = useState<{ id: string; success: boolean; message: string } | null>(null);

  useEffect(() => {
    fetchZones();
    fetchCameras();
  }, [fetchZones, fetchCameras]);

  const isWebcamConnected = isWebcamStreamConnected(isWebcamActive, activeCameraStream);
  const total             = getTotalCamerasCount(cameras, isWebcamActive, activeCameraStream);
  const online            = getOnlineCamerasCount(cameras, isWebcamActive, activeCameraStream);
  const offline           = cameras.filter((c) => c.status === 'OFFLINE' || c.status === 'MAINTENANCE' || c.status === 'ERROR').length;
  const aiRunning         = getActiveCamerasCount(cameras, isWebcamActive, activeCameraStream);

  const onlineCctv = cameras.filter((c) => c.status === 'ONLINE');
  const offlineCctv = cameras.filter((c) => c.status !== 'ONLINE');

  const editingCam = cameras.find((c) => c.id === editingCameraId);

  const handleOpenAddModal = (type: CameraSourceType) => {
    setModalSourceType(type);
    setIsAddModalOpen(true);
  };

  const handleDeleteCamera = async (camId: string, camName: string) => {
    if (window.confirm(`Are you sure you want to remove ${camName} (${camId}) from SHIELD?`)) {
      try {
        await api.deleteCamera(camId);
        removeCamera(camId);
      } catch (err: any) {
        console.error('Failed to delete camera:', err);
        alert('Failed to remove camera: ' + (err?.response?.data?.detail || err.message));
      }
    }
  };

  const handleTestCameraStream = async (cam: any) => {
    if (!cam.stream_url) return;
    try {
      const res = await api.testStream(cam.stream_url, cam.stream_type || 'RTSP');
      setTestNotice({
        id: cam.id,
        success: res.success,
        message: res.success
          ? `${cam.name}: Connected successfully (${res.resolution || '1080p'} @ ${res.fps || 25} FPS)`
          : `${cam.name}: Stream unreachable (${res.error || 'Connection timed out'})`,
      });
      setTimeout(() => setTestNotice(null), 6000);
    } catch (e: any) {
      setTestNotice({
        id: cam.id,
        success: false,
        message: `${cam.name}: Probe failed (${e.message})`,
      });
      setTimeout(() => setTestNotice(null), 6000);
    }
  };

  return (
    <div className="space-y-5">
      {/* Header with real connection actions */}
      <div className="flex items-center justify-between flex-wrap gap-3 pb-3 border-b border-[#272b37] light:border-[#d3d8e3]">
        <div>
          <h2 className="text-lg font-bold text-white light:text-slate-900 flex items-center gap-2">
            <CameraIcon size={20} className="text-[#22c55e] light:text-[#15803d]" />
            Surveillance Source Management
          </h2>
          <p className="text-xs text-[#9aa2b5] light:text-slate-500 font-mono">
            Connect and manage physical CCTV feeds, Phone Wi-Fi cameras, and Laptop webcams
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => handleOpenAddModal('CCTV')}
            className="px-3.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 light:bg-slate-900 light:hover:bg-slate-800 text-white text-xs font-semibold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
          >
            <Video size={13} />
            <span>+ Add CCTV Camera</span>
          </button>

          <button
            type="button"
            onClick={() => handleOpenAddModal('PHONE')}
            className="px-3.5 py-1.5 rounded-xl bg-amber-600/90 hover:bg-amber-600 text-white text-xs font-semibold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
          >
            <Smartphone size={13} />
            <span>+ Connect Phone / Wi-Fi</span>
          </button>

          <button
            type="button"
            onClick={() => handleOpenAddModal('WEBCAM')}
            className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer"
          >
            <CameraIcon size={13} />
            <span>+ Connect Laptop Camera</span>
          </button>
        </div>
      </div>

      {/* Dynamic Stats Summary Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Cameras',  value: total,     color: 'text-white light:text-slate-900' },
          { label: 'Online',         value: online,    color: 'text-[#22c55e] light:text-[#15803d]' },
          { label: 'Offline',        value: offline,   color: 'text-red-400 light:text-red-600' },
          { label: 'AI Active',      value: aiRunning, color: 'text-emerald-400 light:text-emerald-700' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-4 text-center shadow-card transition-colors">
            <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
            <div className="text-xs text-[#9aa2b5] light:text-slate-500 mt-1">{label}</div>
          </div>
        ))}
      </div>

      {/* Test Notice Toast */}
      {testNotice && (
        <div
          className={`p-3.5 rounded-xl border text-xs flex items-center justify-between gap-3 animate-fadeIn shadow-card ${
            testNotice.success
              ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300 light:text-emerald-800 light:bg-emerald-50'
              : 'bg-red-500/10 border-red-500/40 text-red-300 light:text-red-800 light:bg-red-50'
          }`}
        >
          <div className="flex items-center gap-2">
            <Radio size={14} className={testNotice.success ? 'text-emerald-400' : 'text-red-400'} />
            <span className="font-mono font-medium">{testNotice.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setTestNotice(null)}
            className="text-[#9aa2b5] light:text-slate-500 hover:text-white light:hover:text-slate-900 text-xs px-2 py-0.5 cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Local Device Camera Card (if active) */}
      {isWebcamActive && (
        <div className="space-y-2">
          <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-emerald-400 light:text-emerald-700 flex items-center gap-2">
            <CameraIcon size={13} />
            Browser Local Video Input
          </h3>
          <WebcamCard />
        </div>
      )}

      {/* Empty State when 0 total cameras exist */}
      {total === 0 && (
        <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-8 text-center space-y-6 shadow-card transition-colors">
          <div className="w-14 h-14 rounded-full bg-[#191c24] light:bg-slate-100 border border-[#272b37] light:border-slate-300 flex items-center justify-center mx-auto text-[#62697b] light:text-slate-400">
            <WifiOff size={26} />
          </div>

          <div className="space-y-1">
            <h3 className="text-base font-bold text-white light:text-slate-900">No cameras connected</h3>
            <p className="text-xs text-[#9aa2b5] light:text-slate-500 max-w-md mx-auto leading-relaxed">
              At startup, SHIELD starts with zero predefined cameras. Connect physical CCTV feeds, mobile phone cameras over Wi-Fi, or this computer's built-in webcam.
            </p>
          </div>

          {/* Quick Onboarding 3-Card Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-left max-w-3xl mx-auto pt-2">
            {/* 1. CCTV Card */}
            <div
              onClick={() => handleOpenAddModal('CCTV')}
              className="p-4 rounded-xl bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] hover:border-slate-500 light:hover:border-slate-400 transition-all cursor-pointer group"
            >
              <div className="w-9 h-9 rounded-lg bg-slate-800/80 light:bg-slate-200 border border-slate-700 light:border-slate-300 flex items-center justify-center text-white light:text-slate-900 mb-3 group-hover:scale-105 transition-transform">
                <Video size={18} />
              </div>
              <h4 className="text-sm font-semibold text-white light:text-slate-900 group-hover:text-emerald-400 light:group-hover:text-emerald-700 transition-colors">
                Add CCTV Camera
              </h4>
              <p className="text-[11px] text-[#9aa2b5] light:text-slate-500 mt-1 leading-relaxed">
                Connect physical IP/CCTV surveillance cameras via RTSP or ONVIF stream URLs.
              </p>
              <span className="inline-block mt-3 text-[11px] font-mono text-emerald-400 light:text-emerald-700 group-hover:underline font-semibold">
                + Connect CCTV →
              </span>
            </div>


            {/* 2. Phone Wi-Fi Card */}
            <div
              onClick={() => handleOpenAddModal('PHONE')}
              className="p-4 rounded-xl bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] hover:border-amber-500/50 light:hover:border-amber-500/50 transition-all cursor-pointer group"
            >
              <div className="w-9 h-9 rounded-lg bg-amber-500/15 light:bg-amber-100 border border-amber-500/30 light:border-amber-300 flex items-center justify-center text-amber-400 light:text-amber-700 mb-3 group-hover:scale-105 transition-transform">
                <Smartphone size={18} />
              </div>
              <h4 className="text-sm font-semibold text-white light:text-slate-900 group-hover:text-amber-400 light:group-hover:text-amber-700 transition-colors">
                Phone / Wi-Fi Camera
              </h4>
              <p className="text-[11px] text-[#9aa2b5] light:text-slate-500 mt-1 leading-relaxed">
                Turn any Android/iPhone into an AI security camera via local Wi-Fi IP webcam stream.
              </p>
              <span className="inline-block mt-3 text-[11px] font-mono text-amber-400 light:text-amber-700 group-hover:underline font-semibold">
                + Connect Phone →
              </span>
            </div>

            {/* 3. Laptop Webcam Card */}
            <div
              onClick={() => handleOpenAddModal('WEBCAM')}
              className="p-4 rounded-xl bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] hover:border-emerald-500/50 light:hover:border-emerald-500/50 transition-all cursor-pointer group"
            >
              <div className="w-9 h-9 rounded-lg bg-emerald-500/15 light:bg-emerald-100 border border-emerald-500/30 light:border-emerald-300 flex items-center justify-center text-emerald-400 light:text-[#15803d] mb-3 group-hover:scale-105 transition-transform">
                <CameraIcon size={18} />
              </div>
              <h4 className="text-sm font-semibold text-white light:text-slate-900 group-hover:text-emerald-400 light:group-hover:text-emerald-700 transition-colors">
                Laptop Webcam
              </h4>
              <p className="text-[11px] text-[#9aa2b5] light:text-slate-500 mt-1 leading-relaxed">
                Instant browser MediaStream input with full YOLOv8 detection and spatial zones.
              </p>
              <span className="inline-block mt-3 text-[11px] font-mono text-emerald-400 light:text-[#15803d] group-hover:underline font-semibold">
                + Connect Webcam →
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Online Cameras Section */}
      {onlineCctv.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <CameraIcon size={13} className="text-emerald-400" />
              Active Online Surveillance Sources ({onlineCctv.length})
            </h3>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {onlineCctv.map((cam) => (
              <CameraCard
                key={cam.id}
                camera={cam}
                isSelected={cam.id === selected}
                onClick={() => setSelected(cam.id === selected ? null : cam.id)}
                onConfigureZone={() => {
                  setEditingCameraId(cam.id);
                  setEditingSourceType('CAMERA');
                }}
                onDelete={() => handleDeleteCamera(cam.id, cam.name)}
                onTest={() => handleTestCameraStream(cam)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Offline / Configured Cameras Section */}
      {offlineCctv.length > 0 && (
        <div className="space-y-3 pt-3 border-t border-[#1e2d4a]/70">
          <h3 className="text-xs font-mono font-semibold uppercase tracking-wider text-slate-500 flex items-center gap-2">
            <WifiOff size={13} className="text-red-400" />
            Configured Offline / Error Sources ({offlineCctv.length})
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {offlineCctv.map((cam) => (
              <CameraCard
                key={cam.id}
                camera={cam}
                isSelected={cam.id === selected}
                onClick={() => setSelected(cam.id === selected ? null : cam.id)}
                onConfigureZone={() => {
                  setEditingCameraId(cam.id);
                  setEditingSourceType('CAMERA');
                }}
                onDelete={() => handleDeleteCamera(cam.id, cam.name)}
                onTest={() => handleTestCameraStream(cam)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Add Camera Modal */}
      <AddCameraModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        initialSourceType={modalSourceType}
      />

      {/* Camera Specific Zone Modal */}
      {editingCameraId && (
        <ZoneEditorModal
          sourceId={editingCameraId}
          sourceType={editingSourceType}
          sourceLabel={editingCam?.location ? `${editingCameraId} (${editingCam.location})` : editingCameraId}
          isOpen={true}
          onClose={() => setEditingCameraId(null)}
        />
      )}
    </div>
  );
}
