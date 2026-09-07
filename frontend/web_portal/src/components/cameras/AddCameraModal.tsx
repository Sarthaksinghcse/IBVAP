import React, { useState, useEffect } from 'react';
import { X, Camera, Smartphone, Video, Loader2, CheckCircle2, AlertCircle, RefreshCw, Radio } from 'lucide-react';
import { useStore } from '../../store/useStore';
import * as api from '../../services/api';
import type { CameraSourceType } from '../../types';

interface AddCameraModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialSourceType?: CameraSourceType;
}

export function AddCameraModal({ isOpen, onClose, initialSourceType = 'CCTV' }: AddCameraModalProps) {
  const [activeTab, setActiveTab] = useState<CameraSourceType>(initialSourceType);

  // Form Fields
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');
  const [streamUrl, setStreamUrl] = useState('');
  const [streamType, setStreamType] = useState('RTSP');
  const [selectedDeviceId, setSelectedDeviceId] = useState('');

  // Stream Testing State
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<api.StreamTestResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Store actions
  const addCamera = useStore((s) => s.addCamera);
  const availableCameraDevices = useStore((s) => s.availableCameraDevices);
  const enumerateCameraDevices = useStore((s) => s.enumerateCameraDevices);
  const startDeviceCamera = useStore((s) => s.startDeviceCamera);
  const setCameraMode = useStore((s) => s.setCameraMode);

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialSourceType);
      setErrorMsg(null);
      setTestResult(null);
      if (initialSourceType === 'CCTV') {
        setName('North Gate CCTV');
        setLocation('Main Perimeter Gate');
        setStreamUrl('');
        setStreamType('RTSP');
      } else if (initialSourceType === 'PHONE') {
        setName('Security Phone 01');
        setLocation('Mobile Checkpoint Alpha');
        setStreamUrl('');
        setStreamType('HTTP');
      } else {
        setName('Laptop Webcam');
        setLocation('Operator Console');
      }
      enumerateCameraDevices();
    }
  }, [isOpen, initialSourceType, enumerateCameraDevices]);

  if (!isOpen) return null;

  const handleTabSwitch = (tab: CameraSourceType) => {
    setActiveTab(tab);
    setErrorMsg(null);
    setTestResult(null);
    if (tab === 'CCTV') {
      setName('North Gate CCTV');
      setLocation('Main Perimeter Gate');
      setStreamUrl('');
      setStreamType('RTSP');
    } else if (tab === 'PHONE') {
      setName('Security Phone 01');
      setLocation('Mobile Checkpoint Alpha');
      setStreamUrl('');
      setStreamType('HTTP');
    } else {
      setName('Laptop Webcam');
      setLocation('Operator Console');
    }
  };

  const handleTestStream = async () => {
    if (!streamUrl.trim()) {
      setErrorMsg('Please enter a stream URL to test.');
      return;
    }
    setIsTesting(true);
    setTestResult(null);
    setErrorMsg(null);
    try {
      const res = await api.testStream(streamUrl.trim(), streamType);
      setTestResult(res);
      if (!res.success) {
        setErrorMsg(res.error || 'Failed to reach camera stream. Check network and URL.');
      }
    } catch (err: any) {
      setTestResult({
        success: false,
        status: 'OFFLINE',
        error: err?.response?.data?.detail || 'Network error while attempting to probe stream.',
      });
      setErrorMsg('Network error while attempting to probe stream.');
    } finally {
      setIsTesting(false);
    }
  };

  const handleSaveCamera = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setErrorMsg('Please provide a camera name.');
      return;
    }

    // Laptop Webcam flow
    if (activeTab === 'WEBCAM') {
      setIsSubmitting(true);
      try {
        setCameraMode(true);
        await startDeviceCamera(selectedDeviceId || undefined);
        onClose();
      } catch (err: any) {
        setErrorMsg('Failed to start device camera: ' + err.message);
      } finally {
        setIsSubmitting(false);
      }
      return;
    }

    // Network CCTV / Phone flow
    if (!streamUrl.trim()) {
      setErrorMsg('Stream URL is required for network cameras.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const newCam = await api.createCamera({
        name: name.trim(),
        location: location.trim() || 'Surveillance Area',
        source_type: activeTab,
        stream_url: streamUrl.trim(),
        stream_type: streamType,
        status: testResult?.success ? 'ONLINE' : 'OFFLINE',
        resolution: testResult?.resolution || '1920x1080',
        fps: testResult?.fps || 25.0,
      });

      addCamera(newCam);
      onClose();
    } catch (err: any) {
      setErrorMsg(err?.response?.data?.detail || 'Failed to register camera in system.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
      <div className="bg-[#0e1626] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded-xl shadow-2xl w-full max-w-xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e2d4a] light:border-[#d1d5db] bg-[#141e33]/50 light:bg-slate-50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#1d6af5]/15 border border-[#1d6af5]/30 flex items-center justify-center text-[#1d6af5]">
              <Video size={18} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white light:text-slate-900">Add Video Surveillance Source</h3>
              <p className="text-[11px] text-slate-400 light:text-slate-500 font-mono">Connect real CCTV, Phone Wi-Fi camera, or Laptop webcam</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-md bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 flex items-center justify-center transition-all cursor-pointer"
          >
            <X size={15} />
          </button>
        </div>

        {/* Source Type Selector Tabs */}
        <div className="grid grid-cols-3 gap-1 p-2 bg-[#0a0f1d] light:bg-slate-100 border-b border-[#1e2d4a] light:border-[#d1d5db]">
          <button
            type="button"
            onClick={() => handleTabSwitch('CCTV')}
            className={`py-2.5 px-3 rounded-lg text-xs font-medium flex items-center justify-center gap-2 transition-all cursor-pointer ${
              activeTab === 'CCTV'
                ? 'bg-[#1d6af5] text-white shadow-md font-semibold'
                : 'text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 hover:bg-[#141e33] light:hover:bg-white'
            }`}
          >
            <Video size={14} />
            <span>CCTV Camera</span>
          </button>
          <button
            type="button"
            onClick={() => handleTabSwitch('PHONE')}
            className={`py-2.5 px-3 rounded-lg text-xs font-medium flex items-center justify-center gap-2 transition-all cursor-pointer ${
              activeTab === 'PHONE'
                ? 'bg-amber-600 text-white shadow-md font-semibold'
                : 'text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 hover:bg-[#141e33] light:hover:bg-white'
            }`}
          >
            <Smartphone size={14} />
            <span>Phone / Wi-Fi</span>
          </button>
          <button
            type="button"
            onClick={() => handleTabSwitch('WEBCAM')}
            className={`py-2.5 px-3 rounded-lg text-xs font-medium flex items-center justify-center gap-2 transition-all cursor-pointer ${
              activeTab === 'WEBCAM'
                ? 'bg-emerald-600 text-white shadow-md font-semibold'
                : 'text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 hover:bg-[#141e33] light:hover:bg-white'
            }`}
          >
            <Camera size={14} />
            <span>Laptop Webcam</span>
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSaveCamera} className="p-5 overflow-y-auto space-y-4">
          {errorMsg && (
            <div className="p-3 rounded-lg bg-red-500/10 light:bg-red-50 border border-red-500/30 light:border-red-200 text-red-300 light:text-red-700 text-xs flex items-start gap-2.5">
              <AlertCircle size={15} className="text-red-400 light:text-red-600 shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <p className="font-semibold">Connection Notice</p>
                <p className="text-[11px] leading-relaxed text-red-200/90 light:text-red-700">{errorMsg}</p>
              </div>
            </div>
          )}

          {/* Camera Name */}
          <div>
            <label className="block text-xs font-medium text-slate-300 light:text-slate-700 mb-1.5">
              Camera / Source Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={activeTab === 'CCTV' ? 'e.g. North Gate CCTV' : activeTab === 'PHONE' ? 'e.g. Security Phone 01' : 'e.g. Laptop Webcam'}
              className="w-full bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded-lg px-3 py-2 text-xs text-white light:text-slate-900 placeholder-slate-500 focus:outline-none focus:border-[#1d6af5] transition-all font-mono"
            />
          </div>

          {/* Location */}
          <div>
            <label className="block text-xs font-medium text-slate-300 light:text-slate-700 mb-1.5">
              Physical Location / Sector
            </label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Sector Alpha — Gate A"
              className="w-full bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded-lg px-3 py-2 text-xs text-white light:text-slate-900 placeholder-slate-500 focus:outline-none focus:border-[#1d6af5] transition-all"
            />
          </div>

          {/* Stream URL (for CCTV and Phone) */}
          {(activeTab === 'CCTV' || activeTab === 'PHONE') && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-medium text-slate-300 light:text-slate-700">
                  {activeTab === 'CCTV' ? 'RTSP / Stream URL' : 'Phone IP Webcam Stream URL'} <span className="text-red-400">*</span>
                </label>
                <span className="text-[10px] font-mono text-slate-500 light:text-slate-500">
                  {activeTab === 'CCTV' ? 'rtsp://user:pass@ip:554/stream' : 'http://PHONE_IP:8080/video'}
                </span>
              </div>
              <input
                type="text"
                required
                value={streamUrl}
                onChange={(e) => {
                  setStreamUrl(e.target.value);
                  setTestResult(null);
                }}
                placeholder={activeTab === 'CCTV' ? 'rtsp://admin:password@192.168.1.100:554/live/ch0' : 'http://192.168.1.45:8080/video'}
                className="w-full bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded-lg px-3 py-2 text-xs text-white light:text-slate-900 placeholder-slate-500 focus:outline-none focus:border-[#1d6af5] transition-all font-mono"
              />

              {/* Protocol Selector & Test Stream Button */}
              <div className="flex items-center justify-between mt-2.5 gap-2 flex-wrap">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] text-slate-400 light:text-slate-600">Protocol:</span>
                  <select
                    value={streamType}
                    onChange={(e) => setStreamType(e.target.value)}
                    className="bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded px-2 py-1 text-[11px] text-slate-300 light:text-slate-900 font-mono focus:outline-none focus:border-[#1d6af5]"
                  >
                    <option value="RTSP">RTSP (Real Time Streaming Protocol)</option>
                    <option value="HTTP">HTTP / MJPEG Stream</option>
                    <option value="ONVIF">ONVIF Network Stream</option>
                  </select>
                </div>

                <button
                  type="button"
                  onClick={handleTestStream}
                  disabled={isTesting || !streamUrl.trim()}
                  className="px-3 py-1.5 rounded-lg bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 border border-[#1e2d4a] light:border-slate-300 hover:border-[#1d6af5]/50 text-xs font-mono text-slate-300 light:text-slate-800 hover:text-white light:hover:text-slate-900 transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer shadow-sm"
                >
                  {isTesting ? (
                    <>
                      <Loader2 size={12} className="animate-spin text-[#1d6af5]" />
                      <span>Probing Stream...</span>
                    </>
                  ) : (
                    <>
                      <Radio size={12} className="text-emerald-400 light:text-[#15803d]" />
                      <span>Test Connection</span>
                    </>
                  )}
                </button>
              </div>

              {/* Test Result Card */}
              {testResult && (
                <div
                  className={`mt-3 p-3 rounded-lg border text-xs flex items-start gap-2.5 animate-fadeIn ${
                    testResult.success
                      ? 'bg-emerald-500/10 light:bg-emerald-50 border-emerald-500/30 light:border-emerald-200 text-emerald-300 light:text-emerald-800'
                      : 'bg-red-500/10 light:bg-red-50 border-red-500/30 light:border-red-200 text-red-300 light:text-red-800'
                  }`}
                >
                  {testResult.success ? (
                    <>
                      <CheckCircle2 size={16} className="text-emerald-400 light:text-[#15803d] shrink-0 mt-0.5" />
                      <div>
                        <p className="font-semibold text-emerald-200 light:text-emerald-900">Stream Connection Successful!</p>
                        <p className="text-[11px] font-mono text-emerald-300/90 light:text-emerald-700 mt-0.5">
                          Status: ONLINE • Resolution: {testResult.resolution || '1920x1080'} • FPS: {testResult.fps || 25}
                        </p>
                      </div>
                    </>
                  ) : (
                    <>
                      <AlertCircle size={16} className="text-red-400 light:text-red-600 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-semibold text-red-200 light:text-red-900">Stream Unreachable</p>
                        <p className="text-[11px] font-mono text-red-300/90 light:text-red-700 mt-0.5">
                          {testResult.error || 'Could not connect to stream URL.'}
                        </p>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Laptop Webcam Device Selection */}
          {activeTab === 'WEBCAM' && (
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-slate-300 light:text-slate-700 mb-1.5">
                  Select Video Input Device
                </label>
                {availableCameraDevices.length > 0 ? (
                  <select
                    value={selectedDeviceId}
                    onChange={(e) => setSelectedDeviceId(e.target.value)}
                    className="w-full bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded-lg px-3 py-2 text-xs text-slate-200 light:text-slate-900 focus:outline-none focus:border-[#1d6af5] font-mono"
                  >
                    <option value="">Default System Webcam</option>
                    {availableCameraDevices.map((dev, idx) => (
                      <option key={dev.deviceId || idx} value={dev.deviceId}>
                        {dev.label || `Camera ${idx + 1}`}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="p-3 rounded-lg bg-[#141e33] light:bg-slate-100 border border-[#1e2d4a] light:border-slate-300 text-xs text-slate-400 light:text-slate-600">
                    Browser webcam will be requested via HTML5 MediaStream API.
                  </div>
                )}
              </div>

              <div className="p-3 rounded-lg bg-emerald-500/10 light:bg-emerald-50 border border-emerald-500/20 light:border-emerald-200 text-xs text-emerald-300 light:text-emerald-800 flex items-start gap-2.5">
                <Camera size={16} className="text-emerald-400 light:text-[#15803d] shrink-0 mt-0.5" />
                <p className="text-[11px] leading-relaxed">
                  Real-time YOLOv8 frame inference will run automatically on the browser webcam stream with isolated tracking and spatial zone analysis.
                </p>
              </div>
            </div>
          )}

          {/* Footer Controls */}
          <div className="flex items-center justify-end gap-2.5 pt-4 border-t border-[#1e2d4a] light:border-[#d1d5db]">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 text-xs font-medium text-slate-300 light:text-slate-800 hover:text-white light:hover:text-slate-900 transition-all cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 rounded-lg bg-[#1d6af5] hover:bg-[#1655c7] text-white text-xs font-medium transition-all shadow-md flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>Connecting...</span>
                </>
              ) : (
                <span>
                  {activeTab === 'WEBCAM'
                    ? 'Connect Local Webcam'
                    : activeTab === 'PHONE'
                    ? 'Connect Phone Camera'
                    : 'Save & Connect CCTV'}
                </span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>

  );
}
