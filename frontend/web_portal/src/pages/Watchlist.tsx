import React, { useEffect, useState, useRef } from 'react';
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
} from 'lucide-react';
import { useStore } from '../store/useStore';
import * as api from '../services/api';
import type { WatchlistPerson, TestFaceMatchResult } from '../types';

export function Watchlist() {
  const watchlist = useStore((s) => s.watchlist);
  const fetchWatchlist = useStore((s) => s.fetchWatchlist);
  const addWatchlistPersonToStore = useStore((s) => s.addWatchlistPersonToStore);
  const updateWatchlistPersonInStore = useStore((s) => s.updateWatchlistPersonInStore);
  const removeWatchlistPersonFromStore = useStore((s) => s.removeWatchlistPersonFromStore);

  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterPriority, setFilterPriority] = useState<string>('ALL');

  // Add Person Modal State
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [threatPriority, setThreatPriority] = useState<'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'>('HIGH');
  const [notes, setNotes] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Test Match Modal State
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testFile, setTestFile] = useState<File | null>(null);
  const [testPreview, setTestPreview] = useState<string | null>(null);
  const [testThreshold, setTestThreshold] = useState<number>(45);
  const [testSubmitting, setTestSubmitting] = useState(false);
  const [testResult, setTestResult] = useState<TestFaceMatchResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  // Delete confirmation
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);

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

  // Handle Register Form Submit
  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setFormError('Target full name is required.');
      return;
    }
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

      // Reset form & close
      setName('');
      setIdentifier('');
      setNotes('');
      setThreatPriority('HIGH');
      setSelectedFile(null);
      setImagePreview(null);
      setIsAddModalOpen(false);
    } catch (err: any) {
      console.error('[Watchlist] Registration error:', err);
      const detail = err.response?.data?.detail || err.message || 'Failed to register target face.';
      setFormError(detail);
    } finally {
      setFormSubmitting(false);
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

  // Handle Test Face Match
  const handleTestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testFile) {
      setTestError('Please select a probe photograph to test matching.');
      return;
    }

    setTestSubmitting(true);
    setTestError(null);
    setTestResult(null);

    try {
      const formData = new FormData();
      formData.append('file', testFile);
      formData.append('threshold', (testThreshold / 100).toString());

      const res = await api.testFaceMatch(formData);
      setTestResult(res);
    } catch (err: any) {
      console.error('[Watchlist] Test match error:', err);
      setTestError(err.response?.data?.detail || 'Failed to process probe image.');
    } finally {
      setTestSubmitting(false);
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

  return (
    <div className="space-y-6">
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
            Registered Persons of Interest (POI) evaluated against live camera streams and forensic video.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setTestFile(null);
              setTestPreview(null);
              setTestResult(null);
              setTestError(null);
              setIsTestModalOpen(true);
            }}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-sm font-medium transition-colors"
          >
            <Scan className="w-4 h-4 text-emerald-400" />
            <span>Test Face Match</span>
          </button>

          <button
            onClick={() => {
              setName('');
              setIdentifier('');
              setNotes('');
              setThreatPriority('HIGH');
              setSelectedFile(null);
              setImagePreview(null);
              setFormError(null);
              setIsAddModalOpen(true);
            }}
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
            <div className="text-xs text-slate-400 font-medium">Embedding Engine</div>
            <div className="text-sm font-bold text-cyan-400 font-mono mt-1.5">OpenCV SFace 128D</div>
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
            No persons of interest are currently registered. Register known individuals with face images to enable automated real-time recognition across CCTV and Webcam streams.
          </p>
          <button
            onClick={() => setIsAddModalOpen(true)}
            className="mt-6 inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shadow-lg shadow-blue-600/20 transition-colors"
          >
            <UserPlus className="w-4 h-4" />
            <span>Register First Target</span>
          </button>
        </div>
      ) : filteredList.length === 0 ? (
        <div className="bg-slate-800/30 border border-slate-700/60 rounded-xl p-8 text-center text-slate-400">
          <p className="text-sm">No targets matched your search query "{searchQuery}".</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filteredList.map((person) => {
            const photoUrl = person.photo_path
              ? `${backendRoot}${person.photo_path}`
              : null;

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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 max-w-sm w-full space-y-4 shadow-2xl">
            <div className="flex items-center gap-3 text-red-400">
              <AlertTriangle className="w-6 h-6" />
              <h3 className="text-base font-bold text-slate-100">Delete Watchlist Entry?</h3>
            </div>
            <p className="text-xs text-slate-300">
              This will permanently delete the registered biometric face embedding vector and target profile from SQLite.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setDeleteTargetId(null)}
                className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeletePerson(deleteTargetId)}
                className="px-3.5 py-1.5 bg-red-600 hover:bg-red-500 text-white text-xs font-semibold rounded-lg"
              >
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Register Target Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-5 shadow-2xl my-8">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-blue-400" />
                <h3 className="text-lg font-bold text-slate-100">Register Watchlist Target</h3>
              </div>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="text-slate-400 hover:text-slate-200"
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

            <form onSubmit={handleAddSubmit} className="space-y-4">
              {/* Photo Upload & Preview */}
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
                  onClick={() => setIsAddModalOpen(false)}
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
                      <span>Extracting Face Embedding...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Save & Extract 128-D Vector</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Test Probe Match Modal */}
      {isTestModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm overflow-y-auto">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-5 shadow-2xl my-8">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Scan className="w-5 h-5 text-emerald-400" />
                <h3 className="text-lg font-bold text-slate-100">Test Face Match Probe</h3>
              </div>
              <button
                onClick={() => setIsTestModalOpen(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <XCircle className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleTestSubmit} className="space-y-4">
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

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Match Threshold
                  </label>
                  <span className="text-xs font-mono font-bold text-emerald-400">
                    {testThreshold}% (cosine { (testThreshold / 100).toFixed(2) })
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
                  onClick={() => setIsTestModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium rounded-lg"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={testSubmitting || !testFile}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition-colors flex items-center gap-2 disabled:opacity-50"
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
    </div>
  );
}
