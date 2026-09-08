import { useEffect } from 'react';
import { BrowserRouter, HashRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { useWebSocket } from './hooks/useWebSocket';
import { useStore } from './store/useStore';
import Dashboard     from './pages/Dashboard';
import LiveMonitoring from './pages/LiveMonitoring';
import Alerts        from './pages/Alerts';
import AlertHistory  from './pages/AlertHistory';
import Cameras       from './pages/Cameras';
import { Watchlist } from './pages/Watchlist';
import MapPage       from './pages/MapPage';
import Analytics     from './pages/Analytics';
import SystemStatus  from './pages/SystemStatus';
import Settings      from './pages/Settings';

// ─── Detect Electron ─────────────────────────────────────────────────────────

declare global {
  interface Window {
    electronAPI?: {
      isDesktop: boolean;
      showNotification: (title: string, body: string, urgency?: string) => void;
      minimizeToTray: () => void;
      getAppVersion: () => Promise<string>;
      onNavigate: (callback: (route: string) => void) => void;
    };
  }
}

const isElectron = !!(window as any).electronAPI?.isDesktop;

// Choose router based on environment
// Electron uses file:// protocol which doesn't support browser history routing
const Router = isElectron ? HashRouter : BrowserRouter;

// ─── Inner App (needs to be inside Router for hooks) ─────────────────────────

function AppRoutes() {
  // Start WebSocket (or mock engine) — called once at root level
  useWebSocket();
  const theme = useStore((s) => s.theme);
  const navigate = useNavigate();

  useEffect(() => {
    if (theme === 'light') {
      document.documentElement.classList.add('light');
      document.documentElement.classList.remove('dark');
      document.documentElement.setAttribute('data-theme', 'light');
    } else {
      document.documentElement.classList.add('dark');
      document.documentElement.classList.remove('light');
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  }, [theme]);

  // Listen for navigation commands from Electron tray menu
  useEffect(() => {
    if (window.electronAPI?.onNavigate) {
      window.electronAPI.onNavigate((route: string) => {
        navigate(route);
      });
    }
  }, [navigate]);

  return (

    <Routes>
      <Route element={<Layout />}>
        <Route index             element={<Dashboard />} />
        <Route path="monitoring" element={<LiveMonitoring />} />
        <Route path="alerts">
          <Route index          element={<Alerts />} />
          <Route path="history" element={<AlertHistory />} />
        </Route>
        <Route path="watchlist" element={<Watchlist />} />
        <Route path="cameras"   element={<Cameras />} />
        <Route path="map"       element={<MapPage />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="system"    element={<SystemStatus />} />
        <Route path="settings"  element={<Settings />} />
        {/* Fallback */}
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}



// ─── Root App ─────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <Router>
      <AppRoutes />
    </Router>
  );
}
