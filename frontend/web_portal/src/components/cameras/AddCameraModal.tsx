import React, { useState, useEffect } from 'react';
import {
  X,
  Camera,
  Smartphone,
  Video,
  Loader2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Radio,
  Usb,
  HelpCircle,
  ExternalLink,
  ChevronDown,
  ShieldCheck,
} from 'lucide-react';
import { useStore } from '../../store/useStore';
import * as api from '../../services/api';
import type { CameraSourceType, USBDetectResponse, USBTestResponse } from '../../types';

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

  // USB Phone Fields & States
  const [usbAppType, setUsbAppType] = useState<'IP_WEBCAM' | 'DROIDCAM' | 'CUSTOM'>('IP_WEBCAM');
  const [phonePort, setPhonePort] = useState<number>(8080);
  const [localPort, setLocalPort] = useState<number>(8090);
  const [streamPath, setStreamPath] = useState<string>('/video');
  const [isDetectingUsb, setIsDetectingUsb] = useState(false);
  const [isFindingPort, setIsFindingPort] = useState(false);
  const [usbDetectData, setUsbDetectData] = useState<USBDetectResponse | null>(null);
  const [isUsbTesting, setIsUsbTesting] = useState(false);
  const [usbTestResult, setUsbTestResult] = useState<USBTestResponse | null>(null);
  const [showUsbInstructions, setShowUsbInstructions] = useState(false);

  // General Stream Testing State
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

  const handleDetectUsbDevices = async () => {
    setIsDetectingUsb(true);
    setErrorMsg(null);
    try {
      const res = await api.detectUsbPhone();
      setUsbDetectData(res);
      if (res.devices && res.devices.length > 0) {
        const authorizedDev = res.devices.find((d) => d.authorized) || res.devices[0];
        if (authorizedDev.model && authorizedDev.model !== 'Unknown Android') {
          setName(`${authorizedDev.model} (USB)`);
        }
      }
    } catch (err: any) {
      console.error('[USB] Detect error:', err);
    } finally {
      setIsDetectingUsb(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialSourceType);
      setErrorMsg(null);
      setTestResult(null);
      setUsbTestResult(null);

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
      } else if (initialSourceType === 'USB_PHONE') {
        setName('Android Phone (USB Cable)');
        setLocation('USB Mobile Surveillance Station');
        handleDetectUsbDevices();
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
    setUsbTestResult(null);

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
    } else if (tab === 'USB_PHONE') {
      setName('Android Phone (USB Cable)');
      setLocation('USB Mobile Surveillance Station');
      setUsbAppType('IP_WEBCAM');
      setPhonePort(8080);
      setLocalPort(8090);
      setStreamPath('/video');
      handleDetectUsbDevices();
    } else {
      setName('Laptop Webcam');
      setLocation('Operator Console');
    }
  };

  const handleFindAvailablePort = async () => {
    setIsFindingPort(true);
    setErrorMsg(null);
    try {
      const res = await api.findAvailableUsbPort(Number(localPort) || 8090);
      if (res && res.available_port) {
        setLocalPort(res.available_port);
      }
    } catch (err: any) {
      console.warn('[USB] Could not query port endpoint, falling back to 8090');
    } finally {
      setIsFindingPort(false);
    }
  };

  const handlePresetSelect = (preset: 'IP_WEBCAM' | 'DROIDCAM' | 'CUSTOM') => {
    setUsbAppType(preset);
    setUsbTestResult(null);
    if (preset === 'IP_WEBCAM') {
      setPhonePort(8080);
      setLocalPort(8090);
      setStreamPath('/video');
    } else if (preset === 'DROIDCAM') {
      setPhonePort(4747);
      setLocalPort(8090);
      setStreamPath('/video');
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

  const handleTestUsbStream = async () => {
    setIsUsbTesting(true);
    setUsbTestResult(null);
    setErrorMsg(null);
    try {
      const res = await api.testUsbPhoneStream({
        phone_port: Number(phonePort),
        local_port: Number(localPort),
        stream_path: streamPath,
        device_serial: usbDetectData?.devices?.[0]?.serial,
        auto_find_port: true,
      });
      setUsbTestResult(res);
      // If server bound to an alternate free port (e.g. 8091), reflect it immediately in UI state
      if (res.local_port && res.local_port !== localPort) {
        setLocalPort(res.local_port);
      }
      if (!res.success) {
        setErrorMsg(res.message || 'Stream test failed over USB.');
      }
    } catch (err: any) {
      setUsbTestResult({
        success: false,
        message: err?.response?.data?.detail || 'Error communicating with phone over USB cable.',
        adb_forwarded: false,
      });
      setErrorMsg(err?.response?.data?.detail || 'Error testing stream over USB cable.');
    } finally {
      setIsUsbTesting(false);
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

    // USB Phone flow
    if (activeTab === 'USB_PHONE') {
      setIsSubmitting(true);
      setErrorMsg(null);
      try {
        const newCam = await api.connectUsbPhone({
          name: name.trim(),
          location: location.trim() || 'USB Mobile Surveillance',
          device_serial: usbDetectData?.devices?.[0]?.serial,
          phone_port: Number(phonePort),
          local_port: Number(localPort),
          stream_path: streamPath,
          app_type: usbAppType,
        });
        addCamera(newCam);
        onClose();
      } catch (err: any) {
        setErrorMsg(err?.response?.data?.detail || 'Failed to connect USB phone camera.');
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

  const detectedAuthorized = usbDetectData?.devices?.some((d) => d.authorized);
  const detectedUnauthorized = usbDetectData?.devices?.some((d) => !d.authorized);
  const pnpDetected = usbDetectData?.pnp_hardware_detected && usbDetectData.pnp_hardware_detected.length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
      <div className="bg-[#0e1626] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded-xl shadow-2xl w-full max-w-xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1e2d4a] light:border-[#d1d5db] bg-[#141e33]/50 light:bg-slate-50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#1d6af5]/15 border border-[#1d6af5]/30 flex items-center justify-center text-[#1d6af5]">
              {activeTab === 'USB_PHONE' ? <Usb size={18} /> : <Video size={18} />}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white light:text-slate-900">Add Video Surveillance Source</h3>
              <p className="text-[11px] text-slate-400 light:text-slate-500 font-mono">
                Connect physical CCTV, USB Data Cable phone, Wi-Fi phone, or Laptop webcam
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded-md bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 flex items-center justify-center transition-all cursor-pointer"
          >
            <X size={15} />
          </button>
        </div>

        {/* Source Type Selector Tabs (4 Tabs) */}
        <div className="grid grid-cols-4 gap-1 p-2 bg-[#0a0f1d] light:bg-slate-100 border-b border-[#1e2d4a] light:border-[#d1d5db]">
          <button
            type="button"
            onClick={() => handleTabSwitch('CCTV')}
            className={`py-2 px-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
              activeTab === 'CCTV'
                ? 'bg-[#1d6af5] text-white shadow-md font-semibold'
                : 'text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 hover:bg-[#141e33] light:hover:bg-white'
            }`}
          >
            <Video size={13} />
            <span>CCTV</span>
          </button>
          <button
            type="button"
            onClick={() => handleTabSwitch('USB_PHONE')}
            className={`py-2 px-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
              activeTab === 'USB_PHONE'
                ? 'bg-cyan-600 text-white shadow-md font-semibold ring-1 ring-cyan-400/50'
                : 'text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 hover:bg-[#141e33] light:hover:bg-white'
            }`}
          >
            <Usb size={13} />
            <span>USB Phone</span>
          </button>
          <button
            type="button"
            onClick={() => handleTabSwitch('PHONE')}
            className={`py-2 px-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
              activeTab === 'PHONE'
                ? 'bg-amber-600 text-white shadow-md font-semibold'
                : 'text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 hover:bg-[#141e33] light:hover:bg-white'
            }`}
          >
            <Smartphone size={13} />
            <span>Wi-Fi Phone</span>
          </button>
          <button
            type="button"
            onClick={() => handleTabSwitch('WEBCAM')}
            className={`py-2 px-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
              activeTab === 'WEBCAM'
                ? 'bg-emerald-600 text-white shadow-md font-semibold'
                : 'text-slate-400 light:text-slate-600 hover:text-slate-200 light:hover:text-slate-900 hover:bg-[#141e33] light:hover:bg-white'
            }`}
          >
            <Camera size={13} />
            <span>Webcam</span>
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
              placeholder={
                activeTab === 'USB_PHONE'
                  ? 'e.g. Android Phone (USB)'
                  : activeTab === 'CCTV'
                  ? 'e.g. North Gate CCTV'
                  : activeTab === 'PHONE'
                  ? 'e.g. Security Phone 01'
                  : 'e.g. Laptop Webcam'
              }
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
              placeholder={activeTab === 'USB_PHONE' ? 'e.g. Mobile USB Station' : 'e.g. Sector Alpha — Gate A'}
              className="w-full bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded-lg px-3 py-2 text-xs text-white light:text-slate-900 placeholder-slate-500 focus:outline-none focus:border-[#1d6af5] transition-all"
            />
          </div>

          {/* ═══════════════════════════════════════════════════════════
              TAB: USB PHONE (Physical Data Cable & ADB Port Forwarding)
             ═══════════════════════════════════════════════════════════ */}
          {activeTab === 'USB_PHONE' && (
            <div className="space-y-4 pt-1">
              {/* USB Device Hardware Status Card */}
              <div className="p-3.5 rounded-xl bg-[#090d16] light:bg-slate-50 border border-[#1e2d4a] light:border-slate-200">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Usb size={15} className="text-cyan-400" />
                    <span className="text-xs font-semibold text-slate-200 light:text-slate-800">
                      Physical USB Device Status
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={handleDetectUsbDevices}
                    disabled={isDetectingUsb}
                    className="px-2 py-1 rounded bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-slate-300 hover:border-cyan-500/50 text-[11px] font-mono text-cyan-400 light:text-cyan-600 flex items-center gap-1.5 transition-all cursor-pointer shadow-xs disabled:opacity-50"
                  >
                    <RefreshCw size={11} className={isDetectingUsb ? 'animate-spin' : ''} />
                    <span>Scan USB</span>
                  </button>
                </div>

                {/* State display */}
                {isDetectingUsb ? (
                  <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
                    <Loader2 size={13} className="animate-spin text-cyan-400" />
                    <span>Querying ADB socket and physical USB bus...</span>
                  </div>
                ) : detectedAuthorized ? (
                  <div className="space-y-1.5">
                    {usbDetectData?.devices.map((dev) => (
                      <div
                        key={dev.serial}
                        className="flex items-center justify-between p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono"
                      >
                        <div className="flex items-center gap-2">
                          <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                          <div>
                            <span className="font-bold text-white">{dev.model}</span>
                            <span className="text-[10px] text-emerald-400/80 ml-2">SN: {dev.serial}</span>
                          </div>
                        </div>
                        <span className="text-[10px] bg-emerald-950 px-2 py-0.5 rounded text-emerald-300 font-semibold uppercase">
                          Authorized Over USB
                        </span>
                      </div>
                    ))}
                  </div>
                ) : detectedUnauthorized ? (
                  <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2">
                    <AlertCircle size={15} className="text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold text-white">Device Connected — Authorization Required</p>
                      <p className="text-[11px] text-amber-200/90 mt-0.5">
                        Please unlock your phone screen and tap <strong>'Always allow from this computer'</strong> on
                        the USB Debugging prompt, then click <strong>Scan USB</strong>.
                      </p>
                    </div>
                  </div>
                ) : pnpDetected ? (
                  <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-start gap-2">
                    <AlertCircle size={15} className="text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold text-white">
                        Physical Cable Detected: {usbDetectData?.pnp_hardware_detected[0]?.name}
                      </p>
                      <p className="text-[11px] text-amber-200/90 mt-0.5">
                        The phone is physically plugged in, but <strong>USB Debugging</strong> is currently turned off or
                        unauthorized. Follow the 4-step guide below to activate it.
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="p-2.5 rounded-lg bg-[#141e33] light:bg-slate-100 border border-[#1e2d4a] light:border-slate-200 text-slate-300 light:text-slate-700 text-xs flex items-start gap-2">
                    <AlertCircle size={14} className="text-slate-400 shrink-0 mt-0.5" />
                    <p className="text-[11px] leading-relaxed">
                      Plug your Android phone into this computer using a <strong>USB Data Cable</strong> (not a
                      charge-only cable). Turn on <strong>USB Debugging</strong> in phone Developer Options.
                    </p>
                  </div>
                )}

                {/* Collapsible Connection Guide */}
                <div className="mt-2 pt-2 border-t border-[#1e2d4a]/50">
                  <button
                    type="button"
                    onClick={() => setShowUsbInstructions(!showUsbInstructions)}
                    className="text-[11px] font-mono text-cyan-400 hover:text-cyan-300 flex items-center gap-1 cursor-pointer"
                  >
                    <HelpCircle size={12} />
                    <span>{showUsbInstructions ? 'Hide setup instructions' : 'How to connect over USB cable (4 steps)'}</span>
                    <ChevronDown size={12} className={`transition-transform ${showUsbInstructions ? 'rotate-180' : ''}`} />
                  </button>

                  {showUsbInstructions && (
                    <ol className="mt-2 space-y-1.5 text-[11px] text-slate-300 light:text-slate-600 bg-[#0a0f1d] p-3 rounded-lg border border-[#1e2d4a] font-sans list-decimal list-inside leading-relaxed">
                      <li>
                        <strong>Use a USB Data Cable</strong>: Connect phone to PC. On the phone, set USB mode to{' '}
                        <em>File Transfer (MTP)</em>.
                      </li>
                      <li>
                        <strong>Enable Developer Options</strong>: Phone Settings → <em>About phone</em> → Tap{' '}
                        <em>Build Number</em> 7 times.
                      </li>
                      <li>
                        <strong>Enable USB Debugging</strong>: Settings → <em>Developer options</em> → Toggle{' '}
                        <em>USB Debugging</em> ON.
                      </li>
                      <li>
                        <strong>Allow Connection</strong>: On phone screen prompt, check{' '}
                        <em>'Always allow from this computer'</em> and tap OK.
                      </li>
                    </ol>
                  )}
                </div>
              </div>

              {/* Streaming App Preset Selection */}
              <div>
                <label className="block text-xs font-medium text-slate-300 light:text-slate-700 mb-1.5">
                  Phone Streaming App Preset
                </label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => handlePresetSelect('IP_WEBCAM')}
                    className={`p-2 rounded-lg text-left border transition-all cursor-pointer ${
                      usbAppType === 'IP_WEBCAM'
                        ? 'bg-cyan-950/40 border-cyan-500/60 ring-1 ring-cyan-500/30'
                        : 'bg-[#141e33] light:bg-white border-[#1e2d4a] light:border-slate-200 opacity-70 hover:opacity-100'
                    }`}
                  >
                    <div className="text-xs font-semibold text-white light:text-slate-900">IP Webcam</div>
                    <div className="text-[10px] font-mono text-cyan-400">Port :8080 • /video</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => handlePresetSelect('DROIDCAM')}
                    className={`p-2 rounded-lg text-left border transition-all cursor-pointer ${
                      usbAppType === 'DROIDCAM'
                        ? 'bg-cyan-950/40 border-cyan-500/60 ring-1 ring-cyan-500/30'
                        : 'bg-[#141e33] light:bg-white border-[#1e2d4a] light:border-slate-200 opacity-70 hover:opacity-100'
                    }`}
                  >
                    <div className="text-xs font-semibold text-white light:text-slate-900">DroidCam</div>
                    <div className="text-[10px] font-mono text-purple-400">Port :4747 • /video</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => handlePresetSelect('CUSTOM')}
                    className={`p-2 rounded-lg text-left border transition-all cursor-pointer ${
                      usbAppType === 'CUSTOM'
                        ? 'bg-cyan-950/40 border-cyan-500/60 ring-1 ring-cyan-500/30'
                        : 'bg-[#141e33] light:bg-white border-[#1e2d4a] light:border-slate-200 opacity-70 hover:opacity-100'
                    }`}
                  >
                    <div className="text-xs font-semibold text-white light:text-slate-900">Custom Stream</div>
                    <div className="text-[10px] font-mono text-slate-400">Manual Port/Path</div>
                  </button>
                </div>
              </div>

              {/* Port & Stream Path Fields */}
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] font-medium text-slate-300 light:text-slate-700">
                        Phone App Port
                      </label>
                      <span className="text-[9px] font-mono text-cyan-400 bg-cyan-950/60 px-1 rounded">Phone</span>
                    </div>
                    <input
                      type="number"
                      value={phonePort}
                      onChange={(e) => setPhonePort(Number(e.target.value))}
                      className="w-full bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded px-2.5 py-1.5 text-xs text-white light:text-slate-900 font-mono focus:outline-none focus:border-cyan-500 transition-colors"
                      placeholder="8080"
                    />
                    <span className="text-[9px] text-slate-500 block mt-0.5">App port on phone</span>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] font-medium text-slate-300 light:text-slate-700">
                        PC Local Port
                      </label>
                      <button
                        type="button"
                        onClick={handleFindAvailablePort}
                        disabled={isFindingPort}
                        className="text-[9px] font-mono text-cyan-400 hover:text-cyan-300 flex items-center gap-1 cursor-pointer bg-[#141e33] px-1.5 py-0.5 rounded border border-[#1e2d4a] hover:border-cyan-500/40 transition-colors"
                        title="Scan for available PC port starting at 8090"
                      >
                        <RefreshCw size={9} className={isFindingPort ? 'animate-spin' : ''} />
                        <span>Find Free Port</span>
                      </button>
                    </div>
                    <input
                      type="number"
                      value={localPort}
                      onChange={(e) => setLocalPort(Number(e.target.value))}
                      className="w-full bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded px-2.5 py-1.5 text-xs text-white light:text-slate-900 font-mono focus:outline-none focus:border-cyan-500 transition-colors"
                      placeholder="8090"
                    />
                    <span className="text-[9px] text-slate-500 block mt-0.5">Host PC forward target</span>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] font-medium text-slate-300 light:text-slate-700">
                        Stream Path
                      </label>
                      <span className="text-[9px] font-mono text-slate-500">Endpoint</span>
                    </div>
                    <input
                      type="text"
                      value={streamPath}
                      onChange={(e) => setStreamPath(e.target.value)}
                      className="w-full bg-[#141e33] light:bg-white border border-[#1e2d4a] light:border-[#d1d5db] rounded px-2.5 py-1.5 text-xs text-white light:text-slate-900 font-mono focus:outline-none focus:border-cyan-500 transition-colors"
                      placeholder="/video"
                    />
                    <span className="text-[9px] text-slate-500 block mt-0.5">MJPEG / Video URI</span>
                  </div>
                </div>

                {/* Tunnel Architecture Card */}
                <div className="p-3 rounded-lg bg-[#0a0f1d] border border-[#1e2d4a] space-y-2">
                  <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                    <span className="flex items-center gap-1 text-slate-300">
                      <Smartphone size={11} className="text-purple-400" /> Phone :{phonePort}
                    </span>
                    <span className="text-cyan-400 font-bold">───[ USB Cable (ADB forward) ]───▶</span>
                    <span className="flex items-center gap-1 text-slate-300">
                      <Usb size={11} className="text-cyan-400" /> PC 127.0.0.1:{localPort}
                    </span>
                  </div>

                  <div className="flex items-center justify-between gap-3 pt-1 border-t border-[#1e2d4a]/60">
                    <div className="min-w-0">
                      <span className="text-[10px] uppercase font-mono text-slate-400 block">SHIELD Video Stream URL</span>
                      <span className="text-xs font-mono font-bold text-cyan-300 truncate block">
                        http://127.0.0.1:{localPort}{streamPath}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={handleTestUsbStream}
                      disabled={isUsbTesting}
                      className="px-3 py-1.5 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/40 text-xs font-mono text-cyan-300 flex items-center gap-1.5 transition-all cursor-pointer shadow-xs disabled:opacity-50"
                    >
                      {isUsbTesting ? (
                        <>
                          <Loader2 size={12} className="animate-spin text-cyan-400" />
                          <span>Testing Feed...</span>
                        </>
                      ) : (
                        <>
                          <Radio size={12} className="text-cyan-400" />
                          <span>Test USB Stream</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {/* USB Test Result Card */}
              {usbTestResult && (
                <div
                  className={`p-3 rounded-lg border text-xs flex items-start gap-2.5 animate-fadeIn ${
                    usbTestResult.success
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                      : 'bg-red-500/10 border-red-500/30 text-red-300'
                  }`}
                >
                  {usbTestResult.success ? (
                    <>
                      <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-semibold text-white">USB Video Feed Validated!</p>
                        <p className="text-[11px] font-mono text-emerald-300/90 mt-0.5">
                          {usbTestResult.message} • Port: tcp:{usbTestResult.local_port || localPort} • Frames confirmed
                          {usbTestResult.resolution ? ` • ${usbTestResult.resolution}` : ''}
                        </p>
                      </div>
                    </>
                  ) : (
                    <>
                      <AlertCircle size={16} className="text-red-400 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-semibold text-white">USB Stream Test Failed</p>
                        <p className="text-[11px] font-mono text-red-300/90 mt-0.5">{usbTestResult.message}</p>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ═══════════════════════════════════════════════════════════
              TAB: CCTV & PHONE (Wi-Fi)
             ═══════════════════════════════════════════════════════════ */}
          {(activeTab === 'CCTV' || activeTab === 'PHONE') && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-medium text-slate-300 light:text-slate-700">
                  {activeTab === 'CCTV' ? 'RTSP / Stream URL' : 'Phone IP Webcam Stream URL'}{' '}
                  <span className="text-red-400">*</span>
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
                placeholder={
                  activeTab === 'CCTV'
                    ? 'rtsp://admin:password@192.168.1.100:554/live/ch0'
                    : 'http://192.168.1.45:8080/video'
                }
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

          {/* ═══════════════════════════════════════════════════════════
              TAB: LAPTOP WEBCAM
             ═══════════════════════════════════════════════════════════ */}
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
                  Real-time YOLOv8 frame inference will run automatically on the browser webcam stream with isolated
                  tracking and spatial zone analysis.
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
              className={`px-5 py-2 rounded-lg text-white text-xs font-medium transition-all shadow-md flex items-center gap-1.5 disabled:opacity-50 cursor-pointer ${
                activeTab === 'USB_PHONE'
                  ? 'bg-cyan-600 hover:bg-cyan-500'
                  : activeTab === 'WEBCAM'
                  ? 'bg-emerald-600 hover:bg-emerald-500'
                  : activeTab === 'PHONE'
                  ? 'bg-amber-600 hover:bg-amber-500'
                  : 'bg-[#1d6af5] hover:bg-[#1655c7]'
              }`}
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>Connecting...</span>
                </>
              ) : (
                <span>
                  {activeTab === 'USB_PHONE'
                    ? 'Connect USB Phone Camera'
                    : activeTab === 'WEBCAM'
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
