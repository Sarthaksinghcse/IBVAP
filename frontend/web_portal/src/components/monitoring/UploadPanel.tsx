import { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, FileVideo, X, CheckCircle2, Loader2, Square, AlertCircle, RefreshCw, Play } from 'lucide-react';
import { useStore } from '../../store/useStore';
import * as api from '../../services/api';
import type { VideoStatus } from '../../types';

// ─── Status Steps ─────────────────────────────────────────────────────────────

const STATUS_STEPS: VideoStatus[] = ['READY', 'UPLOADING', 'PROCESSING', 'AI_ANALYZING', 'COMPLETED'];

const STATUS_LABELS: Record<VideoStatus, string> = {
  READY:        'Ready',
  UPLOADING:    'Uploading video file…',
  PROCESSING:   'Decoding video stream…',
  AI_ANALYZING: 'Analyzing with YOLOv8 & Tracker…',
  COMPLETED:    'Analysis complete',
  CANCELLED:    'Analysis cancelled',
  ERROR:        'Analysis failed',
};

function StepIndicator({ current }: { current: VideoStatus }) {
  const steps = STATUS_STEPS;
  const currentIdx = steps.indexOf(current);

  return (
    <div className="flex items-center gap-1">
      {steps.map((step, idx) => {
        const done    = idx < currentIdx || current === 'COMPLETED';
        const active  = idx === currentIdx && current !== 'COMPLETED';
        return (
          <div key={step} className="flex items-center gap-1">
            <div
              className={`
                w-2 h-2 rounded-full transition-all duration-300
                ${done   ? 'bg-green-400'  : ''}
                ${active ? 'bg-blue-400 animate-pulse' : ''}
                ${!done && !active ? 'bg-[#1e2d4a]' : ''}
              `}
            />
            {idx < steps.length - 1 && (
              <div className={`h-px w-4 transition-colors ${done ? 'bg-green-400/50' : 'bg-[#1e2d4a]'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Upload Panel ──────────────────────────────────────────────────────────────

export function UploadPanel() {
  const [dragOver, setDragOver] = useState(false);
  const [file, setFile]         = useState<File | null>(null);
  const [status, setStatus]     = useState<VideoStatus>('READY');
  const [uploadPct, setUploadPct] = useState(0);
  const [error, setError]       = useState<string | null>(null);
  const inputRef                = useRef<HTMLInputElement>(null);
  const pollTimerRef            = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMock                  = import.meta.env.VITE_USE_MOCK === 'true';

  const {
    setUploadProgress,
    setUploadStatus,
    setActiveVideoUrl,
    setActiveVideoId,
    setUploadedVideoName,
    setDetections,
    setAlerts,
    setPendingVideoBlob,
    pendingVideoBlob,
    selectedCameraId,
    videoAnalysisMetrics,
    setVideoAnalysisMetrics,
    activeVideoId
  } = useStore();

  const [existingVideos, setExistingVideos] = useState<import('../../types').Video[]>([]);
  const [loadingExisting, setLoadingExisting] = useState(false);

  useEffect(() => {
    api.getVideos()
      .then((vList) => {
        if (vList && vList.length > 0) {
          // Filter to completed videos
          setExistingVideos(vList.filter((v) => v.status === 'COMPLETED'));
        }
      })
      .catch((err) => console.warn('[UploadPanel] Failed to fetch existing videos:', err));
  }, []);

  const handleSelectExistingVideo = async (v: import('../../types').Video) => {
    setError(null);
    setLoadingExisting(true);
    setStatus('COMPLETED');
    setUploadStatus('COMPLETED');
    setActiveVideoId(v.id);
    setUploadedVideoName(v.filename);
    setVideoAnalysisMetrics({ progress: 100, status: 'COMPLETED' });

    const rawPath = v.file_path;
    const basename = rawPath
      ? rawPath.split(/[\\/]/).pop()
      : (v.id ? `${v.id}_${v.filename}` : v.filename);

    if (basename) {
      setActiveVideoUrl(`/storage/videos/${basename}`);
    }

    try {
      const dets = await api.getDetections(undefined, v.id, 5000);
      if (dets && dets.length > 0) {
        setDetections(dets);
      }
    } catch (dErr) {
      console.warn('[UploadPanel] Failed to fetch detections for selected video:', dErr);
    }

    try {
      const latestAlerts = await api.getAlerts();
      if (latestAlerts) setAlerts(latestAlerts);
    } catch (aErr) {
      console.warn('[UploadPanel] Failed to refresh alerts:', aErr);
    }
    setLoadingExisting(false);
  };

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, []);

  const handleFile = (f: File) => {
    if (!f.type.startsWith('video/') && !f.name.match(/\.(mp4|avi|mkv|mov)$/i)) {
      setError('Please select a valid video file (mp4, avi, mkv)');
      return;
    }
    // Clear all previous analysis state before setting new file
    setActiveVideoUrl(null);
    setActiveVideoId(null);
    setUploadedVideoName(null);
    setDetections([]);
    setUploadStatus(null);
    setVideoAnalysisMetrics(null);
    if (pendingVideoBlob) URL.revokeObjectURL(pendingVideoBlob);
    const blobUrl = URL.createObjectURL(f);
    setPendingVideoBlob(blobUrl);
    setUploadedVideoName(f.name);
    setFile(f);
    setError(null);
    setStatus('READY');
    setUploadPct(0);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, []);

  const handleStopAnalysis = async () => {
    if (activeVideoId) {
      try {
        await api.cancelVideoAnalysis(activeVideoId);
      } catch (e) {
        console.warn('[UploadPanel] Cancel error:', e);
      }
    }
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    setStatus('READY');
    setUploadStatus(null);
    setVideoAnalysisMetrics(null);
    setError('Analysis cancelled by user.');
  };

  const handleUpload = async () => {
    if (!file) return;
    setError(null);

    if (isMock) {
      setStatus('UPLOADING');
      for (let p = 0; p <= 100; p += 10) {
        await new Promise((r) => setTimeout(r, 60));
        setUploadPct(p);
      }
      setStatus('PROCESSING');
      await new Promise((r) => setTimeout(r, 1000));
      setStatus('AI_ANALYZING');
      await new Promise((r) => setTimeout(r, 1500));
      setStatus('COMPLETED');
      return;
    }

    try {
      setStatus('UPLOADING');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('camera_id', selectedCameraId || 'BOP-07');

      const res = await api.uploadVideo(formData, (pct) => {
        setUploadPct(pct);
        setUploadProgress(pct);
      });

      const videoId = res.id;
      setActiveVideoId(videoId);
      setUploadedVideoName(file.name);
      setStatus('AI_ANALYZING');
      setUploadStatus('AI_ANALYZING');

      // Poll real backend video analysis status
      const pollVideoStatus = async () => {
        try {
          const s = await api.getVideoAnalysisStatus(videoId);
          setVideoAnalysisMetrics({
            progress: s.progress,
            currentFrame: s.current_frame,
            totalFrames: s.total_frames,
            fps: s.fps,
            detections: s.detections,
            tracks: s.tracks,
            events: s.events,
            status: s.status,
          });

          if (s.status === 'PROCESSING' || s.status === 'AI_ANALYZING') {
            setStatus('AI_ANALYZING');
            setUploadStatus('AI_ANALYZING');
            pollTimerRef.current = setTimeout(pollVideoStatus, 800);
          } else if (s.status === 'COMPLETED') {
            setStatus('COMPLETED');
            setUploadStatus('COMPLETED');
            setVideoAnalysisMetrics({ progress: 100, status: 'COMPLETED' });

            // 1. Activate video URL for playback in CCTVPanel
            const rawPath = res.file_path;
            const basename = rawPath
              ? rawPath.split(/[\\/]/).pop()
              : (res.id ? `${res.id}_${file.name}` : file.name);

            if (basename) {
              setActiveVideoUrl(`/storage/videos/${basename}`);
            }

            // 2. Revoke thumbnail preview blob
            if (pendingVideoBlob) {
              URL.revokeObjectURL(pendingVideoBlob);
              setPendingVideoBlob(null);
            }

            // 3. Fetch real YOLO detections for this video
            try {
              const dets = await api.getDetections(undefined, videoId, 5000);
              if (dets && dets.length > 0) {
                setDetections(dets);
              }
            } catch (dErr) {
              console.warn('[UploadPanel] Failed to fetch detections:', dErr);
            }

            // 4. Refresh alerts
            try {
              const latestAlerts = await api.getAlerts();
              if (latestAlerts) {
                setAlerts(latestAlerts);
              }
            } catch (aErr) {
              console.warn('[UploadPanel] Failed to refresh alerts:', aErr);
            }
          } else if (s.status === 'CANCELLED') {
            setStatus('READY');
            setUploadStatus(null);
            setError('Analysis was cancelled.');
          } else if (s.status === 'ERROR') {
            setStatus('ERROR');
            setUploadStatus('ERROR');
            setError(s.error || 'YOLOv8 analysis encountered an error.');
          }
        } catch (err) {
          console.error('[UploadPanel] Status poll error:', err);
          pollTimerRef.current = setTimeout(pollVideoStatus, 1500);
        }
      };

      pollTimerRef.current = setTimeout(pollVideoStatus, 800);
    } catch (e) {
      setStatus('ERROR');
      setError('Upload failed. Check backend connection.');
    }
  };

  const reset = () => {
    if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    if (pendingVideoBlob) {
      URL.revokeObjectURL(pendingVideoBlob);
      setPendingVideoBlob(null);
    }
    setFile(null);
    setStatus('READY');
    setUploadPct(0);
    setError(null);
    setActiveVideoUrl(null);
    setActiveVideoId(null);
    setUploadedVideoName(null);
    setUploadStatus(null);
    setVideoAnalysisMetrics(null);
    setDetections([]);
  };

  const currentProgress = status === 'UPLOADING' ? uploadPct : (videoAnalysisMetrics?.progress ?? 0);

  return (
    <div className="bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d3d8e3] rounded-2xl p-4 shadow-card transition-colors">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Upload size={14} className="text-[#22c55e] light:text-[#15803d]" />
          <span className="text-sm font-semibold text-white light:text-slate-900">Upload CCTV Video</span>
        </div>
        {status !== 'READY' && (
          <StepIndicator current={status} />
        )}
      </div>

      {!file ? (
        <>
        /* ── Drop Zone ── */
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`
            border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200
            ${dragOver
              ? 'border-emerald-500 bg-emerald-500/10 light:bg-emerald-50'
              : 'border-[#272b37] light:border-[#d3d8e3] bg-[#191c24] light:bg-slate-50 hover:border-slate-500 light:hover:border-slate-400'
            }
          `}
        >
          <FileVideo size={32} className={`mx-auto mb-3 ${dragOver ? 'text-emerald-400' : 'text-[#62697b] light:text-slate-400'}`} />
          <p className="text-sm text-white light:text-slate-800 font-medium">Drag & drop a video file here</p>
          <p className="text-xs text-[#9aa2b5] light:text-slate-500 mt-1">or click to browse · MP4, AVI, MKV supported</p>
          <input
            ref={inputRef}
            type="file"
            accept="video/*"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
        </div>

        {/* Quick select existing analyzed videos */}
        {existingVideos.length > 0 && (
          <div className="mt-4 pt-3 border-t border-[#272b37] light:border-[#d3d8e3]">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-300 light:text-slate-700 flex items-center gap-1.5">
                <Play size={12} className="text-emerald-400" />
                Pre-Analyzed CCTV Footage ({existingVideos.length})
              </span>
              <span className="text-[10px] text-slate-500">Click to load instant ANPR & detections</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {existingVideos.slice(0, 4).map((v) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => handleSelectExistingVideo(v)}
                  disabled={loadingExisting}
                  className="flex items-center justify-between p-2.5 rounded-lg bg-[#191c24] hover:bg-[#202430] border border-[#272b37] hover:border-emerald-500/50 text-left transition-all cursor-pointer group"
                >
                  <div className="min-w-0 flex-1 pr-2">
                    <div className="text-xs font-medium text-slate-200 group-hover:text-emerald-400 truncate flex items-center gap-1.5">
                      <FileVideo size={13} className="text-emerald-400 flex-shrink-0" />
                      {v.filename}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                      Duration: {v.duration ? `${v.duration.toFixed(1)}s` : 'N/A'} · Status: {v.status}
                    </div>
                  </div>
                  <span className="text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded">
                    Load ANPR
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </>
      ) : (
        /* ── File selected / uploading / analyzing ── */
        <div className="space-y-3">
          {/* File info */}
          <div className="flex items-center gap-3 bg-[#191c24] light:bg-slate-50 border border-[#272b37] light:border-[#d3d8e3] rounded-xl px-3 py-2.5">
            <FileVideo size={18} className="text-emerald-400 light:text-[#15803d] flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold text-white light:text-slate-900 truncate">{file.name}</div>
              <div className="text-[10px] text-[#9aa2b5] light:text-slate-500 font-mono">
                {(file.size / (1024 * 1024)).toFixed(2)} MB
              </div>
            </div>
            {status === 'READY' && (
              <button onClick={reset} className="p-1 hover:text-red-400 transition-colors cursor-pointer">
                <X size={14} className="text-[#62697b] light:text-slate-400" />
              </button>
            )}
            {status === 'COMPLETED' && (
              <CheckCircle2 size={16} className="text-emerald-400 light:text-[#15803d]" />
            )}
          </div>

          {/* Status text & Progress */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                {(status === 'UPLOADING' || status === 'PROCESSING' || status === 'AI_ANALYZING') && (
                  <Loader2 size={13} className="text-emerald-400 light:text-[#15803d] animate-spin" />
                )}
                <span className={
                  status === 'COMPLETED' ? 'text-emerald-400 light:text-[#15803d] font-semibold' :
                  status === 'ERROR'     ? 'text-red-400 light:text-red-600 font-semibold' :
                  'text-white light:text-slate-900 font-semibold'
                }>
                  {STATUS_LABELS[status]}
                </span>
              </div>
              {status !== 'READY' && (
                <span className="font-mono text-[11px] text-[#9aa2b5] light:text-slate-500 font-bold">
                  {currentProgress}%
                </span>
              )}
            </div>

            {/* Progress Bar */}
            {(status === 'UPLOADING' || status === 'PROCESSING' || status === 'AI_ANALYZING') && (
              <div className="w-full h-2 bg-[#272b37] light:bg-slate-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-500 to-green-600 rounded-full transition-all duration-300"
                  style={{ width: `${Math.max(4, currentProgress)}%` }}
                />
              </div>
            )}

            {/* Frame and Detection Metrics Breakdown */}
            {status === 'AI_ANALYZING' && videoAnalysisMetrics && videoAnalysisMetrics.totalFrames > 0 && (
              <div className="grid grid-cols-3 gap-2 pt-1 text-[10px] font-mono text-[#9aa2b5] light:text-slate-600">
                <div className="bg-[#191c24] light:bg-slate-50 p-1.5 rounded-xl border border-[#272b37] light:border-[#d3d8e3] text-center">
                  <div className="text-[#62697b] light:text-slate-400">Frame</div>
                  <div className="text-white light:text-slate-900 font-bold">
                    {videoAnalysisMetrics.currentFrame} / {videoAnalysisMetrics.totalFrames}
                  </div>
                </div>
                <div className="bg-[#191c24] light:bg-slate-50 p-1.5 rounded-xl border border-[#272b37] light:border-[#d3d8e3] text-center">
                  <div className="text-[#62697b] light:text-slate-400">Objects</div>
                  <div className="text-white light:text-slate-900 font-bold">
                    {videoAnalysisMetrics.detections}
                  </div>
                </div>
                <div className="bg-[#191c24] light:bg-slate-50 p-1.5 rounded-xl border border-[#272b37] light:border-[#d3d8e3] text-center">
                  <div className="text-[#62697b] light:text-slate-400">Tracks</div>
                  <div className="text-emerald-400 light:text-[#15803d] font-bold">
                    {videoAnalysisMetrics.tracks}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Error display */}
          {error && (
            <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded p-2">
              <AlertCircle size={14} className="flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Actions */}
          {status === 'READY' && (
            <button onClick={handleUpload} className="ibvap-btn-primary w-full justify-center text-sm cursor-pointer py-2">
              <Upload size={14} /> Upload & Analyze with YOLOv8
            </button>
          )}

          {(status === 'AI_ANALYZING' || status === 'PROCESSING') && (
            <button
              type="button"
              onClick={handleStopAnalysis}
              className="ibvap-btn-danger w-full justify-center text-xs py-1.5 cursor-pointer flex items-center gap-1.5"
            >
              <Square size={12} /> Stop Analysis
            </button>
          )}

          {status === 'COMPLETED' && (
            <button onClick={reset} className="ibvap-btn-ghost w-full justify-center text-sm cursor-pointer py-2 flex items-center gap-1.5">
              <RefreshCw size={13} /> Upload Another Video
            </button>
          )}

          {status === 'ERROR' && (
            <button onClick={reset} className="ibvap-btn-ghost w-full justify-center text-xs py-1.5 cursor-pointer">
              Try Again
            </button>
          )}
        </div>
      )}
    </div>
  );
}

