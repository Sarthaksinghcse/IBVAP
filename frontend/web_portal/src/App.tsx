import { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
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

// ─── Inner App (needs to be inside BrowserRouter for hooks) ──────────────────

function AppRoutes() {
  // Start WebSocket (or mock engine) — called once at root level
  useWebSocket();
  const theme = useStore((s) => s.theme);

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

  return (
    <ErrorBoundary
      fallbackTitle="SHIELD Application Viewport"
      fallbackMessage="An unexpected issue occurred in the primary view. The navigation and background services remain active."
    >
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
    </ErrorBoundary>
  );
}



// ─── Root App ─────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}

