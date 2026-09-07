import type { ReactNode } from 'react';
import type { ThreatLevel } from '../../types';

interface KPICardProps {
  label: string;
  value: string | number;
  sub?: string;
  icon: ReactNode;
  iconBg?: string;
  accent?: ThreatLevel | 'blue' | 'green' | 'slate';
  trend?: { value: number; label: string };
}

const ACCENT_COLORS = {
  CRITICAL: { text: 'text-red-400 light:text-red-600',    bg: 'bg-red-500/10 light:bg-red-50',    border: 'border-red-500/20 light:border-red-200',    num: 'text-red-300 light:text-red-700' },
  HIGH:     { text: 'text-orange-400 light:text-orange-600', bg: 'bg-orange-500/10 light:bg-orange-50', border: 'border-orange-500/20 light:border-orange-200', num: 'text-orange-300 light:text-orange-700' },
  MEDIUM:   { text: 'text-yellow-400 light:text-yellow-600', bg: 'bg-yellow-500/10 light:bg-yellow-50', border: 'border-yellow-500/20 light:border-yellow-200', num: 'text-yellow-300 light:text-yellow-700' },
  LOW:      { text: 'text-green-400 light:text-[#15803d]',  bg: 'bg-green-500/10 light:bg-emerald-50',  border: 'border-green-500/20 light:border-emerald-200',  num: 'text-green-300 light:text-[#15803d]' },
  NONE:     { text: 'text-slate-400 light:text-slate-600',  bg: 'bg-slate-500/10 light:bg-slate-100',  border: 'border-slate-500/20 light:border-slate-200',  num: 'text-slate-300 light:text-slate-900' },
  blue:     { text: 'text-blue-400 light:text-blue-600',   bg: 'bg-blue-500/10 light:bg-blue-50',   border: 'border-blue-500/20 light:border-blue-200',   num: 'text-blue-300 light:text-blue-800' },
  green:    { text: 'text-green-400 light:text-[#15803d]',  bg: 'bg-green-500/10 light:bg-emerald-50',  border: 'border-green-500/20 light:border-emerald-200',  num: 'text-green-300 light:text-[#15803d]' },
  slate:    { text: 'text-slate-400 light:text-slate-600',  bg: 'bg-slate-500/10 light:bg-slate-100',  border: 'border-slate-500/20 light:border-slate-200',  num: 'text-slate-300 light:text-slate-900' },
};

export function KPICard({ label, value, sub, icon, accent = 'blue', trend }: KPICardProps) {
  const c = ACCENT_COLORS[accent];

  return (
    <div className={`ibvap-card p-4 flex flex-col gap-3 hover:border-[#253a5e] light:hover:border-slate-400 transition-all duration-200 ${c.border}`}>
      {/* Top row: value + icon */}
      <div className="flex items-start justify-between">
        <div>
          <div className={`text-3xl font-bold font-mono tracking-tight leading-none ${c.num}`}>
            {String(value).padStart(2, '0')}
          </div>
          <div className="text-xs font-medium text-slate-300 light:text-slate-700 mt-1.5">{label}</div>
        </div>

        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${c.bg}`}>
          <span className={c.text}>{icon}</span>
        </div>
      </div>

      {/* Bottom: sub-label + optional trend */}
      <div className="flex items-center justify-between">
        {sub && (
          <span className="text-[10px] text-slate-500 light:text-slate-500 font-medium uppercase tracking-wide">{sub}</span>
        )}
        {trend && (
          <span className={`text-[10px] font-mono ${trend.value > 0 ? 'text-red-400 light:text-red-600' : 'text-green-400 light:text-[#15803d]'}`}>
            {trend.value > 0 ? '↑' : '↓'} {Math.abs(trend.value)} {trend.label}
          </span>
        )}
      </div>
    </div>
  );
}

