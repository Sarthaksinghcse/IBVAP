// ─── IBVAP Desktop — Preload Script ──────────────────────────────────────────
// Exposes a safe bridge between Electron main process and the React renderer.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // ─── Identity ────────────────────────────────────────────────────────────
  isDesktop: true,

  // ─── App Info ────────────────────────────────────────────────────────────
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  // ─── Native Notifications ───────────────────────────────────────────────
  showNotification: (title, body, urgency = 'normal') => {
    ipcRenderer.send('show-notification', { title, body, urgency });
  },

  // ─── Window Controls ────────────────────────────────────────────────────
  minimizeToTray: () => {
    ipcRenderer.send('minimize-to-tray');
  },

  // ─── Navigation (from tray menu) ────────────────────────────────────────
  onNavigate: (callback) => {
    ipcRenderer.on('navigate', (_, route) => callback(route));
  },

  // ─── Intrusion & Threat Reporting (Supabase Cloud Sync) ─────────────────
  reportZoneBreach: (data) => ipcRenderer.invoke('report-zone-breach', data),
  reportLoitering: (data) => ipcRenderer.invoke('report-loitering', data),
  reportFaceMatch: (data) => ipcRenderer.invoke('report-face-match', data),
});
