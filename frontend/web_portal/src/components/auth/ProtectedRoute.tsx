import { Navigate, useLocation } from 'react-router-dom';
import { useStore } from '../../store/useStore';
import { Shield, Loader2 } from 'lucide-react';

interface ProtectedRouteProps {
  children?: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const isAuthenticated = useStore((s) => s.isAuthenticated);
  const isAuthChecking = useStore((s) => s.isAuthChecking);
  const location = useLocation();

  if (isAuthChecking) {
    return (
      <div className="min-h-screen bg-[#0b0d11] flex flex-col items-center justify-center p-4">
        <div className="relative flex items-center justify-center mb-6">
          <div className="w-16 h-16 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center shadow-[0_0_25px_rgba(6,182,212,0.15)] animate-pulse">
            <Shield className="w-8 h-8 text-cyan-400" />
          </div>
          <Loader2 className="absolute w-20 h-20 text-cyan-400/40 animate-spin" />
        </div>
        <div className="text-center font-mono">
          <p className="text-white text-sm font-semibold tracking-wider uppercase mb-1">
            IBVAP Neural Shield
          </p>
          <p className="text-xs text-slate-400 tracking-wide">
            Validating Biometric Operator Session...
          </p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return children ? <>{children}</> : null;
}
