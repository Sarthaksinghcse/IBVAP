import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell, CheckCheck, Menu,
  Sun, Moon, Globe, Check, MoreVertical, X
} from 'lucide-react';
import { useStore } from '../../store/useStore';
import { formatHeaderClock, formatRelativeTime } from '../../utils/time';

const SUPPORTED_TIMEZONES = [
  { value: 'SYSTEM',            label: 'System Default' },
  { value: 'Asia/Kolkata',       label: 'IST · India (UTC+5:30)' },
  { value: 'UTC',               label: 'UTC · Universal' },
  { value: 'America/New_York',   label: 'EST · New York (UTC-5)' },
  { value: 'America/Los_Angeles',label: 'PST · Los Angeles (UTC-8)' },
  { value: 'Europe/London',      label: 'GMT · London (UTC+0)' },
  { value: 'Asia/Dubai',         label: 'GST · Dubai (UTC+4)' },
  { value: 'Asia/Singapore',     label: 'SGT · Singapore (UTC+8)' },
  { value: 'Asia/Tokyo',         label: 'JST · Tokyo (UTC+9)' },
];

export function TopBar() {
  const navigate = useNavigate();

  // Store state
  const alerts           = useStore((s) => s.alerts);
  const readAlertIds     = useStore((s) => s.readAlertIds);
  const markAlertRead    = useStore((s) => s.markAlertRead);
  const markAllAlertsRead= useStore((s) => s.markAllAlertsRead);
  const setSelectedAlert = useStore((s) => s.setSelectedAlert);

  const timeZone         = useStore((s) => s.timeZone);
  const setTimeZone      = useStore((s) => s.setTimeZone);
  const timeFormat       = useStore((s) => s.timeFormat);
  const setTimeFormat    = useStore((s) => s.setTimeFormat);
  const theme            = useStore((s) => s.theme);
  const setTheme         = useStore((s) => s.setTheme);

  // Local UI State
  const [isNotifOpen, setIsNotifOpen] = useState(false);
  const [isMenuOpen, setIsMenuOpen]   = useState(false);
  const [now, setNow]                 = useState(() => new Date());
  const [tzSearch, setTzSearch]       = useState('');

  const notifRef = useRef<HTMLDivElement>(null);
  const menuRef  = useRef<HTMLDivElement>(null);

  // Real-time ticking clock
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Compute unread alert count
  const unreadAlerts = alerts.filter((a) => !readAlertIds.includes(a.id));
  const unreadCount  = unreadAlerts.length;

  // Close menus on outside click
  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setIsNotifOpen(false);
      }
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  const { dateStr, timeStr } = formatHeaderClock(now, timeZone, timeFormat);

  const filteredTimezones = SUPPORTED_TIMEZONES.filter((t) =>
    t.label.toLowerCase().includes(tzSearch.toLowerCase()) || t.value.toLowerCase().includes(tzSearch.toLowerCase())
  );

  return (
    <header className="flex-shrink-0 flex items-center justify-between px-6 py-3 bg-[#08090c] light:bg-white border-b border-[#272b37] light:border-[#d9dde3] relative z-40 select-none transition-colors duration-200">

      {/* ── Left: Hamburger Menu & Search Bar ─────────────────────── */}
      <div className="flex items-center gap-4 flex-1 max-w-lg">
        <button className="text-[#9aa2b5] light:text-slate-600 hover:text-white light:hover:text-slate-900 p-1.5 rounded-lg transition-colors cursor-pointer">
          <Menu size={18} />
        </button>

        <div className="relative w-full max-w-sm">
          <input
            type="text"
            placeholder="Search cameras, events, alerts..."
            className="w-full bg-[#121419] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] rounded-xl pl-9 pr-3 py-1.5 text-xs text-white light:text-slate-900 placeholder-[#62697b] light:placeholder-slate-400 focus:outline-none focus:border-[#22c55e] transition-all font-sans font-medium"
          />
          <svg
            className="w-3.5 h-3.5 text-[#62697b] light:text-slate-400 absolute left-3 top-2.5 pointer-events-none"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
      </div>

      {/* ── Right: Theme, Format, Bell, Operator Profile & Preferences ── */}
      <div className="flex items-center gap-3">

        {/* Quick Theme Toggle (Sun/Moon) */}
        <div className="flex items-center bg-[#121419] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] rounded-xl p-0.5">
          <button
            type="button"
            onClick={() => setTheme('light')}
            className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
              theme === 'light' ? 'bg-white text-slate-900 shadow-xs' : 'text-[#9aa2b5] light:text-slate-500 hover:text-white light:hover:text-slate-900'
            }`}
            title="Light Theme"
          >
            <Sun size={13} />
          </button>
          <button
            type="button"
            onClick={() => setTheme('dark')}
            className={`p-1.5 rounded-lg transition-colors cursor-pointer ${
              theme === 'dark' || theme === 'system' ? 'bg-[#191c24] text-white shadow-xs' : 'text-[#9aa2b5] light:text-slate-500 hover:text-white light:hover:text-slate-900'
            }`}
            title="Dark Theme"
          >
            <Moon size={13} />
          </button>
        </div>

        {/* 24h / 12h Toggle Button */}
        <button
          type="button"
          onClick={() => setTimeFormat(timeFormat === '24h' ? '12h' : '24h')}
          className="px-2.5 py-1 rounded-xl bg-[#121419] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] text-xs font-mono font-bold text-[#9aa2b5] light:text-slate-700 hover:text-white light:hover:text-slate-900 transition-all cursor-pointer shadow-xs"
          title="Toggle 12h / 24h Clock Format"
        >
          {timeFormat}
        </button>

        {/* ── Notification Bell with Popover ────────────────────────── */}
        <div className="relative" ref={notifRef}>
          <button
            type="button"
            onClick={() => setIsNotifOpen(!isNotifOpen)}
            className={`relative p-2 rounded-xl bg-[#121419] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] transition-colors cursor-pointer ${
              isNotifOpen ? 'bg-[#191c24] text-white' : 'text-[#9aa2b5] light:text-slate-700 hover:text-white light:hover:text-slate-900'
            }`}
            aria-label="Notifications"
          >
            <Bell size={14} />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 min-w-[17px] h-[17px] px-1 rounded-full bg-red-600 text-white text-[9px] font-bold flex items-center justify-center font-mono shadow-sm">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>

          {/* Notification Popover */}
          {isNotifOpen && (
            <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl shadow-2xl overflow-hidden z-50 animate-fadeIn">
              <div className="flex items-center justify-between px-4 py-3 border-b border-[#272b37] light:border-[#d9dde3] bg-[#191c24] light:bg-slate-50">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-white light:text-slate-900">Security Notifications</span>
                  {unreadCount > 0 && (
                    <span className="px-1.5 py-0.2 text-[10px] font-mono font-semibold bg-red-500/20 text-red-400 border border-red-500/30 rounded">
                      {unreadCount} unread
                    </span>
                  )}
                </div>
                {unreadCount > 0 && (
                  <button
                    type="button"
                    onClick={() => markAllAlertsRead()}
                    className="text-[11px] text-[#22c55e] light:text-[#15803d] hover:underline flex items-center gap-1 cursor-pointer font-bold"
                  >
                    <CheckCheck size={13} /> Mark all read
                  </button>
                )}
              </div>

              <div className="max-h-80 overflow-y-auto divide-y divide-[#272b37] light:divide-[#d9dde3]">
                {alerts.length === 0 ? (
                  <div className="py-8 text-center text-[#62697b] light:text-slate-400 text-xs">
                    No security alerts recorded
                  </div>
                ) : (
                  alerts.slice(0, 20).map((alert) => {
                    const isRead = readAlertIds.includes(alert.id);
                    const threatBg =
                      alert.threat_level === 'CRITICAL' ? 'bg-red-500' :
                      alert.threat_level === 'HIGH'     ? 'bg-orange-500' :
                      alert.threat_level === 'MEDIUM'   ? 'bg-yellow-500' :
                      'bg-green-500';

                    return (
                      <div
                        key={alert.id}
                        onClick={() => {
                          markAlertRead(alert.id);
                          setSelectedAlert(alert.id);
                          setIsNotifOpen(false);
                          navigate('/alerts');
                        }}
                        className={`px-4 py-3 hover:bg-white/5 light:hover:bg-slate-50 cursor-pointer transition-colors flex items-start gap-3 ${
                          !isRead ? 'bg-[#191c24]/50 light:bg-slate-100/50' : ''
                        }`}
                      >
                        <span className={`w-2 h-2 rounded-full mt-1 flex-shrink-0 ${threatBg}`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-semibold text-white light:text-slate-900 truncate">
                              {alert.event_type.replace('_', ' ')}
                            </span>
                            <span className="text-[10px] font-mono text-[#9aa2b5] light:text-slate-500 flex-shrink-0">
                              {formatRelativeTime(alert.created_at)}
                            </span>
                          </div>
                          <p className="text-[11px] text-[#9aa2b5] light:text-slate-600 truncate mt-0.5">
                            {alert.camera_id} • {alert.object_id} ({alert.threat_level})
                          </p>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </div>

        {/* Operator Profile Pill */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[#121419] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] shadow-xs">
          <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-slate-700 to-slate-600 light:from-slate-300 light:to-slate-400 border border-slate-500/40 flex items-center justify-center text-[10px] font-bold text-white light:text-slate-800 flex-shrink-0 shadow-inner">
            SO
          </div>
          <div className="hidden sm:block text-left">
            <div className="text-xs font-semibold text-white light:text-slate-900 leading-tight">
              Security Operator
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" />
              <span className="text-[9px] font-mono text-emerald-400 light:text-emerald-700 font-bold">Online</span>
            </div>
          </div>
        </div>

        {/* ── 3-Dot Preferences Menu ─────────────────────────────────── */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className={`p-2 rounded-xl bg-[#121419] light:bg-[#f8fafc] border border-[#272b37] light:border-[#d9dde3] transition-colors cursor-pointer ${
              isMenuOpen ? 'bg-[#191c24] text-white' : 'text-[#9aa2b5] light:text-slate-700 hover:text-white light:hover:text-slate-900'
            }`}
            title="Preferences & Settings"
          >
            <MoreVertical size={14} />
          </button>

          {/* Preferences Dropdown */}
          {isMenuOpen && (
            <div className="absolute right-0 mt-2 w-72 bg-[#121419] light:bg-white border border-[#272b37] light:border-[#d9dde3] rounded-2xl shadow-2xl p-4 z-50 animate-fadeIn space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-[#272b37] light:border-[#d9dde3]">
                <span className="text-xs font-bold text-white light:text-slate-900">System Preferences</span>
                <button onClick={() => setIsMenuOpen(false)} className="text-[#9aa2b5] light:text-slate-500 hover:text-white p-1">
                  <X size={13} />
                </button>
              </div>



              {/* Timezone Selector */}
              <div>
                <label className="text-[10px] font-mono text-[#9aa2b5] light:text-slate-500 uppercase tracking-wider block mb-1.5 flex items-center gap-1">
                  <Globe size={11} className="text-emerald-400" /> Timezone
                </label>
                <input
                  type="text"
                  placeholder="Filter timezone..."
                  value={tzSearch}
                  onChange={(e) => setTzSearch(e.target.value)}
                  className="w-full bg-[#191c24] light:bg-slate-100 border border-[#272b37] light:border-slate-300 rounded-lg px-2.5 py-1 text-xs text-white light:text-slate-900 placeholder-[#62697b] mb-1.5 focus:outline-none focus:border-[#22c55e]"
                />
                <div className="max-h-36 overflow-y-auto space-y-0.5">
                  {filteredTimezones.map((tz) => (
                    <button
                      key={tz.value}
                      type="button"
                      onClick={() => {
                        setTimeZone(tz.value);
                      }}
                      className={`w-full text-left px-2 py-1 rounded-lg text-xs flex items-center justify-between transition-colors ${
                        timeZone === tz.value
                          ? 'bg-[#13271d] text-[#22c55e] light:bg-[#ecfdf5] light:text-[#15803d] font-semibold'
                          : 'text-[#9aa2b5] light:text-slate-600 hover:bg-[#191c24] light:hover:bg-slate-100 hover:text-white'
                      }`}
                    >
                      <span>{tz.label}</span>
                      {timeZone === tz.value && <Check size={12} className="text-[#22c55e] light:text-[#15803d]" />}
                    </button>
                  ))}
                </div>
              </div>

              {/* Live Header Clock Preview */}
              <div className="pt-2 border-t border-[#272b37] light:border-[#d3d8e3] flex items-center justify-between text-[10px] font-mono text-[#9aa2b5] light:text-slate-500">
                <span>Current Time:</span>
                <span className="text-white light:text-slate-900 font-bold">{timeStr} ({dateStr})</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );

}
