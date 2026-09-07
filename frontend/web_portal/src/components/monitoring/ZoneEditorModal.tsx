import { useState, useEffect, useRef } from 'react';
import { X, ShieldAlert, Check, Trash2, RotateCcw, Crosshair, HelpCircle, Layers } from 'lucide-react';
import { useStore } from '../../store/useStore';
import * as api from '../../services/api';
import type { Zone } from '../../types';

interface ZoneEditorModalProps {
  sourceId: string;
  sourceType: 'CAMERA' | 'WEBCAM' | 'VIDEO';
  sourceLabel?: string;
  isOpen: boolean;
  onClose: () => void;
}

export function ZoneEditorModal({
  sourceId,
  sourceType,
  sourceLabel,
  isOpen,
  onClose,
}: ZoneEditorModalProps) {
  const zones = useStore((s) => s.zones);
  const setZoneForSource = useStore((s) => s.setZoneForSource);
  const deleteZoneFromStore = useStore((s) => s.deleteZoneFromStore);

  const existingZone = zones[sourceId] as Zone | undefined;

  const [zoneName, setZoneName] = useState<string>('Restricted Zone A');
  const [zoneType, setZoneType] = useState<'RESTRICTED' | 'EXCLUSION' | 'BUFFER'>('RESTRICTED');
  const [enabled, setEnabled] = useState<boolean>(true);
  const [points, setPoints] = useState<[number, number][]>([]);
  const [saving, setSaving] = useState<boolean>(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setStatusMsg(null);
      if (existingZone && existingZone.coordinates && existingZone.coordinates.length >= 3) {
        setZoneName(existingZone.name || 'Restricted Zone A');
        setZoneType(existingZone.zone_type || 'RESTRICTED');
        setEnabled(existingZone.enabled ?? true);
        setPoints([...existingZone.coordinates]);
      } else {
        setZoneName('Restricted Zone A');
        setZoneType('RESTRICTED');
        setEnabled(true);
        setPoints([]);
      }
    }
  }, [isOpen, existingZone, sourceId]);

  if (!isOpen) return null;

  // Preset generators
  const applyPreset = (preset: 'left' | 'right' | 'center' | 'top') => {
    switch (preset) {
      case 'left':
        setPoints([[5, 5], [45, 5], [45, 95], [5, 95]]);
        break;
      case 'right':
        setPoints([[55, 5], [95, 5], [95, 95], [55, 95]]);
        break;
      case 'center':
        setPoints([[25, 20], [75, 20], [75, 80], [25, 80]]);
        break;
      case 'top':
        setPoints([[5, 5], [95, 5], [95, 45], [5, 45]]);
        break;
    }
  };

  // Convert client pointer event to normalized 0-100% SVG coordinates
  const getNormalizedCoords = (e: React.MouseEvent | MouseEvent): [number, number] | null => {
    if (!svgRef.current) return null;
    const rect = svgRef.current.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return null;
    const x = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
    const y = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
  };

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (draggingIdx !== null) return;
    const coords = getNormalizedCoords(e);
    if (!coords) return;

    if (points.length < 8) {
      setPoints((prev) => [...prev, coords]);
    }
  };

  const handlePointMouseDown = (idx: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setDraggingIdx(idx);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingIdx === null) return;
    const coords = getNormalizedCoords(e);
    if (!coords) return;
    setPoints((prev) => {
      const next = [...prev];
      next[draggingIdx] = coords;
      return next;
    });
  };

  const handleMouseUp = () => {
    setDraggingIdx(null);
  };

  const handleSave = async () => {
    if (points.length < 3) {
      setStatusMsg({ type: 'error', text: 'Zone polygon must have at least 3 points.' });
      return;
    }
    setSaving(true);
    setStatusMsg(null);
    try {
      const saved = await api.saveZone({
        source_id: sourceId,
        source_type: sourceType,
        name: zoneName.trim() || 'Restricted Zone A',
        coordinates: points,
        enabled,
        zone_type: zoneType,
      });
      setZoneForSource(sourceId, saved);
      setStatusMsg({ type: 'success', text: `Zone '${saved.name}' saved successfully for ${sourceId}!` });
      setTimeout(() => {
        onClose();
      }, 900);
    } catch (err: any) {
      console.error('[ZoneEditor] Error saving zone:', err);
      setStatusMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to save zone' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!existingZone) {
      setPoints([]);
      return;
    }
    setSaving(true);
    setStatusMsg(null);
    try {
      await api.deleteZone(sourceId);
      deleteZoneFromStore(sourceId);
      setPoints([]);
      setStatusMsg({ type: 'success', text: `Zone removed for ${sourceId}.` });
      setTimeout(() => {
        onClose();
      }, 700);
    } catch (err: any) {
      console.error('[ZoneEditor] Error deleting zone:', err);
      setStatusMsg({ type: 'error', text: err.response?.data?.detail || 'Failed to delete zone' });
    } finally {
      setSaving(false);
    }
  };

  const pointsString = points.map((p) => `${p[0]},${p[1]}`).join(' ');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fadeIn">
      <div className="ibvap-card p-0 w-full max-w-3xl overflow-hidden border border-[#1e2d4a] light:border-[#d1d5db] shadow-2xl flex flex-col max-h-[90vh] light:bg-white">
        {/* Modal Header */}
        <div className="px-5 py-3.5 bg-[#080d1c] light:bg-slate-50 border-b border-[#1e2d4a] light:border-[#d1d5db] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded bg-red-500/15 light:bg-red-100 border border-red-500/30 light:border-red-300 flex items-center justify-center text-red-400 light:text-red-700">
              <ShieldAlert size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-100 light:text-slate-900">
                  Spatial Restricted Zone Configuration
                </h3>
                <span className="px-2 py-0.5 rounded font-mono text-[10px] font-bold bg-[#1d6af5]/20 light:bg-blue-100 border border-[#1d6af5]/40 light:border-blue-300 text-[#1d6af5] light:text-blue-700">
                  {sourceId}
                </span>
              </div>
              <p className="text-xs text-slate-400 light:text-slate-500 mt-0.5">
                Attached to {sourceLabel || sourceId} · Normalized video coordinate space (0–100%)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded text-slate-400 light:text-slate-600 hover:text-white light:hover:text-slate-900 hover:bg-slate-800/60 light:hover:bg-slate-200 transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1 bg-[#0a0f1e] light:bg-white">
          {/* Status Message */}
          {statusMsg && (
            <div
              className={`p-2.5 rounded text-xs flex items-center gap-2 ${
                statusMsg.type === 'success'
                  ? 'bg-emerald-500/15 light:bg-emerald-50 border border-emerald-500/30 light:border-emerald-200 text-emerald-300 light:text-emerald-800'
                  : 'bg-red-500/15 light:bg-red-50 border border-red-500/30 light:border-red-200 text-red-300 light:text-red-800'
              }`}
            >
              {statusMsg.type === 'success' ? <Check size={14} /> : <ShieldAlert size={14} />}
              <span>{statusMsg.text}</span>
            </div>
          )}

          {/* Form settings */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <label className="text-[11px] font-mono uppercase text-slate-400 light:text-slate-600 block mb-1">
                Zone Identifier / Name
              </label>
              <input
                type="text"
                value={zoneName}
                onChange={(e) => setZoneName(e.target.value)}
                placeholder="e.g. Restricted Zone A"
                className="ibvap-input w-full text-xs"
              />
            </div>
            <div>
              <label className="text-[11px] font-mono uppercase text-slate-400 light:text-slate-600 block mb-1">
                Security Zone Type
              </label>
              <select
                value={zoneType}
                onChange={(e) => setZoneType(e.target.value as any)}
                className="ibvap-input w-full text-xs"
              >
                <option value="RESTRICTED">RESTRICTED (Intrusion Trigger)</option>
                <option value="EXCLUSION">EXCLUSION (No-Go Area)</option>
                <option value="BUFFER">BUFFER (Perimeter Warning)</option>
              </select>
            </div>
            <div className="flex items-center justify-between px-3 py-2 bg-[#141e33] light:bg-slate-50 border border-[#1e2d4a] light:border-[#d1d5db] rounded mt-auto">
              <div>
                <span className="text-xs font-semibold text-slate-200 light:text-slate-900 block">Zone Active</span>
                <span className="text-[10px] text-slate-500 light:text-slate-500">Enable AI threat evaluation</span>
              </div>
              <button
                type="button"
                onClick={() => setEnabled(!enabled)}
                className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ${
                  enabled ? 'bg-[#1d6af5]' : 'bg-[#1e2d4a] light:bg-slate-300'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ${
                    enabled ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          {/* Preset Buttons */}
          <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
            <span className="text-xs font-mono text-slate-400 light:text-slate-600 flex items-center gap-1.5">
              <Layers size={13} className="text-slate-400 light:text-slate-500" />
              Quick Presets:
            </span>
            <div className="flex items-center gap-1.5 flex-wrap">
              <button
                type="button"
                onClick={() => applyPreset('left')}
                className="text-[11px] font-mono px-2.5 py-1 rounded bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 text-slate-300 light:text-slate-800 border border-[#1e2d4a] light:border-slate-300 transition-all cursor-pointer"
              >
                Left Sector (0-50%)
              </button>
              <button
                type="button"
                onClick={() => applyPreset('right')}
                className="text-[11px] font-mono px-2.5 py-1 rounded bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 text-slate-300 light:text-slate-800 border border-[#1e2d4a] light:border-slate-300 transition-all cursor-pointer"
              >
                Right Sector (50-100%)
              </button>
              <button
                type="button"
                onClick={() => applyPreset('center')}
                className="text-[11px] font-mono px-2.5 py-1 rounded bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 text-slate-300 light:text-slate-800 border border-[#1e2d4a] light:border-slate-300 transition-all cursor-pointer"
              >
                Center Box
              </button>
              <button
                type="button"
                onClick={() => applyPreset('top')}
                className="text-[11px] font-mono px-2.5 py-1 rounded bg-[#141e33] light:bg-slate-100 hover:bg-[#1e2d4a] light:hover:bg-slate-200 text-slate-300 light:text-slate-800 border border-[#1e2d4a] light:border-slate-300 transition-all cursor-pointer"
              >
                Top Fence Perimeter
              </button>
              <button
                type="button"
                onClick={() => setPoints([])}
                className="text-[11px] font-mono px-2 py-1 rounded bg-red-500/15 light:bg-red-50 hover:bg-red-500/25 light:hover:bg-red-100 text-red-300 light:text-red-700 border border-red-500/30 light:border-red-200 transition-all flex items-center gap-1 cursor-pointer"
              >
                <RotateCcw size={11} /> Clear
              </button>
            </div>
          </div>

          {/* Interactive Visual Canvas */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-slate-400 light:text-slate-600">
              <span className="flex items-center gap-1 text-slate-400 light:text-slate-600">
                <Crosshair size={12} className="text-red-400" />
                Click viewport to add polygon vertex points (drag existing points to adjust):
              </span>
              <span className="font-mono text-slate-400 light:text-slate-600">
                {points.length} vertex point{points.length !== 1 ? 's' : ''} defined
              </span>
            </div>

            <div
              className="relative w-full h-72 rounded border border-[#1e2d4a] light:border-[#d1d5db] overflow-hidden select-none bg-[#050811]"
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            >
              {/* Grid backdrop */}
              <div
                className="absolute inset-0 opacity-15 pointer-events-none"
                style={{
                  backgroundImage:
                    'linear-gradient(to right, #3b82f6 1px, transparent 1px), linear-gradient(to bottom, #3b82f6 1px, transparent 1px)',
                  backgroundSize: '10% 10%',
                }}
              />

              {/* Center watermark */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
                <span className="font-mono text-3xl font-bold tracking-widest text-slate-600">
                  {sourceId} VIEWPORT
                </span>
              </div>

              {/* SVG Polygon Layer */}
              <svg
                ref={svgRef}
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                onClick={handleSvgClick}
                className="absolute inset-0 w-full h-full cursor-crosshair z-10"
              >
                {/* Render Polygon if at least 3 points */}
                {points.length >= 3 && (
                  <polygon
                    points={pointsString}
                    fill={enabled ? 'rgba(239, 68, 68, 0.18)' : 'rgba(100, 116, 139, 0.15)'}
                    stroke={enabled ? '#ef4444' : '#64748b'}
                    strokeWidth="0.8"
                    strokeDasharray="2,1"
                  />
                )}

                {/* Render lines if 2 points */}
                {points.length === 2 && (
                  <line
                    x1={points[0][0]}
                    y1={points[0][1]}
                    x2={points[1][0]}
                    y2={points[1][1]}
                    stroke="#ef4444"
                    strokeWidth="0.8"
                    strokeDasharray="2,1"
                  />
                )}

                {/* Render vertex drag handles */}
                {points.map((p, idx) => (
                  <g key={idx}>
                    <circle
                      cx={p[0]}
                      cy={p[1]}
                      r="1.8"
                      fill="#ef4444"
                      stroke="#ffffff"
                      strokeWidth="0.5"
                      className="cursor-move hover:r-2.5 transition-all"
                      onMouseDown={(e) => handlePointMouseDown(idx, e)}
                    />
                    <text
                      x={p[0] + 2}
                      y={p[1] - 2}
                      fill="#ffffff"
                      fontSize="3.5"
                      fontFamily="monospace"
                      className="pointer-events-none font-bold"
                    >
                      P{idx + 1}
                    </text>
                  </g>
                ))}
              </svg>

              {/* Empty state hint */}
              {points.length === 0 && (
                <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center pointer-events-none z-0">
                  <div className="w-10 h-10 rounded-full bg-red-500/10 border border-red-500/30 flex items-center justify-center text-red-400 mb-2">
                    <Crosshair size={20} />
                  </div>
                  <p className="text-xs font-semibold text-slate-300">No Restricted Zone Configured</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Click anywhere inside this viewport or select a preset above to define this camera's boundary.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Coordinate list */}
          {points.length > 0 && (
            <div className="p-2.5 rounded bg-[#141e33]/50 light:bg-slate-50 border border-[#1e2d4a] light:border-[#d1d5db] flex items-center gap-2 overflow-x-auto text-[10px] font-mono text-slate-400 light:text-slate-600">
              <span className="text-slate-500 font-bold uppercase flex-shrink-0">Coordinates (%):</span>
              {points.map((p, idx) => (
                <span key={idx} className="bg-[#080d1c] light:bg-white px-2 py-0.5 rounded border border-[#1e2d4a] light:border-slate-300 text-slate-300 light:text-slate-800 flex-shrink-0 font-medium">
                  P{idx + 1}: ({p[0]}%, {p[1]}%)
                </span>
              ))}
            </div>
          )}

          {/* Guidance note */}
          <div className="flex items-start gap-2 text-[11px] text-slate-500 light:text-slate-600 bg-[#080d1c] light:bg-slate-50 p-2.5 rounded border border-[#1e2d4a]/70 light:border-[#d1d5db]">
            <HelpCircle size={14} className="text-blue-400 light:text-blue-600 flex-shrink-0 mt-0.5" />
            <span>
              This geometry is isolated strictly to <strong className="text-slate-300 light:text-slate-900">{sourceId}</strong>. Other cameras will never share or inherit this zone unless separately defined.
            </span>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 bg-[#080d1c] light:bg-slate-50 border-t border-[#1e2d4a] light:border-[#d1d5db] flex items-center justify-between flex-wrap gap-2">
          <div>
            {existingZone && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={saving}
                className="text-xs text-red-400 light:text-red-700 hover:text-red-300 px-3 py-1.5 rounded bg-red-500/10 light:bg-red-50 hover:bg-red-500/20 light:hover:bg-red-100 border border-red-500/30 light:border-red-200 transition-all flex items-center gap-1.5 cursor-pointer"
              >
                <Trash2 size={13} /> Clear Zone Configuration
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs px-3 py-1.5 rounded text-slate-300 light:text-slate-800 hover:text-white light:hover:text-slate-900 bg-[#141e33] light:bg-slate-200 hover:bg-[#1e2d4a] light:hover:bg-slate-300 border border-[#1e2d4a] light:border-slate-300 transition-all cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || points.length < 3}
              className="ibvap-btn-primary text-xs py-1.5 px-4 flex items-center gap-1.5 shadow-glow-accent disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <Check size={13} /> {saving ? 'Saving Zone...' : `Save Zone for ${sourceId}`}
            </button>
          </div>
        </div>
      </div>
    </div>

  );
}
