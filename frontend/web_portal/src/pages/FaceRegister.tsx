import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import {
  Shield, Camera, CheckCircle2, AlertTriangle, ArrowRight,
  RefreshCw, User, Mail, ShieldAlert, Sparkles, Lock, Eye
} from 'lucide-react';
import { useWebcamCapture } from '../hooks/useWebcamCapture';
import { registerFaceWebcam } from '../services/api';
import { useStore } from '../store/useStore';

export default function FaceRegister() {
  const navigate = useNavigate();
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

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'operator' | 'admin' | 'viewer'>('operator');

  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successData, setSuccessData] = useState<{ name: string; role: string } | null>(null);

  useEffect(() => {
    startStream();
    return () => {
      stopStream();
    };
  }, [startStream, stopStream]);

  const handleCapture = () => {
    setErrorMessage(null);
    const frame = captureFrame();
    if (!frame) {
      setErrorMessage('Could not capture frame. Please ensure your camera is running and visible.');
      return;
    }
    setCapturedImage(frame);
  };

  const handleRetake = () => {
    setCapturedImage(null);
    setErrorMessage(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!name.trim()) {
      setErrorMessage('Please enter your full name.');
      return;
    }

    if (!capturedImage) {
      setErrorMessage('Please capture your facial photo using the camera before registering.');
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await registerFaceWebcam({
        name: name.trim(),
        email: email.trim() || undefined,
        role,
        image_base64: capturedImage,
      });

      setSuccessData({ name: res.name, role: res.role });
      login(res.token, {
        user_id: res.user_id,
        name: res.name,
        email: res.email,
        role: res.role,
        photo_url: res.photo_url,
      });

      // Brief delay for success animation before navigating
      setTimeout(() => {
        navigate('/');
      }, 1200);
    } catch (err: any) {
      console.error('[FaceRegister] Error:', err);
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409) {
        setErrorMessage(detail || 'This face is already enrolled under another operator profile.');
      } else if (err.response?.status === 400) {
        setErrorMessage(detail || 'Facial validation failed. Please face the camera directly with good lighting.');
      } else {
        setErrorMessage(detail || 'Failed to complete registration. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#07090d] text-slate-100 flex flex-col justify-between relative overflow-hidden font-sans select-none">
      {/* Background cybernetic grid effects */}
      <div className="absolute inset-0 pointer-events-none opacity-20 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:24px_24px]" />
      <div className="absolute top-0 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-[128px] pointer-events-none" />
      <div className="absolute bottom-0 left-1/4 w-96 h-96 bg-blue-600/10 rounded-full blur-[128px] pointer-events-none" />

      {/* Header */}
      <header className="relative z-10 border-b border-slate-800/80 bg-[#0c1017]/80 backdrop-blur-md px-6 py-4 flex items-center justify-between">
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
          to="/login"
          className="flex items-center gap-2 text-xs text-cyan-400 hover:text-cyan-300 font-mono tracking-wide px-3 py-1.5 rounded-lg border border-cyan-500/30 hover:border-cyan-400/50 bg-cyan-500/5 hover:bg-cyan-500/10 transition-all"
        >
          <span>Already enrolled? Face Login</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </header>

      {/* Main Content */}
      <main className="relative z-10 max-w-5xl mx-auto w-full px-4 py-8 my-auto">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          
          {/* Left: Camera & Biometric Viewfinder */}
          <div className="lg:col-span-7 flex flex-col items-center">
            <div className="w-full bg-[#0d121c] border border-slate-800 rounded-2xl p-5 shadow-2xl backdrop-blur-xl relative overflow-hidden">
              <div className="flex items-center justify-between mb-3 font-mono text-xs text-slate-400">
                <span className="flex items-center gap-1.5 text-cyan-400 font-medium">
                  <Eye className="w-3.5 h-3.5 animate-pulse" />
                  BIOMETRIC SENSOR STREAM
                </span>
                <span className="flex items-center gap-1 text-[11px] text-emerald-400">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                  {isReady ? 'CAMERA ONLINE' : isCameraLoading ? 'STARTING SENSOR...' : 'STANDBY'}
                </span>
              </div>

              {/* Viewport Frame */}
              <div className="relative aspect-[4/3] w-full rounded-xl overflow-hidden bg-black border border-slate-700/80 shadow-inner flex items-center justify-center">
                {capturedImage ? (
                  <img
                    src={capturedImage}
                    alt="Enrolled Face Capture"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="w-full h-full object-cover mirror-mode"
                    style={{ transform: 'scaleX(-1)' }}
                  />
                )}

                {/* Reticle Overlay when stream is live and not frozen */}
                {!capturedImage && isReady && (
                  <div className="absolute inset-0 pointer-events-none flex flex-col items-center justify-center">
                    {/* Face target guide oval */}
                    <div className="w-48 h-64 border-2 border-dashed border-cyan-400/50 rounded-[50%] flex items-center justify-center relative shadow-[0_0_20px_rgba(6,182,212,0.2)]">
                      <div className="w-3 h-3 border-t-2 border-l-2 border-cyan-400 absolute -top-1 -left-1" />
                      <div className="w-3 h-3 border-t-2 border-r-2 border-cyan-400 absolute -top-1 -right-1" />
                      <div className="w-3 h-3 border-b-2 border-l-2 border-cyan-400 absolute -bottom-1 -left-1" />
                      <div className="w-3 h-3 border-b-2 border-r-2 border-cyan-400 absolute -bottom-1 -right-1" />

                      {/* Center reticle crosshair */}
                      <div className="w-4 h-0.5 bg-cyan-400/60" />
                      <div className="h-4 w-0.5 bg-cyan-400/60 absolute" />
                    </div>

                    <div className="absolute bottom-4 bg-black/60 backdrop-blur-md px-3 py-1 rounded-full border border-cyan-500/30 text-[11px] font-mono text-cyan-300">
                      Center your face inside the target frame
                    </div>
                  </div>
                )}

                {/* Error overlay */}
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

              {/* Viewport Control Buttons */}
              <div className="mt-4 flex items-center gap-3">
                {!capturedImage ? (
                  <button
                    type="button"
                    onClick={handleCapture}
                    disabled={!isReady}
                    className="w-full py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-mono text-xs font-bold rounded-xl shadow-[0_0_20px_rgba(6,182,212,0.25)] flex items-center justify-center gap-2 transition-all"
                  >
                    <Camera className="w-4 h-4" />
                    CAPTURE BIOMETRIC SAMPLE
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleRetake}
                    className="w-full py-3 bg-slate-800 hover:bg-slate-700 text-slate-200 font-mono text-xs font-semibold rounded-xl border border-slate-700 flex items-center justify-center gap-2 transition-all"
                  >
                    <RefreshCw className="w-4 h-4 text-cyan-400" />
                    RETAKE FACIAL SCAN
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Right: Operator Identity Form */}
          <div className="lg:col-span-5">
            <div className="bg-[#0d121c] border border-slate-800 rounded-2xl p-6 shadow-2xl backdrop-blur-xl">
              <div className="mb-6">
                <h1 className="text-lg font-bold text-white tracking-wide flex items-center gap-2">
                  <span>Operator Enrollment</span>
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                </h1>
                <p className="text-xs text-slate-400 mt-1">
                  Enrolls your 128-D facial feature signature as passwordless login credential.
                </p>
              </div>

              {errorMessage && (
                <div className="mb-5 p-3.5 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-start gap-2.5">
                  <ShieldAlert className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div className="leading-relaxed">{errorMessage}</div>
                </div>
              )}

              {successData && (
                <div className="mb-5 p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs flex items-center gap-3 animate-fade-in">
                  <CheckCircle2 className="w-5 h-5 flex-shrink-0" />
                  <div>
                    <p className="font-bold text-emerald-300">Biometric Credentials Enrolled!</p>
                    <p className="text-[11px] text-emerald-400/80">Welcome, {successData.name}. Launching command station...</p>
                  </div>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                {/* Full Name */}
                <div>
                  <label className="block text-xs font-mono font-medium text-slate-300 mb-1.5">
                    Operator Full Name <span className="text-red-400">*</span>
                  </label>
                  <div className="relative">
                    <User className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Inspector Ramesh Rao"
                      required
                      className="w-full bg-[#131924] border border-slate-700/80 rounded-xl pl-9 pr-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 transition-all font-mono"
                    />
                  </div>
                </div>

                {/* Email Address */}
                <div>
                  <label className="block text-xs font-mono font-medium text-slate-300 mb-1.5">
                    Security Official Email (Optional)
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="ramesh.rao@border.security.gov.in"
                      className="w-full bg-[#131924] border border-slate-700/80 rounded-xl pl-9 pr-3.5 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/50 transition-all font-mono"
                    />
                  </div>
                </div>

                {/* Role Selection */}
                <div>
                  <label className="block text-xs font-mono font-medium text-slate-300 mb-1.5">
                    Operational Privilege Level
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {(['operator', 'admin', 'viewer'] as const).map((r) => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => setRole(r)}
                        className={`py-2 px-2.5 rounded-lg border text-center font-mono text-[11px] capitalize transition-all ${
                          role === r
                            ? 'bg-cyan-500/15 border-cyan-400 text-cyan-300 font-bold shadow-[0_0_10px_rgba(6,182,212,0.15)]'
                            : 'bg-[#131924] border-slate-700 text-slate-400 hover:border-slate-600'
                        }`}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Biometric Requirements Checklist */}
                <div className="bg-[#131924] border border-slate-800 rounded-xl p-3.5 space-y-2 text-[11px] text-slate-400 font-mono">
                  <div className="flex items-center gap-2">
                    <div className={`w-1.5 h-1.5 rounded-full ${capturedImage ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                    <span>Facial sample captured from sensor</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <span>OpenCV SFace 128-D embedding representation</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <span>Cross-operator uniqueness check (no duplicates)</span>
                  </div>
                </div>

                {/* Submit button */}
                <button
                  type="submit"
                  disabled={isSubmitting || !capturedImage || !name.trim()}
                  className="w-full mt-2 py-3 bg-gradient-to-r from-emerald-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-mono text-xs font-bold tracking-wider uppercase rounded-xl shadow-[0_0_20px_rgba(16,185,129,0.2)] flex items-center justify-center gap-2 transition-all"
                >
                  {isSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      ANALYZING & ENROLLING BIOMETRICS...
                    </>
                  ) : (
                    <>
                      <Lock className="w-4 h-4" />
                      CONFIRM & ENROLL OPERATOR
                    </>
                  )}
                </button>
              </form>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-slate-800/60 py-3 text-center text-slate-500 text-[11px] font-mono">
        IBVAP Secure Terminal · OpenCV YuNet 2023 & SFace Engine · Zero-Password Policy
      </footer>
    </div>
  );
}
