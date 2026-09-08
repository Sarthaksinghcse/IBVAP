import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import {
  Shield, Camera, CheckCircle2, AlertTriangle, ArrowRight,
  RefreshCw, Scan, Lock, ShieldCheck, UserPlus, Zap
} from 'lucide-react';
import { useWebcamCapture } from '../hooks/useWebcamCapture';
import { loginFaceWebcam } from '../services/api';
import { useStore } from '../store/useStore';

export default function FaceLogin() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useStore((s) => s.login);

  const {
    videoRef,
    isReady,
    isLoading: isCameraLoading,
    error: cameraError,
    startStream,
    stopStream,
    captureFrame,
  } = useWebcamCapture();

  const [isScanning, setIsScanning] = useState(false);
  const [autoScan, setAutoScan] = useState(true);
  const [authStatus, setAuthStatus] = useState<'idle' | 'scanning' | 'success' | 'failed'>('idle');
  const [statusMessage, setStatusMessage] = useState('Position your face in the center of the frame');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [matchedUser, setMatchedUser] = useState<{ name: string; role: string; confidence?: number | null } | null>(null);

  const autoScanTimerRef = useRef<any>(null);
  const inFlightRef = useRef(false);

  // Start webcam on mount
  useEffect(() => {
    startStream();
    return () => {
      stopStream();
      if (autoScanTimerRef.current) clearInterval(autoScanTimerRef.current);
    };
  }, [startStream, stopStream]);

  // Execute authentication attempt
  const executeScan = useCallback(async () => {
    if (inFlightRef.current || !isReady) return;

    const frame = captureFrame();
    if (!frame) return;

    inFlightRef.current = true;
    setIsScanning(true);
    setAuthStatus('scanning');
    setStatusMessage('Scanning biometric landmarks & extracting 128-D signature...');
    setErrorMessage(null);

    try {
      const res = await loginFaceWebcam({ image_base64: frame });

      // Match confirmed
      setAuthStatus('success');
      setStatusMessage(`Access Granted. Welcome back, ${res.name}!`);
      setMatchedUser({
        name: res.name,
        role: res.role,
        confidence: res.confidence,
      });

      login(res.token, {
        user_id: res.user_id,
        name: res.name,
        email: res.email,
        role: res.role,
        photo_url: res.photo_url,
      });

      // Redirect to previous target or dashboard
      setTimeout(() => {
        const from = (location.state as any)?.from?.pathname || '/';
        navigate(from, { replace: true });
      }, 1000);

    } catch (err: any) {
      console.warn('[FaceLogin] Auth attempt rejected:', err);
      const detail = err.response?.data?.detail;

      if (err.response?.status === 401) {
        setAuthStatus('failed');
        setStatusMessage('Face not recognized in registry.');
        setErrorMessage(detail || 'Face not recognized. Access denied.');
      } else if (err.response?.status === 400) {
        setAuthStatus('idle');
        setStatusMessage(detail || 'No clear face detected. Please face the camera.');
      } else {
        setAuthStatus('failed');
        setErrorMessage(detail || 'Authentication server unreachable.');
      }
    } finally {
      setIsScanning(false);
      inFlightRef.current = false;
    }
  }, [captureFrame, isReady, login, location.state, navigate]);

  // Auto-scan loop
  useEffect(() => {
    if (!autoScan || !isReady || authStatus === 'success') {
      if (autoScanTimerRef.current) clearInterval(autoScanTimerRef.current);
      return;
    }

    autoScanTimerRef.current = setInterval(() => {
      if (!inFlightRef.current && isReady) {
        executeScan();
      }
    }, 2400);

    return () => {
      if (autoScanTimerRef.current) clearInterval(autoScanTimerRef.current);
    };
  }, [autoScan, isReady, authStatus, executeScan]);

  return (
    <div className="min-h-screen bg-[#06080d] text-slate-100 flex flex-col justify-between relative overflow-hidden font-sans select-none">
      {/* Dynamic ambient cyber glow */}
      <div className="absolute inset-0 pointer-events-none opacity-25 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px]" />
      <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-cyan-500/15 rounded-full blur-[140px] pointer-events-none" />

      {/* Header */}
      <header className="relative z-10 border-b border-slate-800/80 bg-[#0b0f17]/70 backdrop-blur-md px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/20 border border-cyan-500/40 flex items-center justify-center shadow-[0_0_15px_rgba(6,182,212,0.2)]">
            <Shield className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold tracking-wider text-sm text-white">IBVAP SHIELD</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                BIOMETRIC AUTH
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono">Integrated Border Video Analytics Platform</p>
          </div>
        </div>

        <Link
          to="/register"
          className="flex items-center gap-2 text-xs text-cyan-400 hover:text-cyan-300 font-mono tracking-wide px-3 py-1.5 rounded-lg border border-cyan-500/30 hover:border-cyan-400/50 bg-cyan-500/5 hover:bg-cyan-500/10 transition-all"
        >
          <UserPlus className="w-3.5 h-3.5" />
          <span>New Operator Enrollment</span>
        </Link>
      </header>

      {/* Main Terminal */}
      <main className="relative z-10 max-w-lg mx-auto w-full px-4 py-8 my-auto flex flex-col items-center">
        
        {/* Terminal Header Info */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 text-xs font-mono mb-2">
            <Lock className="w-3 h-3" />
            <span>PASSWORDLESS FACIAL ACCESS TERMINAL</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Operator Authentication</h1>
          <p className="text-xs text-slate-400 font-mono mt-1">
            Present your face to the camera for instant identity verification.
          </p>
        </div>

        {/* Biometric Viewfinder Card */}
        <div className="w-full bg-[#0c111b] border border-slate-800 rounded-3xl p-5 shadow-2xl backdrop-blur-xl relative overflow-hidden">
          
          {/* Top Status Banner */}
          <div className="flex items-center justify-between mb-3 font-mono text-xs">
            <span className="flex items-center gap-1.5 text-cyan-400 font-medium">
              <Scan className={`w-3.5 h-3.5 ${isScanning ? 'animate-spin text-cyan-300' : ''}`} />
              SFace 128-D Biometric Scanner
            </span>
            <span className="flex items-center gap-1 text-[11px]">
              <span className={`w-2 h-2 rounded-full ${
                authStatus === 'success'
                  ? 'bg-emerald-400'
                  : authStatus === 'failed'
                  ? 'bg-red-400'
                  : isReady
                  ? 'bg-cyan-400 animate-pulse'
                  : 'bg-amber-400'
              }`} />
              <span className={
                authStatus === 'success'
                  ? 'text-emerald-400 font-bold'
                  : authStatus === 'failed'
                  ? 'text-red-400'
                  : 'text-slate-400'
              }>
                {authStatus === 'success' ? 'ACCESS GRANTED' : authStatus === 'failed' ? 'ACCESS DENIED' : isReady ? 'READY' : 'STANDBY'}
              </span>
            </span>
          </div>

          {/* Viewport Frame */}
          <div className={`relative aspect-[4/3] w-full rounded-2xl overflow-hidden bg-black border transition-all duration-300 shadow-inner flex items-center justify-center ${
            authStatus === 'success'
              ? 'border-emerald-500 shadow-[0_0_30px_rgba(16,185,129,0.3)]'
              : authStatus === 'failed'
              ? 'border-red-500 shadow-[0_0_30px_rgba(239,68,68,0.25)]'
              : 'border-slate-700/80'
          }`}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full h-full object-cover mirror-mode"
              style={{ transform: 'scaleX(-1)' }}
            />

            {/* Futuristic Reticle & Scanner Line */}
            {isReady && authStatus !== 'success' && (
              <div className="absolute inset-0 pointer-events-none flex flex-col items-center justify-center">
                {/* Facial alignment oval */}
                <div className="w-52 h-68 border-2 border-dashed border-cyan-400/40 rounded-[50%] flex items-center justify-center relative shadow-[0_0_25px_rgba(6,182,212,0.15)]">
                  <div className="w-3.5 h-3.5 border-t-2 border-l-2 border-cyan-400 absolute -top-1 -left-1" />
                  <div className="w-3.5 h-3.5 border-t-2 border-r-2 border-cyan-400 absolute -top-1 -right-1" />
                  <div className="w-3.5 h-3.5 border-b-2 border-l-2 border-cyan-400 absolute -bottom-1 -left-1" />
                  <div className="w-3.5 h-3.5 border-b-2 border-r-2 border-cyan-400 absolute -bottom-1 -right-1" />

                  {/* Horizontal scanning laser sweep */}
                  <div className="absolute inset-x-0 h-0.5 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_12px_rgba(6,182,212,0.9)] animate-pulse"
                       style={{ animation: 'bounce 2.5s infinite alternate' }} />
                </div>
              </div>
            )}

            {/* Success Overlay */}
            {authStatus === 'success' && matchedUser && (
              <div className="absolute inset-0 bg-[#06140e]/85 backdrop-blur-md flex flex-col items-center justify-center p-6 text-center animate-fade-in">
                <div className="w-16 h-16 rounded-full bg-emerald-500/20 border-2 border-emerald-400 flex items-center justify-center mb-3 shadow-[0_0_25px_rgba(16,185,129,0.4)]">
                  <CheckCircle2 className="w-9 h-9 text-emerald-400" />
                </div>
                <p className="text-xs font-mono uppercase tracking-widest text-emerald-400 font-bold mb-1">
                  Identity Verified
                </p>
                <h2 className="text-xl font-bold text-white mb-1">{matchedUser.name}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono text-[10px] uppercase font-bold border border-emerald-500/40">
                    {matchedUser.role}
                  </span>
                  {matchedUser.confidence && (
                    <span className="text-[11px] font-mono text-emerald-400">
                      {matchedUser.confidence}% Match
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 font-mono mt-4">
                  Entering command station...
                </p>
              </div>
            )}

            {/* Error Overlay */}
            {cameraError && (
              <div className="absolute inset-0 bg-slate-900/90 flex flex-col items-center justify-center p-6 text-center">
                <AlertTriangle className="w-10 h-10 text-amber-400 mb-2" />
                <p className="text-sm font-medium text-white mb-1">Camera Sensor Unavailable</p>
                <p className="text-xs text-slate-400 max-w-xs mb-4">{cameraError}</p>
                <button
                  type="button"
                  onClick={() => startStream()}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-xs font-mono text-white rounded-lg border border-slate-600 flex items-center gap-2"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Retry Camera
                </button>
              </div>
            )}
          </div>

          {/* Status Message Display */}
          <div className="mt-3 text-center">
            <p className={`text-xs font-mono transition-colors ${
              authStatus === 'success'
                ? 'text-emerald-400 font-semibold'
                : authStatus === 'failed'
                ? 'text-red-400 font-semibold'
                : 'text-slate-400'
            }`}>
              {statusMessage}
            </p>
            {errorMessage && (
              <p className="text-[11px] text-red-400/90 font-mono mt-1">
                {errorMessage}
              </p>
            )}
          </div>

          {/* Controls */}
          <div className="mt-4 space-y-3">
            <button
              type="button"
              onClick={executeScan}
              disabled={!isReady || isScanning || authStatus === 'success'}
              className="w-full py-3.5 bg-gradient-to-r from-cyan-600 via-blue-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-mono text-xs font-bold tracking-wider uppercase rounded-xl shadow-[0_0_25px_rgba(6,182,212,0.3)] flex items-center justify-center gap-2 transition-all"
            >
              {isScanning ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  AUTHENTICATING FACE...
                </>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4" />
                  SCAN FACE TO LOGIN
                </>
              )}
            </button>

            {/* Auto-Scan Toggle Switch */}
            <div className="flex items-center justify-between px-3 py-2 bg-[#121824] rounded-xl border border-slate-800 text-xs font-mono">
              <span className="flex items-center gap-1.5 text-slate-400">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                Auto-Scan Sensor
              </span>
              <button
                type="button"
                onClick={() => setAutoScan(!autoScan)}
                className={`w-10 h-5 flex items-center rounded-full p-0.5 transition-colors ${
                  autoScan ? 'bg-cyan-500 justify-end' : 'bg-slate-700 justify-start'
                }`}
              >
                <div className="w-4 h-4 rounded-full bg-white shadow-sm" />
              </button>
            </div>
          </div>
        </div>

        {/* Enrollment link */}
        <div className="mt-6 text-center font-mono text-xs text-slate-400">
          <span>First time accessing this border station? </span>
          <Link to="/register" className="text-cyan-400 hover:text-cyan-300 font-semibold underline underline-offset-4">
            Register your face here →
          </Link>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-slate-800/60 py-3 text-center text-slate-500 text-[11px] font-mono">
        IBVAP Biometric Gateway · Powered by OpenCV YuNet & SFace Neural Engine
      </footer>
    </div>
  );
}
