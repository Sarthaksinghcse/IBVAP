/**
 * SHIELD / IBVAP — Intrusion Reporter
 * Electron Supabase Realtime Integration Module
 *
 * Reports intrusion events (Zone Breaches, Loitering, Face Matches)
 * to Supabase 'alerts' table for real-time push to the Shield iOS app.
 */

const fs = require('fs');
const path = require('path');

let createClient = null;
try {
  ({ createClient } = require('@supabase/supabase-js'));
} catch {
  try {
    ({ createClient } = require(path.join(__dirname, 'node_modules', '@supabase', 'supabase-js')));
  } catch {
    try {
      ({ createClient } = require(path.join(__dirname, '..', 'frontend', 'desktop', 'node_modules', '@supabase', 'supabase-js')));
    } catch {
      try {
        ({ createClient } = require(path.join(__dirname, '..', 'node_modules', '@supabase', 'supabase-js')));
      } catch {
        createClient = null;
      }
    }
  }
}

// ─── Environment Configuration ───────────────────────────────────────────────

function loadEnvironment() {
  const candidateEnvPaths = [
    path.join(__dirname, '.env'),
    path.join(__dirname, '..', '.env'),
    path.join(__dirname, '..', '..', '.env'),
    path.join(__dirname, '..', 'web_portal', '.env'),
    path.join(__dirname, 'frontend', 'desktop', '.env'),
  ];

  for (const envPath of candidateEnvPaths) {
    try {
      if (fs.existsSync(envPath)) {
        const content = fs.readFileSync(envPath, 'utf8');
        const lines = content.split(/\r?\n/);
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed && !trimmed.startsWith('#')) {
            const eqIdx = trimmed.indexOf('=');
            if (eqIdx !== -1) {
              const key = trimmed.slice(0, eqIdx).trim();
              const val = trimmed.slice(eqIdx + 1).trim().replace(/^['"]|['"]$/g, '');
              if (!process.env[key]) {
                process.env[key] = val;
              }
            }
          }
        }
      }
    } catch {
      // Ignore read errors
    }
  }
}

loadEnvironment();

const SUPABASE_URL = process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL || 'https://euyvbxvbnlmqdppqovix.supabase.co';
const SUPABASE_KEY = process.env.SUPABASE_ANON_KEY || process.env.SUPABASE_KEY || process.env.VITE_SUPABASE_ANON_KEY || 'sb_publishable_NhZFPcp7LgMzDwHF7B_ntA_sN1ugz_G';
const ALERTS_TABLE = process.env.SUPABASE_ALERTS_TABLE || process.env.SUPABASE_INTRUSIONS_TABLE || 'alerts';

let supabaseClient = null;

function isConfigured() {
  const url = process.env.SUPABASE_URL || SUPABASE_URL;
  const key = process.env.SUPABASE_ANON_KEY || SUPABASE_KEY;
  return Boolean(url && key && !url.includes('your-project-id'));
}

function initSupabase(url, anonKey) {
  if (url) process.env.SUPABASE_URL = url;
  if (anonKey) process.env.SUPABASE_ANON_KEY = anonKey;
  supabaseClient = null;
  return getSupabaseClient();
}

function getSupabaseClient() {
  if (supabaseClient) return supabaseClient;

  const url = process.env.SUPABASE_URL || SUPABASE_URL;
  const key = process.env.SUPABASE_ANON_KEY || SUPABASE_KEY;

  if (!isConfigured() || !createClient) {
    return null;
  }

  try {
    supabaseClient = createClient(url, key, {
      auth: {
        persistSession: false,
        autoRefreshToken: false,
      },
    });
    return supabaseClient;
  } catch (err) {
    console.warn('[IntrusionReporter] Failed to initialize Supabase client:', err.message);
    return null;
  }
}

function generateAlertId() {
  const ts = Date.now().toString(36).toUpperCase();
  const rand = Math.random().toString(36).substring(2, 6).toUpperCase();
  return `ALT-${ts}-${rand}`;
}

function formatHumanDate(date) {
  try {
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  } catch {
    return date.toISOString();
  }
}

/**
 * Normalizes and inserts an intrusion alert into the Supabase 'alerts' table.
 * Exactly matches the Shield iOS app and Supabase Realtime schema.
 */
async function reportIntrusion(eventType, data = {}) {
  const client = getSupabaseClient();
  const now = new Date();
  const timestamp = data.timestamp || now.toISOString();
  const formattedDate = data.formattedDate || data.formatted_date || formatHumanDate(now);

  const cameraId = data.cameraId || data.camera_id || 'BOP-07';
  const objectType = data.objectType || data.object_type || 'Human';
  const objectId = data.objectId || data.object_id || data.personName || data.name || 'Person #42';
  const confidence = typeof data.confidence === 'number' ? data.confidence : parseFloat(data.confidence) || 0.90;
  const latitude = data.latitude !== undefined && data.latitude !== null ? Number(data.latitude) : 34.5610;
  const longitude = data.longitude !== undefined && data.longitude !== null ? Number(data.longitude) : 76.1320;
  const distanceFromFence = data.distanceFromFence !== undefined ? Number(data.distanceFromFence) : (data.distance_from_fence !== undefined ? Number(data.distance_from_fence) : null);
  const zoneName = data.zoneName || data.zone_name || 'Sector Kargil Restricted Zone';
  const durationSeconds = data.durationSeconds !== undefined ? Math.round(Number(data.durationSeconds)) : (data.duration !== undefined ? Math.round(Number(data.duration)) : null);
  const movementAnalysis = data.movementAnalysis || data.movement_analysis || 'Subject detected in restricted border perimeter';
  const imageName = data.imageName || data.image_name || null;
  const isAcknowledged = Boolean(data.isAcknowledged || data.is_acknowledged || false);

  // Derive defaults based on event type
  let defaultTitle = 'Perimeter Intrusion Detected';
  let defaultSeverity = 'CRITICAL';

  if (eventType === 'ZONE_BREACH') {
    defaultTitle = `Zone Breach — ${cameraId}`;
    defaultSeverity = 'CRITICAL';
  } else if (eventType === 'LOITERING') {
    defaultTitle = `Loitering Detected — ${cameraId}`;
    defaultSeverity = 'HIGH';
  } else if (eventType === 'FACE_MATCH') {
    defaultTitle = `Watchlist Face Match — ${objectId}`;
    defaultSeverity = 'CRITICAL';
  }

  const title = data.title || defaultTitle;
  const severity = data.severity || data.threatLevel || data.threat_level || defaultSeverity;
  const type = data.type || eventType || 'ZONE_BREACH';
  const location = data.location || `${cameraId} • Sector Kargil`;
  const id = data.id || generateAlertId();

  // Record strictly matching Supabase 'alerts' table schema
  const record = {
    id,
    type,
    severity,
    title,
    location,
    camera_id: cameraId,
    timestamp,
    formatted_date: formattedDate,
    object_type: objectType,
    object_id: objectId,
    confidence,
    zone_name: zoneName,
    duration_seconds: durationSeconds,
    distance_from_fence: distanceFromFence,
    is_acknowledged: isAcknowledged,
    movement_analysis: movementAnalysis,
    image_name: imageName,
    latitude,
    longitude,
    created_at: timestamp,
  };

  // If Supabase credentials are not configured yet, operate in offline/mock mode
  if (!client) {
    console.log(`[IntrusionReporter] [OFFLINE/MOCK] ${type} reported to '${ALERTS_TABLE}':`, {
      id: record.id,
      title: record.title,
      camera: record.camera_id,
      object: `${record.object_type} (${record.object_id})`,
      confidence: record.confidence,
      distance: record.distance_from_fence,
      coords: `[${record.latitude}, ${record.longitude}]`,
    });
    return {
      success: true,
      synced: false,
      message: 'Supabase credentials not configured. Event handled locally. Add SUPABASE_URL and SUPABASE_ANON_KEY to .env to enable cloud realtime sync.',
      data: record,
    };
  }

  try {
    const { data: insertedData, error } = await client
      .from(ALERTS_TABLE)
      .insert([record])
      .select();

    if (error) {
      console.warn(`[IntrusionReporter] Supabase insert warning (${error.message || error.code}):`, error);
      return {
        success: false,
        synced: false,
        error: error.message || error,
        data: record,
      };
    }

    console.log(`[IntrusionReporter] 🚨 Realtime alert pushed to Supabase table '${ALERTS_TABLE}':`, record.id, record.title);
    return {
      success: true,
      synced: true,
      data: (insertedData && insertedData[0]) ? insertedData[0] : record,
    };
  } catch (err) {
    console.error(`[IntrusionReporter] Network/client error while reporting ${type}:`, err.message);
    return {
      success: false,
      synced: false,
      error: err.message,
      data: record,
    };
  }
}

/**
 * Report a restricted perimeter or zone breach
 */
async function reportZoneBreach(data = {}) {
  return reportIntrusion('ZONE_BREACH', {
    severity: 'CRITICAL',
    ...data,
  });
}

/**
 * Report suspicious loitering detection
 */
async function reportLoitering(data = {}) {
  return reportIntrusion('LOITERING', {
    severity: 'HIGH',
    ...data,
  });
}

/**
 * Report a facial recognition watchlist match
 */
async function reportFaceMatch(data = {}) {
  return reportIntrusion('FACE_MATCH', {
    severity: 'CRITICAL',
    ...data,
  });
}

module.exports = {
  reportZoneBreach,
  reportLoitering,
  reportFaceMatch,
  reportIntrusion,
  getSupabaseClient,
  initSupabase,
  isConfigured,
  ALERTS_TABLE,
};
