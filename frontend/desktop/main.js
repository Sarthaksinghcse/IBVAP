// ─── IBVAP Desktop — Electron Main Process ──────────────────────────────────
// Spawns the FastAPI backend, shows a splash screen, then loads the React app.

const { app, BrowserWindow, Tray, Menu, nativeImage, Notification, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');
const fs = require('fs');
const { reportZoneBreach, reportLoitering, reportFaceMatch, isConfigured } = require('./intrusion-reporter');

// ─── Paths ───────────────────────────────────────────────────────────────────

const isDev = !app.isPackaged;

const BACKEND_DIR = isDev
  ? path.join(__dirname, '..', '..', 'backend')
  : path.join(process.resourcesPath, 'backend');

const FRONTEND_DIR = isDev
  ? path.join(__dirname, '..', 'web_portal', 'dist')
  : path.join(process.resourcesPath, 'app');

const STORAGE_DIR = isDev
  ? path.join(__dirname, '..', '..', 'storage')
  : path.join(process.resourcesPath, 'storage');

const ICON_PATH = (() => {
  const candidates = [
    path.join(process.resourcesPath, 'icon.ico'),
    path.join(process.resourcesPath, '..', 'icon.ico'),
    path.join(__dirname, 'icon.ico'),
    path.join(__dirname, '..', 'icon.ico'),
    path.join(__dirname, '..', '..', 'frontend', 'desktop', 'icon.ico'),
    'C:\\Users\\thaku\\OneDrive\\Desktop\\IBVAP\\frontend\\desktop\\icon.ico'
  ];
  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return c;
    } catch {}
  }
  return path.join(__dirname, 'icon.ico');
})();

const BACKEND_PORT = 8000;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
const DEV_URL = 'http://localhost:5173';

// ─── State ───────────────────────────────────────────────────────────────────

let mainWindow = null;
let splashWindow = null;
let tray = null;
let backendProcess = null;
let isQuitting = false;

// ─── Splash Screen ──────────────────────────────────────────────────────────

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 480,
    height: 360,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
  splashWindow.center();
}

// ─── Main Window ─────────────────────────────────────────────────────────────

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    title: 'SHIELD — Intelligent Border Surveillance Platform',
    icon: ICON_PATH,
    show: false,
    backgroundColor: '#0a0e1a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  const indexPath = path.join(FRONTEND_DIR, 'index.html');

  const showAndCloseSplash = () => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    }
  };

  // Show window when ready
  mainWindow.once('ready-to-show', showAndCloseSplash);

  // Failsafe in case ready-to-show takes too long
  setTimeout(showAndCloseSplash, 3500);

  // Fallback if URL load fails
  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    console.warn(`[IBVAP] Load failed: ${validatedURL} (${errorDescription})`);
    if (fs.existsSync(indexPath) && !validatedURL.startsWith('file://')) {
      console.log(`[IBVAP] Falling back to local bundle: ${indexPath}`);
      mainWindow.loadFile(indexPath);
    }
  });

  // Decide whether to load dev server or prebuilt bundle
  if (isDev) {
    const testDev = http.get(DEV_URL, (res) => {
      res.resume();
      if (res.statusCode === 200) {
        console.log(`[IBVAP] Loading Vite dev server: ${DEV_URL}`);
        mainWindow.loadURL(DEV_URL);
        mainWindow.webContents.openDevTools({ mode: 'detach' });
      } else if (fs.existsSync(indexPath)) {
        console.log(`[IBVAP] Loading prebuilt bundle: ${indexPath}`);
        mainWindow.loadFile(indexPath);
      } else {
        mainWindow.loadURL(DEV_URL);
      }
    });

    testDev.on('error', () => {
      if (fs.existsSync(indexPath)) {
        console.log(`[IBVAP] Vite server not running. Loading prebuilt bundle: ${indexPath}`);
        mainWindow.loadFile(indexPath);
      } else {
        console.log(`[IBVAP] Loading Vite dev server: ${DEV_URL}`);
        mainWindow.loadURL(DEV_URL);
      }
    });

    testDev.setTimeout(1000, () => {
      testDev.destroy();
      if (fs.existsSync(indexPath)) {
        mainWindow.loadFile(indexPath);
      } else {
        mainWindow.loadURL(DEV_URL);
      }
    });
  } else {
    mainWindow.loadFile(indexPath);
  }

  // Minimize to tray instead of closing
  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
      if (tray) {
        tray.displayBalloon({
          iconType: 'info',
          title: 'SHIELD',
          content: 'Application minimized to system tray. Right-click to quit.',
        });
      }
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ─── System Tray ─────────────────────────────────────────────────────────────

function createTray() {
  try {
    if (!fs.existsSync(ICON_PATH)) {
      console.warn('[IBVAP] Tray icon file not found at:', ICON_PATH);
      return;
    }
    const icon = nativeImage.createFromPath(ICON_PATH);
    if (icon.isEmpty()) {
      console.warn('[IBVAP] Tray icon is empty or invalid format');
      return;
    }

    tray = new Tray(icon.resize({ width: 16, height: 16 }));

    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'Open SHIELD',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
          }
        },
      },
      { type: 'separator' },
      {
        label: 'Dashboard',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
            mainWindow.webContents.send('navigate', '/');
          }
        },
      },
      {
        label: 'Alerts',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
            mainWindow.webContents.send('navigate', '/alerts');
          }
        },
      },
      { type: 'separator' },
      {
        label: 'API Docs',
        click: () => {
          shell.openExternal(`${BACKEND_URL}/docs`);
        },
      },
      { type: 'separator' },
      {
        label: 'Quit SHIELD',
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ]);

    tray.setToolTip('SHIELD — Intelligent Border Surveillance Platform');
    tray.setContextMenu(contextMenu);

    tray.on('double-click', () => {
      if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
      }
    });
  } catch (err) {
    console.warn('[IBVAP] Unable to create system tray:', err.message);
  }
}

// ─── Backend Process ─────────────────────────────────────────────────────────

function checkPython() {
  // 1. Scan candidate roots for project venv
  const candidateRoots = [
    path.join(__dirname, '..', '..'),
    path.join(process.resourcesPath, '..'),
    path.join(process.resourcesPath, '..', '..', '..', '..'),
    process.cwd(),
    path.join(process.cwd(), '..'),
    'C:\\Users\\thaku\\OneDrive\\Desktop\\IBVAP'
  ];

  for (const root of candidateRoots) {
    const venvPaths = [
      path.join(root, 'venv', 'Scripts', 'python.exe'),
      path.join(root, '.venv', 'Scripts', 'python.exe'),
      path.join(root, 'venv', 'bin', 'python'),
      path.join(root, '.venv', 'bin', 'python'),
    ];

    for (const venvPython of venvPaths) {
      try {
        if (fs.existsSync(venvPython)) {
          execSync(`"${venvPython}" -m uvicorn --version`, { encoding: 'utf-8', timeout: 5000, windowsHide: true });
          console.log(`[IBVAP] Found verified venv Python: ${venvPython}`);
          return venvPython;
        }
      } catch {
        // Try next
      }
    }
  }

  // 2. Fall back to system Python if it has uvicorn installed
  const commands = ['python', 'python3', 'py'];
  for (const cmd of commands) {
    try {
      execSync(`${cmd} -m uvicorn --version`, { encoding: 'utf-8', timeout: 5000, windowsHide: true });
      console.log(`[IBVAP] Found verified system ${cmd}`);
      return cmd;
    } catch {
      // Try next
    }
  }
  return null;
}

function checkBackendHealthy() {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/health`, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function startBackend() {
  // 1. If backend is already running (e.g. started by dev script or already active), reuse it
  const alreadyRunning = await checkBackendHealthy();
  if (alreadyRunning) {
    console.log(`[IBVAP] Backend is already running and healthy on port ${BACKEND_PORT}`);
    return;
  }

  const pythonCmd = checkPython();
  if (!pythonCmd) {
    dialog.showErrorBox(
      'Python / Uvicorn Not Found',
      'IBVAP could not find a Python environment with uvicorn installed.\n\n' +
      'Please ensure the virtual environment in the project exists:\n' +
      'cd backend && pip install -r requirements.txt\n\n' +
      'The application will now exit.'
    );
    app.quit();
    throw new Error('Python not found');
  }

  console.log(`[IBVAP] Starting backend from: ${BACKEND_DIR}`);

  const pythonPath = isDev
    ? path.join(__dirname, '..', '..')
    : `${process.resourcesPath};${path.join(process.resourcesPath, 'backend')};${path.join(process.resourcesPath, '..', '..', '..', '..')}`;

  // Resolve canonical persistent DB and Storage paths across dev and packaged modes
  const projectRootCandidates = [
    'C:\\Users\\thaku\\OneDrive\\Desktop\\IBVAP',
    path.join(__dirname, '..', '..'),
    path.join(process.resourcesPath, '..', '..', '..', '..'),
  ];
  let canonicalDb = null;
  let canonicalStorage = null;
  for (const pr of projectRootCandidates) {
    const candidateDb = path.join(pr, 'backend', 'ibvap.db');
    const candidateStorage = path.join(pr, 'storage');
    if (fs.existsSync(candidateDb) || fs.existsSync(candidateStorage)) {
      canonicalDb = candidateDb;
      canonicalStorage = candidateStorage;
      break;
    }
  }

  const resolvedDbPath = canonicalDb || path.join(BACKEND_DIR, 'ibvap.db');
  const resolvedStoragePath = canonicalStorage || STORAGE_DIR;
  console.log(`[IBVAP] Binding persistent DB: ${resolvedDbPath}`);
  console.log(`[IBVAP] Binding persistent Storage: ${resolvedStoragePath}`);

  // Spawn uvicorn
  backendProcess = spawn(
    pythonCmd,
    ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
    {
      cwd: BACKEND_DIR,
      env: {
        ...process.env,
        IBVAP_DB_PATH: resolvedDbPath,
        IBVAP_STORAGE_ROOT: resolvedStoragePath,
        PYTHONDONTWRITEBYTECODE: '1',
        PYTHONPATH: pythonPath,
      },
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    }
  );

  backendProcess.stdout.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  backendProcess.on('error', (err) => {
    console.error('[IBVAP] Failed to start backend:', err);
  });

  backendProcess.on('exit', (code) => {
    console.log(`[IBVAP] Backend exited with code ${code}`);
    if (!isQuitting && code !== 0) {
      dialog.showErrorBox(
        'Backend Crashed',
        `The IBVAP backend process exited unexpectedly (code: ${code}).\n\n` +
        'Please check that all Python dependencies are installed:\n' +
        `cd ${BACKEND_DIR}\npip install -r requirements.txt`
      );
    }
  });

  // Poll health endpoint cleanly with bounded interval
  return new Promise((resolve, reject) => {
    let resolved = false;
    let attempts = 0;
    const maxAttempts = 60; // 30 seconds

    const pollInterval = setInterval(async () => {
      if (resolved) {
        clearInterval(pollInterval);
        return;
      }

      attempts++;
      const healthy = await checkBackendHealthy();
      if (healthy) {
        resolved = true;
        clearInterval(pollInterval);
        console.log('[IBVAP] Backend is healthy');
        resolve();
        return;
      }

      if (attempts >= maxAttempts) {
        resolved = true;
        clearInterval(pollInterval);
        console.error('[IBVAP] Backend failed to start after 30s');
        dialog.showErrorBox(
          'Backend Timeout',
          'The IBVAP backend did not start within 30 seconds.\n\n' +
          'Please ensure Python dependencies are installed:\n' +
          'cd backend && pip install -r requirements.txt'
        );
        app.quit();
        reject(new Error('Backend timeout'));
      }
    }, 500);
  });
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    console.log('[IBVAP] Stopping backend...');
    // On Windows, we need to kill the process tree
    try {
      if (process.platform === 'win32') {
        execSync(`taskkill /pid ${backendProcess.pid} /T /F`, { windowsHide: true });
      } else {
        backendProcess.kill('SIGTERM');
      }
    } catch (e) {
      console.error('[IBVAP] Error stopping backend:', e.message);
    }
    backendProcess = null;
  }
}

// ─── IPC Handlers ────────────────────────────────────────────────────────────

function setupIPC() {
  // Native Windows notification
  ipcMain.on('show-notification', (_, { title, body, urgency }) => {
    if (Notification.isSupported()) {
      const notif = new Notification({
        title: title || 'SHIELD Alert',
        body: body || '',
        icon: ICON_PATH,
        urgency: urgency || 'normal', // low, normal, critical
      });
      notif.on('click', () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      });
      notif.show();
    }
  });

  // Minimize to tray
  ipcMain.on('minimize-to-tray', () => {
    if (mainWindow) mainWindow.hide();
  });

  // Get app version
  ipcMain.handle('get-app-version', () => {
    return app.getVersion();
  });

  // Check if running in desktop mode
  ipcMain.handle('is-desktop', () => true);

  // ─── Intrusion & Threat Reporting (Supabase Cloud Sync) ─────────────────
  ipcMain.handle('report-zone-breach', async (_, data) => {
    return await reportZoneBreach(data);
  });

  ipcMain.handle('report-loitering', async (_, data) => {
    return await reportLoitering(data);
  });

  ipcMain.handle('report-face-match', async (_, data) => {
    return await reportFaceMatch(data);
  });
}

// ─── Real-time AI Alerts Forwarder (WebSocket -> Supabase) ──────────────────

function startAlertsSync() {
  const wsUrl = `ws://127.0.0.1:${BACKEND_PORT}/ws/alerts`;
  const WSClient = globalThis.WebSocket || (typeof WebSocket !== 'undefined' ? WebSocket : null);
  let ws = null;
  let reconnectTimer = null;

  if (!WSClient) {
    console.warn('[IBVAP] Global WebSocket is not available in Electron environment. Realtime alert sync disabled.');
    return;
  }

  function connect() {
    if (isQuitting) return;
    try {
      ws = new WSClient(wsUrl);

      ws.onopen = () => {
        console.log('[IBVAP] Connected to alerts WebSocket for Supabase cloud sync');
      };

      ws.onmessage = async (event) => {
        try {
          const payload = typeof event.data === 'string' ? JSON.parse(event.data) : JSON.parse(event.data.toString());
          if (payload.type === 'ALERT' && payload.data) {
            const a = payload.data;
            const eventType = String(a.event_type || '').toUpperCase();
            const imageName = a.snapshot_path ? path.basename(a.snapshot_path) : undefined;
            const alertId = a.alert_id || a.id;
            const severity = a.threat_level || 'CRITICAL';

            console.log(`[IBVAP] 🚨 AI Alert received: ${alertId} (${eventType}) -> Forwarding to Supabase...`);

            if (eventType.includes('ZONE') || eventType.includes('BREACH') || eventType.includes('INTRUSION')) {
              await reportZoneBreach({
                id: alertId,
                cameraId: a.camera_id,
                objectType: a.object_type,
                objectId: a.object_id,
                confidence: a.confidence,
                movementAnalysis: a.reason,
                imageName,
                severity,
                latitude: a.latitude,
                longitude: a.longitude,
              });
            } else if (eventType.includes('LOITER')) {
              await reportLoitering({
                id: alertId,
                cameraId: a.camera_id,
                objectType: a.object_type,
                objectId: a.object_id,
                confidence: a.confidence,
                movementAnalysis: a.reason,
                imageName,
                severity: severity || 'HIGH',
                latitude: a.latitude,
                longitude: a.longitude,
              });
            } else if (eventType.includes('FACE') || eventType.includes('WATCHLIST')) {
              await reportFaceMatch({
                id: alertId,
                cameraId: a.camera_id,
                personName: a.object_id || a.reason,
                objectId: a.object_id,
                confidence: a.confidence,
                movementAnalysis: a.reason,
                imageName,
                severity,
                latitude: a.latitude,
                longitude: a.longitude,
              });
            }
          }
        } catch (err) {
          // Log parsing error silently
        }
      };

      ws.onerror = () => {};
      ws.onclose = () => {
        if (!isQuitting) {
          reconnectTimer = setTimeout(connect, 5000);
        }
      };
    } catch {
      if (!isQuitting) {
        reconnectTimer = setTimeout(connect, 5000);
      }
    }
  }

  connect();
}

// ─── App Lifecycle ───────────────────────────────────────────────────────────

// Prevent multiple instances
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

app.whenReady().then(async () => {
  console.log('[IBVAP] App starting...');

  // Setup IPC handlers
  setupIPC();

  // Show splash
  createSplashWindow();

  // Start backend
  try {
    await startBackend();
    console.log('[IBVAP] Backend ready');
    startAlertsSync();
  } catch (err) {
    console.error('[IBVAP] Backend failed to start:', err);
    return;
  }

  // Create main window and tray
  createMainWindow();
  createTray();
});

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
});

app.on('window-all-closed', () => {
  // On Windows, don't quit when all windows are closed (tray mode)
  // The app quits via tray menu
});

app.on('activate', () => {
  if (mainWindow === null) {
    createMainWindow();
  }
});
