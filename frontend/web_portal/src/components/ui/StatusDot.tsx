import type { CameraStatus, AIStatus } from '../../types';

// ─── Generic Status Dot ───────────────────────────────────────────────────────

type DotVariant = 'online' | 'offline' | 'maintenance' | 'running' | 'stopped' | 'error' | 'connected' | 'idle';

const DOT_CLASS: Record<DotVariant, string> = {
  online:      'status-dot-online',
  offline:     'status-dot-offline',
  maintenance: 'status-dot-maintenance',
  running:     'status-dot-running',
  stopped:     'status-dot-stopped',
  error:       'status-dot-error',
  connected:   'status-dot-online',
  idle:        'status-dot-stopped',
};

interface StatusDotProps {
  variant: DotVariant;
  label?: string;
  size?: 'sm' | 'md';
}

export function StatusDot({ variant, label, size = 'sm' }: StatusDotProps) {
  const sz = size === 'md' ? 'w-2.5 h-2.5' : 'w-2 h-2';
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`status-dot ${sz} ${DOT_CLASS[variant]}`} />
      {label && <span className="text-xs text-slate-400">{label}</span>}
    </span>
  );
}

// ─── Camera Status Dot ────────────────────────────────────────────────────────

export function CameraStatusDot({ status }: { status: CameraStatus }) {
  const map: Record<CameraStatus, DotVariant> = {
    ONLINE: 'online',
    OFFLINE: 'offline',
    MAINTENANCE: 'maintenance',
    ERROR: 'error',
  };
  return <StatusDot variant={map[status]} label={status} />;
}


// ─── AI Status Dot ────────────────────────────────────────────────────────────

export function AIStatusDot({ status }: { status: AIStatus }) {
  const map: Record<AIStatus, DotVariant> = {
    RUNNING: 'running',
    STOPPED: 'stopped',
    ERROR: 'error',
  };
  return <StatusDot variant={map[status]} label={`AI: ${status}`} />;
}

// ─── WebSocket Status Dot ─────────────────────────────────────────────────────

export function WSStatusDot({ connected }: { connected: boolean }) {
  return (
    <StatusDot variant={connected ? 'connected' : 'offline'} label={connected ? 'WS: Connected' : 'WS: Disconnected'} />
  );
}
