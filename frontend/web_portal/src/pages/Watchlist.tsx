import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  UserCheck,
  UserPlus,
  Trash2,
  Upload,
  ShieldAlert,
  ShieldCheck,
  Search,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Scan,
  RefreshCw,
  Eye,
  Info,
  Camera,
  Video,
  VideoOff,
  Volume2,
  VolumeX,
  Play,
  Pause,
  Maximize2,
  Sparkles,
  Radio,
  Crosshair,
  Activity,
  SlidersHorizontal,
} from 'lucide-react';
import { useStore } from '../store/useStore';
import * as api from '../services/api';
import type { WatchlistPerson, TestFaceMatchResult } from '../types';
import { useWebcamCapture } from '../hooks/useWebcamCapture';
import { playAlertChime } from '../utils/audio';

export function Watchlist() {
  const watchlist = useStore((s) => s.watchlist);
  const fetchWatchlist = useStore((s) => s.fetchWatchlist);
  const addWatchlistPersonToStore = useStore((s) => s.addWatchlistPersonToStore);
  const updateWatchlistPersonInStore = useStore((s) => s.updateWatchlistPersonInStore);
  const removeWatchlistPersonFromStore = useStore((s) => s.removeWatchlistPersonFromStore);

  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterPriority, setFilterPriority] = useState<string>('ALL');

  // --- Add Person Modal State ---
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [registerMode, setRegisterMode] = useState<'webcam' | 'file'>('webcam');
  const [name, setName] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [threatPriority, setThreatPriority] = useState<'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'>('HIGH');
  const [notes, setNotes] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [webcamSnapshot, setWebcamSnapshot] = useState<string | null>(null);
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // --- Test Match Modal State ---
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testMode, setTestMode] = useState<'webcam' | 'file'>('webcam');
  const [testFile, setTestFile] = useState<File | null>(null);
  const [testPreview, setTestPreview] = useState<string | null>(null);
  const [testWebcamSnapshot, setTestWebcamSnapshot] = useState<string | null>(null);
  const [testThreshold, setTestThreshold] = useState<number>(45);
  const [testSubmitting, setTestSubmitting] = useState(false);
  const [testResult, setTestResult] = useState<TestFaceMatchResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  // --- Live Webcam Surveillance Scanner Modal State ---
  const [isScannerOpen, setIsScannerOpen] = useState(false);
  const [autoScanActive, setAutoScanActive] = useState(true);
  const [soundAlerts, setSoundAlerts] = useState(true);
  const [scannerThreshold, setScannerThreshold] = useState(45);
  const [isScanningFrame, setIsScanningFrame] = useState(false);
  const [lastScanResult, setLastScanResult] = useState<TestFaceMatchResult | null>(null);
  const [lastScanSnapshot, setLastScanSnapshot] = useState<string | null>(null);
  const [lastScanTime, setLastScanTime] = useState<string | null>(null);
  const [scanHistory, setScanHistory] = useState<
    Array<{
      id: string;
      timestamp: string;
      result: TestFaceMatchResult;
      snapshot: string;
    }>
  >([]);

  // Delete confirmation
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);

  // Webcam Hooks
  const registerWebcam = useWebcamCapture();
  const testWebcam = useWebcamCapture();
  const scannerWebcam = useWebcamCapture();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const testFileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setLoading(true);
    fetchWatchlist().finally(() => setLoading(false));
  }, [fetchWatchlist]);

  // Handle Photo selection for Registration
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setFormError(null);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  // Capture frame from Register Webcam
  const handleCaptureRegisterPhoto = () => {
    const frame = registerWebcam.captureFrame();
    if (frame) {
      setWebcamSnapshot(frame);
      setFormError(null);
    } else {
      setFormError('Failed to capture frame from webcam. Ensure your face is centered in the camera.');
    }
  };

  // Retake Register Photo
  const handleRetakeRegisterPhoto = () => {
    setWebcamSnapshot(null);
    if (!registerWebcam.isReady) {
      registerWebcam.startStream();
    }
  };

  // Open Register Target Modal
  const openRegisterModal = () => {
    setName('');
    setIdentifier('');
    setNotes('');
    setThreatPriority('HIGH');
    setSelectedFile(null);
    setImagePreview(null);
    setWebcamSnapshot(null);
    setFormError(null);
    setRegisterMode('webcam');
    setIsAddModalOpen(true);
    registerWebcam.startStream();
  };

  // Close Register Target Modal
  const closeRegisterModal = () => {
    registerWebcam.stopStream();
    setIsAddModalOpen(false);
  };

  // Handle Register Form Submit
  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setFormError('Target full name is required.');
      return;
    }

    if (registerMode === 'webcam') {
      if (!webcamSnapshot) {
        setFormError('Please capture a face photograph from the live laptop webcam.');
        return;
      }

      setFormSubmitting(true);
      setFormError(null);

      try {
        const created = await api.registerWatchlistPersonWebcam({
          name: name.trim(),
          identifier: identifier.trim() || undefined,
          notes: notes.trim() || undefined,
          threat_priority: threatPriority,
          is_active: true,
          image_base64: webcamSnapshot,
        });

        addWatchlistPersonToStore(created);
        closeRegisterModal();
      } catch (err: any) {
        console.error('[Watchlist] Webcam registration error:', err);
        const detail =
          err.response?.data?.detail ||
          err.message ||
          'Failed to extract 128-D biometric vector from webcam photo.';
        setFormError(detail);
      } finally {
        setFormSubmitting(false);
      }
    } else {
      if (!selectedFile) {
        setFormError('A clear face photograph is required for biometric registration.');
        return;
      }

      setFormSubmitting(true);
      setFormError(null);

      try {
        const formData = new FormData();
        formData.append('name', name.trim());
        if (identifier.trim()) formData.append('identifier', identifier.trim());
        if (notes.trim()) formData.append('notes', notes.trim());
        formData.append('threat_priority', threatPriority);
        formData.append('is_active', 'true');
        formData.append('file', selectedFile);

        const created = await api.registerWatchlistPerson(formData);
        addWatchlistPersonToStore(created);
        closeRegisterModal();
      } catch (err: any) {
        console.error('[Watchlist] Registration error:', err);
        const detail = err.response?.data?.detail || err.message || 'Failed to register target face.';
        setFormError(detail);
      } finally {
        setFormSubmitting(false);
      }
    }
  };

  // Open Test Probe Modal
  const openTestModal = () => {
    setTestFile(null);
    setTestPreview(null);
    setTestWebcamSnapshot(null);
    setTestResult(null);
    setTestError(null);
    setTestMode('webcam');
    setIsTestModalOpen(true);
    testWebcam.startStream();
  };

  // Close Test Probe Modal
  const closeTestModal = () => {
    testWebcam.stopStream();
    setIsTestModalOpen(false);
  };

  // Handle Test Face Match
  const handleTestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTestSubmitting(true);
    setTestError(null);
    setTestResult(null);

    try {
      if (testMode === 'webcam') {
        const frame = testWebcamSnapshot || testWebcam.captureFrame();
        if (!frame) {
          setTestError('Please capture a photo from the live webcam or activate camera stream.');
          setTestSubmitting(false);
          return;
        }
        setTestWebcamSnapshot(frame);

        const res = await api.testFaceMatchWebcam({
          image_base64: frame,
          threshold: testThreshold / 100,
        });
        setTestResult(res);
        if (res.match_found) {
          playAlertChime();
        }
      } else {
        if (!testFile) {
          setTestError('Please select a probe photograph to test matching.');
          setTestSubmitting(false);
          return;
        }

        const formData = new FormData();
        formData.append('file', testFile);
        formData.append('threshold', (testThreshold / 100).toString());

        const res = await api.testFaceMatch(formData);
        setTestResult(res);
        if (res.match_found) {
          playAlertChime();
        }
      }
    } catch (err: any) {
      console.error('[Watchlist] Test match error:', err);
      setTestError(err.response?.data?.detail || 'Failed to process probe image.');
    } finally {
      setTestSubmitting(false);
    }
  };

  // Open Scanner Modal
  const openScannerModal = () => {
    setIsScannerOpen(true);
    setLastScanResult(null);
    setLastScanSnapshot(null);
    scannerWebcam.startStream();
  };

  // Close Scanner Modal
  const closeScannerModal = () => {
    scannerWebcam.stopStream();
    setIsScannerOpen(false);
  };

  // Continuous Auto-Scan loop for Live Webcam Scanner
  useEffect(() => {
    if (!isScannerOpen || !autoScanActive || !scannerWebcam.isReady) return;

    const intervalId = setInterval(async () => {
      if (isScanningFrame) return;
      const frame = scannerWebcam.captureFrame();
      if (!frame) return;

      try {
        setIsScanningFrame(true);
        const res = await api.testFaceMatchWebcam({
          image_base64: frame,
          threshold: scannerThreshold / 100,
        });

        setLastScanResult(res);
        setLastScanSnapshot(frame);
        setLastScanTime(new Date().toLocaleTimeString());

        if (res.match_found) {
          if (soundAlerts) {
            playAlertChime();
          }
          setScanHistory((prev) => [
            {
              id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              timestamp: new Date().toLocaleTimeString(),
              result: res,
              snapshot: frame,
            },
            ...prev.slice(0, 7),
          ]);
        }
      } catch (e) {
        console.warn('[Watchlist Scanner] Scan frame error:', e);
      } finally {
        setIsScanningFrame(false);
      }
    }, 2000);

    return () => clearInterval(intervalId);
  }, [
    isScannerOpen,
    autoScanActive,
    scannerWebcam.isReady,
    isScanningFrame,
    scannerThreshold,
    soundAlerts,
  ]);

  // Manual Trigger Scan for Live Scanner
  const handleManualScanNow = async () => {
    if (isScanningFrame || !scannerWebcam.isReady) return;
    const frame = scannerWebcam.captureFrame();
    if (!frame) return;

    try {
      setIsScanningFrame(true);
      const res = await api.testFaceMatchWebcam({
        image_base64: frame,
        threshold: scannerThreshold / 100,
      });

      setLastScanResult(res);
      setLastScanSnapshot(frame);
      setLastScanTime(new Date().toLocaleTimeString());

      if (res.match_found) {
        if (soundAlerts) {
          playAlertChime();
        }
        setScanHistory((prev) => [
          {
            id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            timestamp: new Date().toLocaleTimeString(),
            result: res,
            snapshot: frame,
          },
          ...prev.slice(0, 7),
        ]);
      }
    } catch (e: any) {
      console.error('[Watchlist Scanner] Manual scan failed:', e);
    } finally {
      setIsScanningFrame(false);
    }
  };

  // Handle Toggle Active
  const handleToggleActive = async (person: WatchlistPerson) => {
    const nextState = !person.is_active;
    updateWatchlistPersonInStore(person.id, { is_active: nextState });
    try {
      await api.updateWatchlistPerson(person.id, { is_active: nextState });
    } catch (err) {
      console.error('[Watchlist] Toggle status error:', err);
      updateWatchlistPersonInStore(person.id, { is_active: person.is_active });
    }
  };

  // Handle Delete
  const handleDeletePerson = async (id: string) => {
    try {
      await api.deleteWatchlistPerson(id);
      removeWatchlistPersonFromStore(id);
      setDeleteTargetId(null);
    } catch (err) {
      console.error('[Watchlist] Delete error:', err);
    }
  };

  // Filtered List
  const filteredList = watchlist.filter((p) => {
    const matchesSearch =
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (p.identifier && p.identifier.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (p.notes && p.notes.toLowerCase().includes(searchQuery.toLowerCase()));

    const matchesPriority = filterPriority === 'ALL' || p.threat_priority === filterPriority;
    return matchesSearch && matchesPriority;
  });

  const activeCount = watchlist.filter((p) => p.is_active).length;
  const criticalCount = watchlist.filter((p) => p.threat_priority === 'CRITICAL' && p.is_active).length;

  const backendRoot = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  // Matched person details helper for scanner display
  const matchedPerson = lastScanResult?.person_id
    ? watchlist.find((p) => p.id === lastScanResult.person_id)
    : null;

  return (
    <div className="space-y-6">
      {/* Dynamic Keyframes for HUD Scanning Beam */}
      <style>{`
        @keyframes scanSweep {
          0% { top: 6%; opacity: 0.8; }
          50% { top: 92%; opacity: 1; }
          100% { top: 6%; opacity: 0.8; }
        }
        .animate-scan-sweep {
          animation: scanSweep 2.2s ease-in-out infinite;
        }
      `}</style>

      {/* Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-wider text-slate-100 uppercase">
              Target Watchlist
            </h1>
            <span className="bg-red-500/10 border border-red-500/30 text-red-400 text-xs px-2.5 py-0.5 rounded font-mono font-bold tracking-wider">
              REAL BIOMETRICS
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Registered Persons of Interest (POI) evaluated against live laptop webcam and IP surveillance cameras.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Live Laptop Webcam Scanner Button */}
          <button
            onClick={openScannerModal}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/40 text-sm font-semibold shadow-lg shadow-cyan-500/10 transition-all hover:border-cyan-400"
          >
            <Camera className="w-4 h-4 text-cyan-400 animate-pulse" />
            <span>Live Webcam Scanner</span>
          </button>

          {/* Test Face Match Button */}
          <button
            onClick={openTestModal}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-sm font-medium transition-colors"
          >
            <Scan className="w-4 h-4 text-emerald-400" />
            <span>Test Probe</span>
          </button>

          {/* Register Target Button */}
          <button
            onClick={openRegisterModal}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shadow-lg shadow-blue-600/20 transition-colors"
          >
            <UserPlus className="w-4 h-4" />
            <span>Register Target</span>
          </button>
        </div>
      </div>

      {/* KPI Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Total Registered</div>
            <div className="text-2xl font-bold text-slate-100 font-mono mt-1">{watchlist.length}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
            <UserCheck className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Active Surveillance</div>
            <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">{activeCount}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <ShieldCheck className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Critical Threat POIs</div>
            <div className="text-2xl font-bold text-red-400 font-mono mt-1">{criticalCount}</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center text-red-400">
            <ShieldAlert className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 font-medium">Biometric Pipeline</div>
            <div className="text-sm font-bold text-cyan-400 font-mono mt-1.5">YuNet + SFace 128D</div>
          </div>
          <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Scan className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Filters & Search Toolbar */}
      <div className="bg-slate-800/50 border border-slate-700/60 rounded-xl p-3 flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search by name, ID, or notes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-900/80 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <span className="text-xs text-slate-400 whitespace-nowrap">Priority:</span>
          <select
            value={filterPriority}
            onChange={(e) => setFilterPriority(e.target.value)}
            className="bg-slate-900/80 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
          >
            <option value="ALL">All Priorities</option>
            <option value="CRITICAL">🔴 Critical Only</option>
            <option value="HIGH">🟠 High Only</option>
            <option value="MEDIUM">🟡 Medium Only</option>
            <option value="LOW">🟢 Low Only</option>
          </select>

          <button
            onClick={() => fetchWatchlist()}
            className="p-1.5 bg-slate-900/80 border border-slate-700 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors"
            title="Refresh Watchlist"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Watchlist Cards Grid / Empty State */}
      {loading ? (
        <div className="py-16 text-center text-slate-400">
          <RefreshCw className="w-8 h-8 animate-spin mx-auto text-blue-500 mb-2" />
          <p className="text-sm">Loading registered watchlist targets...</p>
        </div>
      ) : watchlist.length === 0 ? (
        <div className="bg-slate-800/30 border border-dashed border-slate-700 rounded-2xl p-12 text-center">
          <div className="w-16 h-16 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center mx-auto text-slate-500 mb-4">
            <UserCheck className="w-8 h-8" />
          </div>
          <h3 className="text-lg font-bold text-slate-200 uppercase tracking-wide">
            NO WATCHLIST ENTRIES
          </h3>
          <p className="text-sm text-slate-400 max-w-md mx-auto mt-2">
            No persons of interest are currently registered. Register targets via live laptop webcam or photo upload to enable real-time tactical recognition.
          </p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={openRegisterModal}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shadow-lg shadow-blue-600/20 transition-colors"
            >
              <Camera className="w-4 h-4" />
              <span>Enroll via Laptop Webcam</span>
            </button>
          </div>
        </div>
      ) : filteredList.length === 0 ? (
        <div className="bg-slate-800/30 border border-slate-700/60 rounded-xl p-8 text-center text-slate-400">
          <p className="text-sm">No targets matched your search query "{searchQuery}".</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredList.map((person) => {
            const photoUrl = person.photo_path ? `${backendRoot}${person.photo_path}` : null;

            const priorityBadge =
              person.threat_priority === 'CRITICAL'
                ? 'bg-red-500/20 text-red-400 border-red-500/40'
                : person.threat_priority === 'HIGH'
                ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                : person.threat_priority === 'MEDIUM'
                ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40'
                : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40';

            return (
              <div
                key={person.id}
                className={`relative bg-slate-800/80 border rounded-xl overflow-hidden transition-all duration-200 ${
                  person.is_active
                    ? 'border-slate-700/80 hover:border-slate-600 shadow-md'
                    : 'border-slate-800 opacity-60'
                }`}
              >
                {/* Photo Header */}
                <div className="relative h-44 bg-slate-900/90 flex items-center justify-center overflow-hidden border-b border-slate-700/50">
                  {photoUrl ? (
                    <img
                      src={photoUrl}
                      alt={person.name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLElement).style.display = 'none';
                      }}
                    />
                  ) : (
                    <div className="text-slate-600 flex flex-col items-center">
                      <UserCheck className="w-12 h-12" />
                      <span className="text-xs mt-1">No Photo</span>
                    </div>
                  )}

                  {/* Priority Tag */}
                  <div className="absolute top-2.5 left-2.5">
                    <span
                      className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded border ${priorityBadge}`}
                    >
                      {person.threat_priority}
                    </span>
                  </div>

                  {/* Active Toggle */}
                  <div className="absolute top-2.5 right-2.5">
                    <button
                      onClick={() => handleToggleActive(person)}
                      className={`text-xs px-2.5 py-0.5 rounded-full font-medium transition-colors border ${
                        person.is_active
                          ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                          : 'bg-slate-700/80 border-slate-600 text-slate-400'
                      }`}
                    >
                      {person.is_active ? 'ACTIVE' : 'DISABLED'}
                    </button>
                  </div>
                </div>

                {/* Body Details */}
                <div className="p-4 space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h4 className="text-base font-bold text-slate-100 leading-tight">
                        {person.name}
                      </h4>
                      {person.identifier && (
                        <p className="text-xs text-blue-400 font-mono mt-0.5">
                          {person.identifier}
                        </p>
                      )}
                    </div>

                    <button
                      onClick={() => setDeleteTargetId(person.id)}
                      className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                      title="Delete Target"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  {person.notes && (
                    <p className="text-xs text-slate-400 line-clamp-2 bg-slate-900/40 p-2 rounded border border-slate-700/40">
                      {person.notes}
                    </p>
                  )}

                  <div className="pt-2 border-t border-slate-700/50 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                    <span>128-D Vector Stored</span>
                    <span>{new Date(person.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteTargetId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-sm w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-red-400">
              <AlertTriangle className="w-6 h-6 flex-shrink-0" />
              <h3 className="text-base font-bold text-slate-100">Delete Watchlist Target</h3>
            </div>
            <p className="text-sm text-slate-300">
              Are you sure you want to delete this target? Their biometric 128-D embedding and enrolled photo will be permanently purged.
            </p>
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setDeleteTargetId(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeletePerson(deleteTargetId)}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-xs font-bold rounded-lg shadow-lg shadow-red-600/20"
              >
                Delete Target
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 1. REGISTER TARGET MODAL (WITH LIVE LAPTOP WEBCAM)                        */}
      {/* ========================================================================= */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-5 shadow-2xl my-8">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-blue-500/20 border border-blue-500/40 flex items-center justify-center text-blue-400">
                  <UserPlus className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-100">Register Watchlist Target</h3>
                  <p className="text-[11px] text-slate-400">Extracts 128-D SFace biometric vector from facial image</p>
                </div>
              </div>
              <button
                onClick={closeRegisterModal}
                className="text-slate-400 hover:text-slate-200 p-1"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {formError && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-400 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{formError}</span>
              </div>
            )}

            {/* Mode Switcher Tabs */}
            <div className="grid grid-cols-2 gap-1 p-1 bg-slate-800/80 border border-slate-700/60 rounded-xl">
              <button
                type="button"
                onClick={() => {
                  setRegisterMode('webcam');
                  if (!registerWebcam.isReady) registerWebcam.startStream();
                }}
                className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-bold transition-all ${
                  registerMode === 'webcam'
                    ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Camera className="w-3.5 h-3.5" />
                <span>Live Laptop Webcam</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setRegisterMode('file');
                  registerWebcam.stopStream();
                }}
                className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-bold transition-all ${
                  registerMode === 'file'
                    ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Upload className="w-3.5 h-3.5" />
                <span>Upload Photo File</span>
              </button>
            </div>

            <form onSubmit={handleAddSubmit} className="space-y-4">
              {/* Webcam Capture Viewport */}
              {registerMode === 'webcam' ? (
                <div className="space-y-2">
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Face Enrollment Frame <span className="text-cyan-400">*</span>
                  </label>

                  {webcamSnapshot ? (
                    // Captured Snapshot Preview
                    <div className="relative rounded-xl overflow-hidden border-2 border-emerald-500/50 bg-slate-950 aspect-video flex items-center justify-center shadow-lg">
                      <img
                        src={webcamSnapshot}
                        alt="Captured Webcam Frame"
                        className="w-full h-full object-cover"
                      />
                      <div className="absolute top-2 left-2 bg-emerald-500/90 text-slate-950 text-[10px] font-bold px-2 py-0.5 rounded shadow">
                        ✓ FRAME CAPTURED
                      </div>
                      <div className="absolute bottom-2 right-2 flex gap-2">
                        <button
                          type="button"
                          onClick={handleRetakeRegisterPhoto}
                          className="px-3 py-1 bg-slate-900/90 hover:bg-slate-900 text-slate-200 text-xs font-semibold rounded-lg border border-slate-700 backdrop-blur shadow flex items-center gap-1.5"
                        >
                          <RefreshCw className="w-3 h-3" />
                          <span>Retake Photo</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    // Live Camera Viewfinder with HUD Reticle
                    <div className="relative rounded-xl overflow-hidden border border-slate-700 bg-black aspect-video flex items-center justify-center">
                      <video
                        ref={registerWebcam.videoRef}
                        autoPlay
                        playsInline
                        muted
                        className="w-full h-full object-cover mirror"
                      />

                      {/* HUD Corner Targeting Brackets */}
                      <div className="absolute inset-4 pointer-events-none">
                        <div className="absolute top-0 left-0 w-6 h-6 border-t-2 border-l-2 border-cyan-400" />
                        <div className="absolute top-0 right-0 w-6 h-6 border-t-2 border-r-2 border-cyan-400" />
                        <div className="absolute bottom-0 left-0 w-6 h-6 border-b-2 border-l-2 border-cyan-400" />
                        <div className="absolute bottom-0 right-0 w-6 h-6 border-b-2 border-r-2 border-cyan-400" />

                        {/* Center Facial Framing Reticle */}
                        <div className="absolute inset-0 m-auto w-36 h-44 rounded-full border border-dashed border-cyan-400/60 flex items-center justify-center">
                          <div className="w-2 h-2 rounded-full bg-cyan-400/80 animate-ping" />
                        </div>
                      </div>

                      {/* Status Badges */}
                      <div className="absolute top-2.5 left-2.5 flex items-center gap-2">
                        <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-900/80 border border-slate-700 text-[10px] font-mono font-semibold text-emerald-400 backdrop-blur">
                          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                          LIVE LAPTOP WEBCAM
                        </span>
                      </div>

                      {/* Loading or Error Overlays */}
                      {registerWebcam.isLoading && (
                        <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm flex flex-col items-center justify-center text-slate-300 gap-2">
                          <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
                          <span className="text-xs font-medium">Connecting to laptop camera...</span>
                        </div>
                      )}

                      {registerWebcam.error && (
                        <div className="absolute inset-0 bg-slate-950/90 p-4 flex flex-col items-center justify-center text-center gap-2">
                          <AlertTriangle className="w-7 h-7 text-red-400" />
                          <p className="text-xs text-red-300">{registerWebcam.error}</p>
                          <button
                            type="button"
                            onClick={() => registerWebcam.startStream()}
                            className="mt-1 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 rounded border border-slate-600"
                          >
                            Retry Camera
                          </button>
                        </div>
                      )}

                      {/* Capture Trigger Button */}
                      {registerWebcam.isReady && (
                        <div className="absolute bottom-3 inset-x-0 flex justify-center">
                          <button
                            type="button"
                            onClick={handleCaptureRegisterPhoto}
                            className="px-4 py-1.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold rounded-lg shadow-lg shadow-cyan-500/30 flex items-center gap-2 transition-transform active:scale-95"
                          >
                            <Camera className="w-3.5 h-3.5" />
                            <span>Capture Face Frame</span>
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                  <p className="text-[11px] text-slate-500">
                    Align your face within the reticle under clear lighting, then capture the snapshot.
                  </p>
                </div>
              ) : (
                // File Upload Section
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Face Photograph <span className="text-red-400">*</span>
                  </label>
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    className={`border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-all ${
                      imagePreview
                        ? 'border-blue-500/50 bg-blue-500/5'
                        : 'border-slate-700 hover:border-slate-500 bg-slate-800/40'
                    }`}
                  >
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept="image/jpeg,image/png,image/webp"
                      onChange={handleFileChange}
                      className="hidden"
                    />

                    {imagePreview ? (
                      <div className="flex flex-col items-center gap-2">
                        <img
                          src={imagePreview}
                          alt="Preview"
                          className="w-24 h-24 object-cover rounded-lg border border-blue-500/40 shadow"
                        />
                        <span className="text-xs text-blue-400 font-medium">Click to change photo</span>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center gap-1.5 py-3">
                        <Upload className="w-8 h-8 text-slate-400" />
                        <span className="text-xs font-semibold text-slate-200">
                          Upload front-facing photo
                        </span>
                        <span className="text-[11px] text-slate-500">
                          JPEG or PNG with clear visible facial landmarks
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Target Name */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                  Full Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Vikram Sharma"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Identifier & Threat Priority */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                    Identifier / Code
                  </label>
                  <input
                    type="text"
                    placeholder="POI-9821"
                    value={identifier}
                    onChange={(e) => setIdentifier(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 font-mono"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                    Threat Priority
                  </label>
                  <select
                    value={threatPriority}
                    onChange={(e: any) => setThreatPriority(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500 font-semibold"
                  >
                    <option value="CRITICAL">🔴 CRITICAL</option>
                    <option value="HIGH">🟠 HIGH</option>
                    <option value="MEDIUM">🟡 MEDIUM</option>
                    <option value="LOW">🟢 LOW</option>
                  </select>
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1">
                  Operational Notes
                </label>
                <textarea
                  rows={2}
                  placeholder="Additional context or briefing details..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Submit Buttons */}
              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={closeRegisterModal}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={formSubmitting}
                  className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded-lg shadow-lg shadow-blue-600/20 transition-colors flex items-center gap-2 disabled:opacity-50"
                >
                  {formSubmitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Extracting Biometric Vector...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Enroll Target & Extract Vector</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. TEST FACE MATCH PROBE MODAL (WEBCAM & FILE)                            */}
      {/* ========================================================================= */}
      {isTestModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-5 shadow-2xl my-8">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Scan className="w-5 h-5 text-emerald-400" />
                <h3 className="text-lg font-bold text-slate-100">Test Face Match Probe</h3>
              </div>
              <button
                onClick={closeTestModal}
                className="text-slate-400 hover:text-slate-200"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            {/* Probe Source Tabs */}
            <div className="grid grid-cols-2 gap-1 p-1 bg-slate-800/80 border border-slate-700/60 rounded-xl">
              <button
                type="button"
                onClick={() => {
                  setTestMode('webcam');
                  if (!testWebcam.isReady) testWebcam.startStream();
                }}
                className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-bold transition-all ${
                  testMode === 'webcam'
                    ? 'bg-emerald-600 text-white shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Camera className="w-3.5 h-3.5" />
                <span>Live Webcam Probe</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setTestMode('file');
                  testWebcam.stopStream();
                }}
                className={`flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-xs font-bold transition-all ${
                  testMode === 'file'
                    ? 'bg-emerald-600 text-white shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Upload className="w-3.5 h-3.5" />
                <span>Upload Test File</span>
              </button>
            </div>

            <form onSubmit={handleTestSubmit} className="space-y-4">
              {testMode === 'webcam' ? (
                <div className="space-y-2">
                  <div className="relative rounded-xl overflow-hidden border border-slate-700 bg-black aspect-video flex items-center justify-center">
                    <video
                      ref={testWebcam.videoRef}
                      autoPlay
                      playsInline
                      muted
                      className="w-full h-full object-cover mirror"
                    />

                    {/* HUD Reticle */}
                    <div className="absolute inset-3 pointer-events-none">
                      <div className="absolute top-0 left-0 w-5 h-5 border-t-2 border-l-2 border-emerald-400" />
                      <div className="absolute top-0 right-0 w-5 h-5 border-t-2 border-r-2 border-emerald-400" />
                      <div className="absolute bottom-0 left-0 w-5 h-5 border-b-2 border-l-2 border-emerald-400" />
                      <div className="absolute bottom-0 right-0 w-5 h-5 border-b-2 border-r-2 border-emerald-400" />
                    </div>

                    {testWebcam.isLoading && (
                      <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm flex flex-col items-center justify-center text-slate-300 gap-2">
                        <RefreshCw className="w-6 h-6 animate-spin text-emerald-400" />
                        <span className="text-xs">Accessing camera...</span>
                      </div>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Look at the camera, then click "Run Match Probe" below to sample the live frame.
                  </p>
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-1.5">
                    Probe Image
                  </label>
                  <div
                    onClick={() => testFileInputRef.current?.click()}
                    className="border-2 border-dashed border-slate-700 hover:border-slate-500 bg-slate-800/40 rounded-xl p-4 text-center cursor-pointer"
                  >
                    <input
                      type="file"
                      ref={testFileInputRef}
                      accept="image/*"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setTestFile(file);
                          setTestResult(null);
                          setTestError(null);
                          const reader = new FileReader();
                          reader.onloadend = () => setTestPreview(reader.result as string);
                          reader.readAsDataURL(file);
                        }
                      }}
                      className="hidden"
                    />

                    {testPreview ? (
                      <div className="flex flex-col items-center gap-2">
                        <img
                          src={testPreview}
                          alt="Probe"
                          className="w-24 h-24 object-cover rounded-lg border border-emerald-500/40"
                        />
                        <span className="text-xs text-emerald-400 font-medium">Click to change probe photo</span>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center gap-1.5 py-3">
                        <Upload className="w-7 h-7 text-slate-400" />
                        <span className="text-xs font-semibold text-slate-200">
                          Upload test image
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Threshold Slider */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Match Threshold
                  </label>
                  <span className="text-xs font-mono font-bold text-emerald-400">
                    {testThreshold}% (cosine {(testThreshold / 100).toFixed(2)})
                  </span>
                </div>
                <input
                  type="range"
                  min={30}
                  max={80}
                  step={1}
                  value={testThreshold}
                  onChange={(e) => setTestThreshold(Number(e.target.value))}
                  className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                />
              </div>

              {testError && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-400">
                  {testError}
                </div>
              )}

              {testResult && (
                <div
                  className={`p-4 rounded-xl border space-y-2 ${
                    testResult.match_found
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                      : testResult.face_detected
                      ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                      : 'bg-red-500/10 border-red-500/30 text-red-300'
                  }`}
                >
                  <div className="flex items-center gap-2 font-bold text-sm">
                    {testResult.match_found ? (
                      <>
                        <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                        <span>MATCH CONFIRMED: {testResult.person_name}</span>
                      </>
                    ) : testResult.face_detected ? (
                      <>
                        <Info className="w-5 h-5 text-amber-400" />
                        <span>UNKNOWN FACE (No Watchlist Match)</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-5 h-5 text-red-400" />
                        <span>NO FACE DETECTED</span>
                      </>
                    )}
                  </div>

                  <p className="text-xs leading-relaxed opacity-90">{testResult.message}</p>

                  {testResult.face_detected && (
                    <div className="pt-2 border-t border-slate-700/50 flex items-center justify-between text-xs font-mono">
                      <span>Similarity: {testResult.similarity.toFixed(1)}%</span>
                      <span>Cosine Score: {testResult.cosine_score.toFixed(4)}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={closeTestModal}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={testSubmitting || (testMode === 'file' && !testFile)}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50 shadow-lg shadow-emerald-600/20"
                >
                  {testSubmitting ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>Computing Similarity...</span>
                    </>
                  ) : (
                    <>
                      <Scan className="w-3.5 h-3.5" />
                      <span>Run Match Probe</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. LIVE WEBCAM SURVEILLANCE SCANNER MODAL (TACTICAL HUD)                  */}
      {/* ========================================================================= */}
      {isScannerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/85 backdrop-blur-md overflow-y-auto">
          <div className="bg-slate-900 border border-cyan-500/40 rounded-2xl max-w-5xl w-full p-5 sm:p-6 space-y-4 shadow-2xl shadow-cyan-950/40 my-4 border-t-cyan-400">
            {/* HUD Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/20 border border-cyan-500/50 flex items-center justify-center text-cyan-400">
                  <Activity className="w-4 h-4 animate-pulse" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-slate-100 uppercase tracking-wider">
                      Live Webcam Watchlist Scanner
                    </h3>
                    <span className="bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 text-[10px] font-mono font-bold px-2 py-0.5 rounded">
                      LAPTOP SENSOR ACTIVE
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">
                    Real-time biometric facial recognition evaluated against {activeCount} active targets
                  </p>
                </div>
              </div>

              {/* Quick Controls Bar */}
              <div className="flex items-center gap-2">
                {/* Audio Alert Toggle */}
                <button
                  onClick={() => setSoundAlerts(!soundAlerts)}
                  className={`p-2 rounded-lg border text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                    soundAlerts
                      ? 'bg-blue-500/20 border-blue-500/40 text-blue-300'
                      : 'bg-slate-800 border-slate-700 text-slate-400'
                  }`}
                  title={soundAlerts ? 'Audio alert chime enabled' : 'Audio alert chime muted'}
                >
                  {soundAlerts ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
                  <span className="hidden md:inline">{soundAlerts ? 'Alarm ON' : 'Muted'}</span>
                </button>

                {/* Auto Scan Toggle */}
                <button
                  onClick={() => setAutoScanActive(!autoScanActive)}
                  className={`px-3 py-2 rounded-lg border text-xs font-bold transition-colors flex items-center gap-1.5 ${
                    autoScanActive
                      ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                      : 'bg-slate-800 border-slate-700 text-slate-400'
                  }`}
                >
                  {autoScanActive ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                  <span>{autoScanActive ? 'Auto-Scan ON' : 'Auto-Scan Paused'}</span>
                </button>

                <button
                  onClick={closeScannerModal}
                  className="p-2 text-slate-400 hover:text-slate-100 hover:bg-slate-800 rounded-lg transition-colors"
                >
                  <XCircle className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Main Scanner Grid: Viewport + Telemetry Panel */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              {/* Left Side: Live Video Viewport with HUD Overlay (7 Cols) */}
              <div className="lg:col-span-7 space-y-3">
                <div className="relative rounded-2xl overflow-hidden border-2 border-cyan-500/40 bg-black aspect-video shadow-2xl flex items-center justify-center">
                  <video
                    ref={scannerWebcam.videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="w-full h-full object-cover mirror"
                  />

                  {/* High-Tech Tactical Corner Reticle */}
                  <div className="absolute inset-4 pointer-events-none">
                    <div className="absolute top-0 left-0 w-8 h-8 border-t-2 border-l-2 border-cyan-400 shadow-[0_0_8px_#22d3ee]" />
                    <div className="absolute top-0 right-0 w-8 h-8 border-t-2 border-r-2 border-cyan-400 shadow-[0_0_8px_#22d3ee]" />
                    <div className="absolute bottom-0 left-0 w-8 h-8 border-b-2 border-l-2 border-cyan-400 shadow-[0_0_8px_#22d3ee]" />
                    <div className="absolute bottom-0 right-0 w-8 h-8 border-b-2 border-r-2 border-cyan-400 shadow-[0_0_8px_#22d3ee]" />

                    {/* Central Targeting Box */}
                    <div className="absolute inset-0 m-auto w-48 h-56 rounded-2xl border border-cyan-400/40 flex items-center justify-center">
                      <Crosshair className="w-6 h-6 text-cyan-400/60" />
                    </div>

                    {/* Animated Scanning Beam */}
                    {autoScanActive && (
                      <div className="absolute inset-x-4 h-0.5 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_12px_#22d3ee] animate-scan-sweep pointer-events-none" />
                    )}
                  </div>

                  {/* Top HUD Telemetry Status */}
                  <div className="absolute top-3 inset-x-3 flex items-center justify-between pointer-events-none">
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-950/80 border border-slate-700/80 text-[10px] font-mono font-bold text-emerald-400 backdrop-blur">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        LIVE STREAM
                      </span>
                      {isScanningFrame && (
                        <span className="flex items-center gap-1 px-2.5 py-1 rounded bg-cyan-950/90 border border-cyan-500/50 text-[10px] font-mono font-bold text-cyan-300 backdrop-blur animate-pulse">
                          <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                          ANALYZING FRAME...
                        </span>
                      )}
                    </div>

                    <span className="px-2 py-1 rounded bg-slate-950/80 border border-slate-700/80 text-[10px] font-mono text-slate-400 backdrop-blur">
                      THRESH: {scannerThreshold}%
                    </span>
                  </div>

                  {/* Target Match In-View Alert Overlay */}
                  {lastScanResult?.match_found && (
                    <div className="absolute bottom-3 inset-x-3 bg-red-600/90 border border-red-400/80 rounded-xl p-2.5 text-white backdrop-blur shadow-2xl flex items-center justify-between animate-pulse">
                      <div className="flex items-center gap-2">
                        <AlertTriangle className="w-5 h-5 text-yellow-300 flex-shrink-0" />
                        <div>
                          <div className="text-xs font-black uppercase tracking-wider">
                            TARGET CONFIRMED: {lastScanResult.person_name}
                          </div>
                          <div className="text-[10px] font-mono text-red-100">
                            Similarity: {lastScanResult.similarity.toFixed(1)}% (cosine {lastScanResult.cosine_score.toFixed(3)})
                          </div>
                        </div>
                      </div>
                      <span className="text-[10px] font-mono font-bold bg-white text-red-700 px-2 py-0.5 rounded">
                        MATCH
                      </span>
                    </div>
                  )}

                  {/* Loading overlay if camera warming up */}
                  {scannerWebcam.isLoading && (
                    <div className="absolute inset-0 bg-slate-950/90 backdrop-blur-sm flex flex-col items-center justify-center text-slate-300 gap-2">
                      <RefreshCw className="w-8 h-8 animate-spin text-cyan-400" />
                      <span className="text-sm font-semibold">Starting laptop webcam sensor...</span>
                    </div>
                  )}
                </div>

                {/* Bottom Bar: Manual Scan + Sensitivity Controls */}
                <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-slate-800/60 border border-slate-700/60 rounded-xl">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleManualScanNow}
                      disabled={isScanningFrame || !scannerWebcam.isReady}
                      className="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold rounded-lg shadow transition-colors flex items-center gap-1.5 disabled:opacity-50"
                    >
                      <Scan className="w-3.5 h-3.5" />
                      <span>Scan Frame Now</span>
                    </button>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Last probe: {lastScanTime || 'Ready'}
                    </span>
                  </div>

                  {/* Threshold Adjuster */}
                  <div className="flex items-center gap-2">
                    <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400" />
                    <span className="text-[11px] text-slate-400">Match Threshold:</span>
                    <input
                      type="range"
                      min={30}
                      max={75}
                      step={1}
                      value={scannerThreshold}
                      onChange={(e) => setScannerThreshold(Number(e.target.value))}
                      className="w-24 h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-cyan-400"
                    />
                    <span className="text-xs font-mono font-bold text-cyan-400 w-8">
                      {scannerThreshold}%
                    </span>
                  </div>
                </div>
              </div>

              {/* Right Side: Biometric Telemetry & Match Intelligence (5 Cols) */}
              <div className="lg:col-span-5 space-y-3">
                {/* Active Match Card */}
                <div className="bg-slate-800/80 border border-slate-700/80 rounded-2xl p-4 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-700/60 pb-2">
                    <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                      Sensor Intelligence
                    </span>
                    <span
                      className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                        lastScanResult?.match_found
                          ? 'bg-red-500/20 text-red-400 border-red-500/40'
                          : lastScanResult?.face_detected
                          ? 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                          : 'bg-slate-700/50 text-slate-400 border-slate-600/50'
                      }`}
                    >
                      {lastScanResult?.match_found
                        ? 'TARGET MATCH'
                        : lastScanResult?.face_detected
                        ? 'UNKNOWN FACE'
                        : 'SCANNING...'}
                    </span>
                  </div>

                  {lastScanResult?.match_found && matchedPerson ? (
                    // Confirmed Match Details Card
                    <div className="space-y-3">
                      {/* Side-by-Side Comparison: Live Probe vs Enrolled Watchlist Photo */}
                      <div className="grid grid-cols-2 gap-2">
                        <div className="space-y-1">
                          <span className="text-[10px] font-semibold text-slate-400 uppercase">
                            Live Probe Crop
                          </span>
                          <div className="h-28 rounded-lg overflow-hidden border border-cyan-500/40 bg-black">
                            {lastScanSnapshot && (
                              <img
                                src={lastScanSnapshot}
                                alt="Live Probe"
                                className="w-full h-full object-cover"
                              />
                            )}
                          </div>
                        </div>
                        <div className="space-y-1">
                          <span className="text-[10px] font-semibold text-slate-400 uppercase">
                            Enrolled Mugshot
                          </span>
                          <div className="h-28 rounded-lg overflow-hidden border border-red-500/40 bg-black">
                            {matchedPerson.photo_path && (
                              <img
                                src={`${backendRoot}${matchedPerson.photo_path}`}
                                alt="Enrolled"
                                className="w-full h-full object-cover"
                              />
                            )}
                          </div>
                        </div>
                      </div>

                      {/* POI Metadata */}
                      <div className="bg-slate-900/90 border border-red-500/30 rounded-xl p-3 space-y-1.5">
                        <div className="flex items-center justify-between">
                          <h4 className="text-sm font-bold text-slate-100">
                            {matchedPerson.name}
                          </h4>
                          <span
                            className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${
                              matchedPerson.threat_priority === 'CRITICAL'
                                ? 'bg-red-500/20 text-red-400 border-red-500/40'
                                : 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                            }`}
                          >
                            {matchedPerson.threat_priority}
                          </span>
                        </div>
                        {matchedPerson.identifier && (
                          <div className="text-xs font-mono text-blue-400">
                            ID: {matchedPerson.identifier}
                          </div>
                        )}
                        {matchedPerson.notes && (
                          <p className="text-[11px] text-slate-400 line-clamp-2">
                            {matchedPerson.notes}
                          </p>
                        )}
                        <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[11px] font-mono text-emerald-400">
                          <span>Similarity: {lastScanResult.similarity.toFixed(1)}%</span>
                          <span>Cosine: {lastScanResult.cosine_score.toFixed(4)}</span>
                        </div>
                      </div>
                    </div>
                  ) : lastScanResult?.face_detected ? (
                    // Unknown Face (No Match)
                    <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl space-y-2 text-amber-300">
                      <div className="flex items-center gap-2 font-bold text-xs">
                        <Info className="w-4 h-4 text-amber-400" />
                        <span>Unknown Subject in View</span>
                      </div>
                      <p className="text-xs text-amber-200/80 leading-relaxed">
                        Face landmarks detected, but cosine score did not meet the {scannerThreshold}% threshold against registered targets.
                      </p>
                      <div className="text-[11px] font-mono text-amber-400/70 pt-1 border-t border-amber-500/20">
                        Top Similarity: {lastScanResult.similarity.toFixed(1)}% (cosine {lastScanResult.cosine_score.toFixed(3)})
                      </div>
                    </div>
                  ) : (
                    // Idle Standby View
                    <div className="py-8 text-center text-slate-500 space-y-2">
                      <Crosshair className="w-8 h-8 mx-auto text-slate-600 animate-pulse" />
                      <p className="text-xs">
                        Position subject facing the laptop webcam. The scanner automatically evaluates frames every 2 seconds.
                      </p>
                    </div>
                  )}
                </div>

                {/* Match Incident Feed */}
                <div className="bg-slate-800/80 border border-slate-700/80 rounded-2xl p-3.5 space-y-2">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-300 uppercase tracking-wider pb-1 border-b border-slate-700/60">
                    <span>Recent Detections</span>
                    <span className="font-mono text-[10px] text-slate-500">
                      {scanHistory.length} incident{scanHistory.length === 1 ? '' : 's'}
                    </span>
                  </div>

                  {scanHistory.length === 0 ? (
                    <div className="py-4 text-center text-slate-500 text-xs">
                      No watchlist targets identified yet in this session.
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                      {scanHistory.map((item) => (
                        <div
                          key={item.id}
                          className="flex items-center justify-between p-2 bg-slate-900/80 border border-red-500/30 rounded-lg text-xs"
                        >
                          <div className="flex items-center gap-2.5">
                            <img
                              src={item.snapshot}
                              alt="Thumb"
                              className="w-8 h-8 rounded object-cover border border-red-500/40"
                            />
                            <div>
                              <div className="font-bold text-slate-100">
                                {item.result.person_name}
                              </div>
                              <div className="text-[10px] font-mono text-emerald-400">
                                {item.result.similarity.toFixed(1)}% match
                              </div>
                            </div>
                          </div>
                          <span className="text-[10px] font-mono text-slate-400">
                            {item.timestamp}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
