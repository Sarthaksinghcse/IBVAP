// ─── IBVAP Desktop — Dev Mode Launcher ───────────────────────────────────────
// Starts the FastAPI backend + Vite dev server, then launches Electron.

const { spawn, execSync } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

const ROOT = path.join(__dirname, '..', '..', '..');
const BACKEND_DIR = path.join(ROOT, 'backend');
const FRONTEND_DIR = path.join(ROOT, 'frontend', 'web_portal');
const DESKTOP_DIR = path.join(__dirname, '..');

const processes = [];

function log(tag, msg) {
  const time = new Date().toLocaleTimeString();
  console.log(`[${time}] [${tag}] ${msg}`);
}

// Find Python command
function findPython() {
  const venvPaths = [
    path.join(ROOT, 'venv', 'Scripts', 'python.exe'),
    path.join(ROOT, '.venv', 'Scripts', 'python.exe'),
    path.join(ROOT, 'venv', 'bin', 'python'),
    path.join(ROOT, '.venv', 'bin', 'python'),
  ];
  for (const p of venvPaths) {
    if (fs.existsSync(p)) {
      try {
        const version = execSync(`"${p}" --version`, { encoding: 'utf-8', timeout: 5000, windowsHide: true });
        log('Python', `Using virtual environment: ${p} (${version.trim()})`);
        return p;
      } catch { /* next */ }
    }
  }

  for (const cmd of ['python', 'python3', 'py']) {
    try {
      const version = execSync(`${cmd} --version`, { encoding: 'utf-8', timeout: 5000, windowsHide: true });
      log('Python', `Using system: ${cmd} (${version.trim()})`);
      return cmd;
    } catch { /* next */ }
  }
  console.error('ERROR: Python not found. Install Python 3.8+ and add to PATH.');
  process.exit(1);
}

// Wait for a URL to respond
function waitForUrl(url, label, timeout = 30000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();

    function check() {
      if (Date.now() - start > timeout) {
        return reject(new Error(`${label} did not start within ${timeout / 1000}s`));
      }

      const req = http.get(url, (res) => {
        if (res.statusCode === 200) {
          log(label, 'Ready ✓');
          resolve();
        } else {
          setTimeout(check, 500);
        }
      });
      req.on('error', () => setTimeout(check, 500));
      req.setTimeout(2000, () => { req.destroy(); setTimeout(check, 500); });
    }

    check();
  });
}

async function main() {
  const pythonCmd = findPython();

  // 1. Start FastAPI backend
  log('Backend', 'Starting FastAPI...');
  const backend = spawn(
    pythonCmd,
    ['-m', 'uvicorn', 'main:app', '--reload', '--host', '127.0.0.1', '--port', '8000'],
    {
      cwd: BACKEND_DIR,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
      shell: true,
      windowsHide: true,
    }
  );
  processes.push(backend);

  backend.stdout.on('data', (d) => log('Backend', d.toString().trim()));
  backend.stderr.on('data', (d) => log('Backend', d.toString().trim()));
  backend.on('exit', (code) => log('Backend', `Exited (code ${code})`));

  // 2. Start Vite dev server
  log('Vite', 'Starting dev server...');
  const vite = spawn(
    /^win/i.test(process.platform) ? 'npm.cmd' : 'npm',
    ['run', 'dev'],
    {
      cwd: FRONTEND_DIR,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, BROWSER: 'none' },
      shell: true,
      windowsHide: true,
    }
  );
  processes.push(vite);

  vite.stdout.on('data', (d) => log('Vite', d.toString().trim()));
  vite.stderr.on('data', (d) => log('Vite', d.toString().trim()));
  vite.on('exit', (code) => log('Vite', `Exited (code ${code})`));

  // 3. Wait for both to be ready
  try {
    await Promise.all([
      waitForUrl('http://localhost:8000/health', 'Backend'),
      waitForUrl('http://localhost:5173', 'Vite'),
    ]);
  } catch (err) {
    console.error(err.message);
    cleanup();
    process.exit(1);
  }

  // 4. Launch Electron
  log('Electron', 'Launching desktop app...');
  const electron = spawn(
    /^win/i.test(process.platform) ? 'npx.cmd' : 'npx',
    ['electron', '.'],
    {
      cwd: DESKTOP_DIR,
      stdio: 'inherit',
      env: { ...process.env },
      shell: true,
    }
  );
  processes.push(electron);

  electron.on('exit', () => {
    log('Electron', 'Window closed');
    cleanup();
  });
}

function cleanup() {
  log('Dev', 'Cleaning up processes...');
  for (const proc of processes) {
    if (proc && !proc.killed) {
      try {
        if (process.platform === 'win32') {
          execSync(`taskkill /pid ${proc.pid} /T /F`, { windowsHide: true });
        } else {
          proc.kill('SIGTERM');
        }
      } catch { /* ignore */ }
    }
  }
  process.exit(0);
}

// Handle Ctrl+C
process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);

main().catch((err) => {
  console.error('Fatal error:', err);
  cleanup();
});
