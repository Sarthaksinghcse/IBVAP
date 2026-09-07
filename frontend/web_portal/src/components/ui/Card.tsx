import { type ReactNode } from 'react';

// ─── Card ─────────────────────────────────────────────────────────────────────

interface CardProps {
  children: ReactNode;
  className?: string;
  noPadding?: boolean;
}

export function Card({ children, className = '', noPadding = false }: CardProps) {
  return (
    <div className={`ibvap-card ${noPadding ? '' : 'p-4'} ${className}`}>
      {children}
    </div>
  );
}

// ─── Card Header ──────────────────────────────────────────────────────────────

interface CardHeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  icon?: ReactNode;
}

export function CardHeader({ title, subtitle, actions, icon }: CardHeaderProps) {
  return (
    <div className="panel-header border-b border-[#272b37] light:border-[#d1d5db] bg-[#191c24] light:bg-slate-50">
      <div className="flex items-center gap-2">
        {icon && <span className="text-[#1d6af5]">{icon}</span>}
        <div>
          <h3 className="panel-title text-sm font-bold text-white light:text-slate-900">{title}</h3>
          {subtitle && <p className="text-[11px] text-[#9aa2b5] light:text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

// ─── Section Header ────────────────────────────────────────────────────────────

interface SectionHeaderProps {
  title: string;
  subtitle?: string;
}

export function SectionHeader({ title, subtitle }: SectionHeaderProps) {
  return (
    <div className="mb-4">
      <h2 className="text-base font-semibold text-slate-100 light:text-slate-900">{title}</h2>
      {subtitle && <p className="text-sm text-slate-500 light:text-slate-500 mt-0.5">{subtitle}</p>}
    </div>
  );
}

// ─── Empty State ───────────────────────────────────────────────────────────────

interface EmptyStateProps {
  icon?: ReactNode;
  message: string;
  sub?: string;
}

export function EmptyState({ icon, message, sub }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      {icon && <div className="text-slate-600 light:text-slate-400 mb-3 text-3xl">{icon}</div>}
      <p className="text-sm text-slate-400 light:text-slate-700 font-medium">{message}</p>
      {sub && <p className="text-xs text-slate-600 light:text-slate-400 mt-1">{sub}</p>}
    </div>
  );
}

// ─── Divider ──────────────────────────────────────────────────────────────────

export function Divider({ className = '' }: { className?: string }) {
  return <div className={`border-t border-[#1e2d4a] light:border-[#d1d5db] ${className}`} />;
}

// ─── Progress Bar ─────────────────────────────────────────────────────────────

interface ProgressBarProps {
  value: number; // 0–100
  color?: string;
  label?: string;
  showValue?: boolean;
}

export function ProgressBar({ value, color = '#1d6af5', label, showValue = false }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, value));
  const barColor =
    pct > 85 ? '#ef4444' : pct > 65 ? '#f97316' : color;

  return (
    <div className="w-full">
      {(label || showValue) && (
        <div className="flex justify-between mb-1">
          {label && <span className="text-xs text-slate-400 light:text-slate-600">{label}</span>}
          {showValue && <span className="text-xs font-mono text-slate-300 light:text-slate-900">{pct}%</span>}
        </div>
      )}
      <div className="w-full h-1.5 bg-[#1e2d4a] light:bg-slate-200 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: barColor }}
        />
      </div>
    </div>
  );
}

