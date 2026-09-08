/**
 * SHIELD / IBVAP — Intrusion Reporter
 * Electron Supabase Integration Module
 *
 * Reports intrusion events (Zone Breaches, Loitering, Face Matches) to Supabase cloud.
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
    createClient = null;
  }
}

// ─── Environment Configuration ───────────────────────────────────────────────

function loadEnvironment() {
  const candidateEnvPaths = [
    path.join(__dirname, '.env'),
    path.join(__dirname, '..', '.env'),
    path.join(__dirname, '..', '..', '.env'),
    path.join(__dirname, '..', 'web_portal', '.env'),
  ];

  for (const envPath of candidateEnvPaths) {
    try {
      if (fs.existsSync(envPath)) {
        const lines = fs.readFileSync(envPath, 'utf8').split(/\r?\n/);
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
      // Ignore reading error
    }
  }
}

loadEnvironment();

const SUPABASE_URL = process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_ANON_KEY || process.env.SUPABASE_KEY || process.env.VITE_SUPABASE_ANON_KEY || '';
const INTRUSIONS_TABLE = process.env.SUPABASE_INTRUSIONS_TABLE || 'intrusions';

let supabaseClient = null;

function isConfigured() {
  return Boolean(SUPABASE_URL && SUPABASE_KEY);
}

function getSupabaseClient() {
  if (supabaseClient) return supabaseClient;

  if (!isConfigured()) {
    return null;
  }

  try {
    supabaseClient = createClient(SUPABASE_URL, SUPABASE_KEY, {
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

/**
 * Generic event reporter to Supabase table
 */
async function reportIntrusion(eventType, data) {
  const client = getSupabaseClient();
  const timestamp = data.timestamp || new Date().toISOString();

  // Normalize payload accommodating both camelCase and snake_case
  const record = {
    event_type: eventType,
    camera_id: data.cameraId || data.camera_id || 'UNKNOWN',
    object_type: data.objectType || data.object_type || 'Unknown',
    object_id: data.objectId || data.object_id || null,
    confidence: typeof data.confidence === 'number' ? data.confidence : parseFloat(data.confidence) || 0.0,
    distance_from_fence: data.distanceFromFence !== undefined ? Number(data.distanceFromFence) : (data.distance_from_fence !== undefined ? Number(data.distance_from_fence) : null),
    latitude: data.latitude !== undefined ? Number(data.latitude) : null,
    longitude: data.longitude !== undefined ? Number(data.longitude) : null,
    movement_analysis: data.movementAnalysis || data.movement_analysis || null,
    person_name: data.personName || data.person_name || data.name || null,
    watchlist_id: data.watchlistId || data.watchlist_id || null,
    duration: data.duration !== undefined ? Number(data.duration) : null,
    threat_level: data.threatLevel || data.threat_level || 'HIGH',
    status: data.status || 'NEW',
    created_at: timestamp,
    metadata: {
      ...data,
      reportedBy: 'SHIELD-Electron',
      reportedAt: timestamp,
    },
  };

  if (!client) {
    console.log(`[IntrusionReporter] [OFFLINE/MOCK] ${eventType} reported:`, {
      camera: record.camera_id,
      object: `${record.object_type} (${record.object_id || 'N/A'})`,
      confidence: record.confidence,
      distance: record.distance_from_fence,
      coords: `[${record.latitude}, ${record.longitude}]`,
    });
    return {
      success: true,
      synced: false,
      message: 'Supabase credentials not configured. Event handled locally.',
      data: record,
    };
  }

  try {
    const { data: insertedData, error } = await client
      .from(INTRUSIONS_TABLE)
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

    console.log(`[IntrusionReporter] Synced ${eventType} to Supabase (${INTRUSIONS_TABLE}):`, record.camera_id, record.object_id);
    return {
      success: true,
      synced: true,
      data: insertedData || record,
    };
  } catch (err) {
    console.error(`[IntrusionReporter] Network/client error while reporting ${eventType}:`, err.message);
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
async function reportZoneBreach(data) {
  return reportIntrusion('ZONE_BREACH', {
    threatLevel: 'CRITICAL',
    ...data,
  });
}

/**
 * Report suspicious loitering detection
 */
async function reportLoitering(data) {
  return reportIntrusion('LOITERING', {
    threatLevel: 'MEDIUM',
    ...data,
  });
}

/**
 * Report a facial recognition watchlist match
 */
async function reportFaceMatch(data) {
  return reportIntrusion('FACE_MATCH', {
    threatLevel: 'CRITICAL',
    ...data,
  });
}

module.exports = {
  reportZoneBreach,
  reportLoitering,
  reportFaceMatch,
  reportIntrusion,
  getSupabaseClient,
  isConfigured,
};
