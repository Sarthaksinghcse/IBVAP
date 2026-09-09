import { NavLink, useLocation } from 'react-router-dom';
import {
  Home, Video, Bell, History, Camera, Map, BarChart2,
  Activity, Settings, UserCheck
} from 'lucide-react';
import { useStore } from '../../store/useStore';

// ─── Nav Items Definition ─────────────────────────────────────────────────────

const NAV_ITEMS = [
  { id: 'dashboard',     path: '/',               label: 'Home',          Icon: Home },
  { id: 'monitoring',    path: '/monitoring',      label: 'Live Monitor',  Icon: Video },
  { id: 'alerts',        path: '/alerts',          label: 'Alerts',        Icon: Bell },
  { id: 'alert-history', path: '/alerts/history',  label: 'Alert History', Icon: History },
  { id: 'watchlist',     path: '/watchlist',       label: 'Watchlist',     Icon: UserCheck },
  { id: 'cameras',       path: '/cameras',         label: 'Cameras',       Icon: Camera },
  { id: 'map',           path: '/map',             label: 'Map',           Icon: Map },
  { id: 'analytics',     path: '/analytics',       label: 'Analytics',     Icon: BarChart2 },
  { id: 'system',        path: '/system',          label: 'System Status', Icon: Activity },
  { id: 'settings',      path: '/settings',        label: 'Settings',      Icon: Settings },
];


// ─── Sidebar Component ─────────────────────────────────────────────────────────

export function Sidebar() {
  const location = useLocation();
  const alerts = useStore((s) => s.alerts);
  const systemStatus = useStore((s) => s.systemStatus);

  const activeAlertsCount = alerts.filter((a) => a.status === 'NEW' || a.status === 'ACKNOWLEDGED').length;
  const isAiRunning = systemStatus.ai_engine_status === 'RUNNING';

  return (
    <aside className="w-56 flex-shrink-0 flex flex-col bg-[#08090c] light:bg-white border-r border-[#272b37] light:border-[#d9dde3] h-screen select-none transition-colors duration-200 sticky top-0">

      {/* ── Brand Header ─────────────────────────────────────────────── */}
      <div className="px-4 py-4 flex items-center gap-3 border-b border-[#272b37] light:border-[#d9dde3]">
        <img
          src="/shield_logo.png"
          alt="SHIELD Logo"
          className="w-8 h-8 object-contain drop-shadow-md flex-shrink-0"
        />
        <div className="min-w-0">
          <div className="text-sm font-extrabold tracking-wider text-white light:text-slate-900 font-mono">
            SHIELD
          </div>
          <div className="text-[9px] text-[#9aa2b5] light:text-slate-500 font-medium leading-tight truncate">
            Intelligent Border Surveillance
          </div>
        </div>
      </div>

      {/* ── Navigation Links ─────────────────────────────────────────── */}
      <nav className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map(({ id, path, label, Icon }) => {
          const isActive =
            path === '/'
              ? location.pathname === '/'
              : location.pathname === path || (path !== '/' && location.pathname.startsWith(path));

          const isAlerts = id === 'alerts';

          return (
            <NavLink
              key={id}
              to={path}
              className={`
                group flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-semibold transition-all duration-150 relative
                ${isActive
                  ? 'bg-[#13271d] text-[#22c55e] border border-[#1b3e2b] light:bg-[#ecfdf5] light:text-[#15803d] light:border-[#86efac] shadow-xs'
                  : 'text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 hover:bg-[#121419] light:hover:bg-slate-100 border border-transparent'
                }
              `}
            >
              <Icon
                size={15}
                className={`flex-shrink-0 transition-colors ${
                  isActive
                    ? 'text-[#22c55e] light:text-[#15803d]'
                    : 'text-[#9aa2b5] light:text-slate-500 group-hover:text-white light:group-hover:text-slate-900'
                }`}
              />
              <span className="flex-1 truncate">{label}</span>

              {isAlerts && activeAlertsCount > 0 && (
                <span className="px-1.5 py-0.2 min-w-[18px] rounded-full bg-red-600 text-white text-[10px] font-bold font-mono text-center shadow-xs">
                  {activeAlertsCount > 99 ? '99+' : activeAlertsCount}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* ── Sidebar Footer / Emblem & AI Status ──────────────────────── */}
      <div className="p-3 border-t border-[#272b37] light:border-[#d9dde3] flex flex-col items-center text-center">
        <img
          src="/shield_logo.png"
          alt="SHIELD"
          className="w-10 h-10 object-contain mb-1 opacity-90 hover:opacity-100 transition-opacity"
        />
        <div className="text-[11px] font-bold font-mono tracking-widest text-white light:text-slate-900">
          SHIELD
        </div>
        <div className="text-[9px] text-[#62697b] light:text-slate-400 font-mono mb-2">
          v2.0.0
        </div>

        {/* AI Engine Status Pill */}
        <div className="w-full flex items-center justify-between px-2.5 py-1 rounded-full bg-[#121419] light:bg-slate-50 border border-[#272b37] light:border-slate-300 text-[10px] font-mono shadow-xs">
          <div className="flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isAiRunning
                  ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)] animate-pulse'
                  : 'bg-red-500'
              }`}
            />
            <span className="text-[#9aa2b5] light:text-slate-700 font-medium text-[9px]">
              AI Engine
            </span>
          </div>
          <span
            className={`text-[8px] font-bold px-1 py-0.2 rounded font-mono ${
              isAiRunning
                ? 'text-emerald-400 bg-emerald-500/10 light:text-emerald-700 light:bg-emerald-100'
                : 'text-red-400 bg-red-500/10 light:text-red-700 light:bg-red-100'
            }`}
          >
            {isAiRunning ? 'RUNNING' : 'STOPPED'}
          </span>
        </div>
      </div>
    </aside>
  );
}

