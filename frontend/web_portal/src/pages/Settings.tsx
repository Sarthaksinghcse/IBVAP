import { Save, Info, Volume2 } from 'lucide-react';
import { useStore } from '../store/useStore';
import { useState, useEffect } from 'react';
import { ZoneEditorModal } from '../components/monitoring/ZoneEditorModal';
import { playPersonDetectedBeep } from '../utils/audio';

interface SettingRowProps {
  label: string;
  description?: string;
  children: React.ReactNode;
}

function SettingRow({ label, description, children }: SettingRowProps) {
  return (
    <div className="flex items-start justify-between gap-6 py-4 border-b border-[#272b37] light:border-[#d3d8e3] last:border-0">
      <div className="flex-1">
        <div className="text-sm font-semibold text-white light:text-slate-900">{label}</div>
        {description && <p className="text-xs text-[#9aa2b5] light:text-slate-500 mt-0.5">{description}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-[#22c55e] focus:ring-offset-2 ${
        value ? 'bg-[#22c55e]' : 'bg-[#272b37] light:bg-slate-300'
      }`}
    >
      <span
        aria-hidden="true"
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
          value ? 'translate-x-5' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

export default function Settings() {
  const settings = useStore((s) => s.settings);
  const updateSetting = useStore((s) => s.updateSetting);
  const zones = useStore((s) => s.zones);
  const fetchZones = useStore((s) => s.fetchZones);
  const cameras = useStore((s) => s.cameras);
  const fetchCameras = useStore((s) => s.fetchCameras);
  const isWebcamActive = useStore((s) => s.isWebcamActive);
  const cameraMode = useStore((s) => s.cameraMode);
  const activeCameraStream = useStore((s) => s.activeCameraStream);

  const [apiBaseUrl, setApiBaseUrl] = useState('http://localhost:8000');
  const [wsUrl, setWsUrl] = useState('ws://localhost:8000/ws/alerts');
  const [wsReconnectDelay, setWsReconnectDelay] = useState(2);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [editingZoneSource, setEditingZoneSource] = useState<{ id: string; name: string; type: 'CAMERA' | 'WEBCAM' } | null>(null);

  useEffect(() => {
    fetchZones();
    fetchCameras();
  }, [fetchZones, fetchCameras]);

  const handleSave = () => {
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  return (
    <div className="max-w-3xl space-y-4">
      {/* Info banner */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-4 flex items-start gap-3 shadow-card transition-colors">
        <Info size={18} className="text-[#22c55e] light:text-[#15803d] flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-bold text-white light:text-slate-900">SHIELD System Configuration</p>
          <p className="text-xs text-[#9aa2b5] light:text-slate-500 mt-0.5">
            Settings control live detection parameters, threshold filtering, alert chime audio, and automatic response actions.
          </p>
        </div>
      </div>

      {/* Detection Settings */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
        <h3 className="text-sm font-bold text-white light:text-slate-900 pb-3 border-b border-[#272b37] light:border-[#d3d8e3]">
          Detection Settings
        </h3>
        <SettingRow label="Show Bounding Boxes" description="Render AI detection bounding boxes on video feeds">
          <Toggle value={settings.showBoundingBoxes} onChange={(v) => updateSetting('showBoundingBoxes', v)} />
        </SettingRow>
        <SettingRow label="Show Restricted Zone" description="Display configured zone polygon overlay on active source viewport">
          <Toggle value={settings.showRestrictedZone} onChange={(v) => updateSetting('showRestrictedZone', v)} />
        </SettingRow>
        <SettingRow label="Show Confidence %" description="Display AI confidence scores on object label tags">
          <Toggle value={settings.showConfidence} onChange={(v) => updateSetting('showConfidence', v)} />
        </SettingRow>
        <SettingRow
          label="Detection Threshold"
          description={`Minimum confidence score for AI detection pipeline (currently: ${settings.aiThreshold}%)`}
        >
          <div className="flex items-center gap-2">
            <input
              type="range" min={30} max={95} step={5} value={settings.aiThreshold}
              onChange={(e) => updateSetting('aiThreshold', Number(e.target.value))}
              className="w-28 accent-[#22c55e]"
            />
            <span className="text-xs font-mono font-bold text-white light:text-slate-900 w-10">{settings.aiThreshold}%</span>
          </div>
        </SettingRow>
        <SettingRow
          label="Loitering Threshold"
          description={`Generate loitering threat alert if object remains in zone for (currently: ${settings.loiteringThreshold}s)`}
        >
          <div className="flex items-center gap-2">
            <input
              type="range" min={5} max={60} step={5} value={settings.loiteringThreshold}
              onChange={(e) => updateSetting('loiteringThreshold', Number(e.target.value))}
              className="w-28 accent-[#22c55e]"
            />
            <span className="text-xs font-mono font-bold text-white light:text-slate-900 w-10">{settings.loiteringThreshold}s</span>
          </div>
        </SettingRow>

        {/* Real Face Recognition Settings */}
        <SettingRow
          label="Face Recognition & Watchlist Matching"
          description="Run real OpenCV YuNet face detection & SFace 128-D biometric matching on detected persons"
        >
          <Toggle
            value={settings.faceRecognitionEnabled ?? true}
            onChange={(v) => updateSetting('faceRecognitionEnabled', v)}
          />
        </SettingRow>

        {(settings.faceRecognitionEnabled ?? true) && (
          <SettingRow
            label="Face Match Similarity Threshold"
            description={`Biometric cosine similarity required to confirm a Watchlist target match (currently: ${settings.faceMatchThreshold ?? 45}% / cosine ${( (settings.faceMatchThreshold ?? 45) / 100 ).toFixed(2)})`}
          >
            <div className="flex items-center gap-2">
              <input
                type="range"
                min={30}
                max={80}
                step={1}
                value={settings.faceMatchThreshold ?? 45}
                onChange={(e) => updateSetting('faceMatchThreshold', Number(e.target.value))}
                className="w-28 accent-red-500"
              />
              <span className="text-xs font-mono font-bold text-red-400 w-10">
                {settings.faceMatchThreshold ?? 45}%
              </span>
            </div>
          </SettingRow>
        )}

        {/* Real ANPR Settings */}
        <SettingRow
          label="Automatic Number Plate Recognition (ANPR)"
          description="Locate license plates on vehicles (CAR, TRUCK, BUS, MOTORCYCLE) and run local CRNN neural OCR"
        >
          <Toggle
            value={settings.anprEnabled ?? true}
            onChange={(v) => updateSetting('anprEnabled', v)}
          />
        </SettingRow>
      </div>



      {/* Camera-Specific Zone Profiles */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
        <div className="flex items-center justify-between pb-3 border-b border-[#272b37] light:border-[#d3d8e3]">
          <div>
            <h3 className="text-sm font-bold text-white light:text-slate-900">
              Camera-Specific Spatial Zones
            </h3>
            <p className="text-xs text-[#9aa2b5] light:text-slate-500 mt-0.5">
              Each connected CCTV camera, Phone Wi-Fi source, and Laptop Webcam maintains its own independent spatial polygon boundary.
            </p>
          </div>
        </div>

        {(() => {
          const realSources = [
            ...(cameraMode && activeCameraStream
              ? [{
                  id: 'WEBCAM-01',
                  name: 'Laptop Webcam',
                  source_type: 'WEBCAM' as const,
                  status: 'ONLINE',
                  location: 'Local Built-in Camera',
                }]
              : []),
            ...cameras.map((c) => ({
              id: c.id,
              name: c.name || c.id,
              source_type: (c.source_type || 'CCTV') as 'CCTV' | 'PHONE' | 'WEBCAM',
              status: c.status,
              location: c.location,
            })),
          ];

          if (realSources.length === 0) {
            return (
              <div className="py-8 text-center">
                <p className="text-xs font-mono font-semibold text-[#9aa2b5] light:text-slate-500">No cameras connected</p>
                <p className="text-[11px] text-[#62697b] light:text-slate-400 mt-1">
                  Connect a CCTV camera via RTSP, a Phone Wi-Fi camera, or your laptop webcam to configure spatial zones.
                </p>
              </div>
            );
          }

          return (
            <div className="divide-y divide-[#272b37] light:divide-[#d3d8e3]">
              {realSources.map((src) => {
                const z = zones[src.id];
                const isConfigured = Boolean(z && z.coordinates && z.coordinates.length >= 3 && z.enabled);
                const isPhone = src.source_type === 'PHONE';
                const isWebcam = src.source_type === 'WEBCAM';

                return (
                  <div key={src.id} className="flex items-center justify-between py-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-white light:text-slate-900">{src.name}</span>
                          <span
                            className={`text-[9px] font-mono px-1.5 py-0.2 rounded font-semibold ${
                              isWebcam
                                ? 'bg-emerald-950/80 border border-emerald-500/30 text-emerald-300'
                                : isPhone
                                ? 'bg-amber-950/80 border border-amber-500/30 text-amber-300'
                                : 'bg-slate-800 border border-slate-700 text-slate-300'
                            }`}
                          >
                            {isWebcam ? 'LAPTOP WEBCAM' : isPhone ? 'PHONE / WIFI' : 'CCTV / RTSP'}
                          </span>
                          <span className="text-[10px] font-mono text-[#9aa2b5] light:text-slate-500">{src.id}</span>
                        </div>
                        <p className="text-[11px] text-[#9aa2b5] light:text-slate-500 mt-0.5 truncate">{src.location}</p>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 flex-shrink-0">
                      {isConfigured ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 light:text-[#15803d]">
                          {z.name} ({z.coordinates.length} pts)
                        </span>
                      ) : (
                        <span className="text-[11px] font-mono text-[#9aa2b5] light:text-slate-500">
                          No Zone Configured
                        </span>
                      )}

                      <button
                        type="button"
                        onClick={() =>
                          setEditingZoneSource({
                            id: src.id,
                            name: src.name,
                            type: src.source_type === 'WEBCAM' ? 'WEBCAM' : 'CAMERA',
                          })
                        }
                        className="text-xs font-mono px-3 py-1.5 rounded-xl bg-[#191c24] light:bg-slate-100 hover:bg-slate-700 light:hover:bg-slate-200 text-emerald-400 light:text-emerald-700 border border-[#272b37] light:border-slate-300 transition-all cursor-pointer shadow-xs font-semibold"
                      >
                        {isConfigured ? 'Edit Zone' : 'Configure'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })()}
      </div>

      {/* Alert Settings */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
        <h3 className="text-sm font-bold text-white light:text-slate-900 pb-3 border-b border-[#272b37] light:border-[#d3d8e3]">
          Alert Settings
        </h3>
        <SettingRow label="Alert Sound (Chime)" description="Play dual-tone sound when a new CRITICAL threat alert occurs">
          <Toggle value={settings.alertSound} onChange={(v) => updateSetting('alertSound', v)} />
        </SettingRow>
        <SettingRow label="Restricted Zone Person Beep" description="Play acoustic alert beep whenever a person enters or is detected inside a restricted zone">
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => playPersonDetectedBeep(true)}
              className="px-2.5 py-1 text-[11px] font-mono font-semibold rounded-lg bg-[#191c24] light:bg-slate-100 border border-[#272b37] light:border-[#d3d8e3] text-emerald-400 light:text-emerald-700 hover:bg-emerald-500/10 transition-colors cursor-pointer flex items-center gap-1.5 shadow-xs"
              title="Click to test restricted zone person intrusion beep"
            >
              <Volume2 size={12} /> Test Beep
            </button>
            <Toggle value={settings.personBeep ?? true} onChange={(v) => updateSetting('personBeep', v)} />
          </div>
        </SettingRow>
        <SettingRow label="Voice Alerting (Text-to-Speech)" description="Verbally announce critical security threats via browser speech synthesis">
          <Toggle value={settings.voiceAlerts ?? true} onChange={(v) => updateSetting('voiceAlerts', v)} />
        </SettingRow>
        <SettingRow label="Auto-Acknowledge Low Alerts" description="Automatically set status to ACKNOWLEDGED for LOW threat events">
          <Toggle value={settings.autoAcknowledge} onChange={(v) => updateSetting('autoAcknowledge', v)} />
        </SettingRow>

        <SettingRow label="Storage Retention" description="System log and snapshot storage period">
          <div className="flex items-center gap-2">
            <input
              type="number" min={1} max={365} value={settings.storageRetention}
              onChange={(e) => updateSetting('storageRetention', Number(e.target.value))}
              className="bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-1.5 w-20 text-center text-xs text-white light:text-slate-900 font-mono font-bold"
            />
            <span className="text-xs text-[#9aa2b5] light:text-slate-500">days</span>
          </div>
        </SettingRow>
      </div>

      {/* Connection Settings */}
      <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-5 shadow-card transition-colors">
        <h3 className="text-sm font-bold text-white light:text-slate-900 pb-3 border-b border-[#272b37] light:border-[#d3d8e3]">
          Backend Connection
        </h3>
        <SettingRow label="API Base URL" description="FastAPI backend service URL">
          <input
            type="text"
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            className="bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-1.5 w-56 text-xs font-mono text-white light:text-slate-900"
          />
        </SettingRow>
        <SettingRow label="WebSocket URL" description="Real-time alert broadcast stream">
          <input
            type="text"
            value={wsUrl}
            onChange={(e) => setWsUrl(e.target.value)}
            className="bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-1.5 w-56 text-xs font-mono text-white light:text-slate-900"
          />
        </SettingRow>
        <SettingRow label="WS Reconnect Delay" description="Seconds before reconnecting lost WebSocket session">
          <div className="flex items-center gap-2">
            <input
              type="number" min={1} max={60} value={wsReconnectDelay}
              onChange={(e) => setWsReconnectDelay(Number(e.target.value))}
              className="bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-1.5 w-20 text-center text-xs text-white light:text-slate-900 font-mono font-bold"
            />
            <span className="text-xs text-[#9aa2b5] light:text-slate-500">sec</span>
          </div>
        </SettingRow>
      </div>

      {/* Save Button */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          className="ibvap-btn-primary px-6 py-2.5 text-sm flex items-center gap-2 cursor-pointer shadow-md"
        >
          <Save size={14} /> Save Settings
        </button>
        {savedSuccess && (
          <span className="text-xs font-semibold text-emerald-400 light:text-[#15803d] animate-fadeIn">
            ✓ Settings saved successfully
          </span>
        )}
      </div>

      {/* Zone Editor Modal */}
      {editingZoneSource && (
        <ZoneEditorModal
          sourceId={editingZoneSource.id}
          sourceType={editingZoneSource.type}
          sourceLabel={editingZoneSource.name}
          isOpen={true}
          onClose={() => setEditingZoneSource(null)}
        />
      )}
    </div>
  );
}
