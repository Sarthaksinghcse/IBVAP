/**
 * Multi-Modal Audio & Text-to-Speech (TTS) Voice Alerting
 * =======================================================
 * Announces critical security threats verbally using the browser SpeechSynthesis API.
 * Deduplicates voice utterances so each unique incident is announced exactly once.
 */

// Deduplication registry for spoken alerts
const spokenAlertIds = new Set<string>();

/**
 * Play a synthesized dual-tone security chime for critical threat events.
 */
export function playAlertChime() {
  try {
    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();

    osc.type = 'sine';
    osc.frequency.setValueAtTime(880, ctx.currentTime); // A5
    osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.35); // A4

    gain.gain.setValueAtTime(0.25, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start();
    osc.stop(ctx.currentTime + 0.35);
  } catch (e) {
    console.debug('[Audio] Web Audio chime playback error:', e);
  }
}

// Singleton Web Audio Context to avoid browser context exhaustion (max 6 limit in Chromium)
let sharedAudioCtx: AudioContext | null = null;

function getSharedAudioContext(): AudioContext | null {
  try {
    const AudioCtxClass = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtxClass) return null;
    if (!sharedAudioCtx || sharedAudioCtx.state === 'closed') {
      sharedAudioCtx = new AudioCtxClass();
    }
    if (sharedAudioCtx.state === 'suspended') {
      sharedAudioCtx.resume().catch(() => {});
    }
    return sharedAudioCtx;
  } catch (e) {
    console.debug('[Audio] Shared AudioContext initialization error:', e);
    return null;
  }
}

// Automatically unlock audio context upon user interactions
if (typeof window !== 'undefined') {
  const unlockAudio = () => {
    const ctx = getSharedAudioContext();
    if (ctx && ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
  };
  window.addEventListener('click', unlockAudio, { capture: true, passive: true });
  window.addEventListener('keydown', unlockAudio, { capture: true, passive: true });
  window.addEventListener('pointerdown', unlockAudio, { capture: true, passive: true });
}

// Rate limiting for restricted zone person intrusion beeps to avoid acoustic overload
let lastPersonZoneBeepTime = 0;

function doSynthesizeIntrusionBeep(ctx: AudioContext) {
  try {
    const t = ctx.currentTime;

    // Pulse 1: Urgent 1174.7 Hz (D6)
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = 'triangle';
    osc1.frequency.setValueAtTime(1174.7, t);
    gain1.gain.setValueAtTime(0.40, t);
    gain1.gain.exponentialRampToValueAtTime(0.001, t + 0.08);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(t);
    osc1.stop(t + 0.08);

    // Pulse 2: High-Alert 1568.0 Hz (G6)
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'triangle';
    osc2.frequency.setValueAtTime(1568.0, t + 0.09);
    gain2.gain.setValueAtTime(0.45, t + 0.09);
    gain2.gain.exponentialRampToValueAtTime(0.001, t + 0.19);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(t + 0.09);
    osc2.stop(t + 0.19);
  } catch (err) {
    console.debug('[Audio] doSynthesizeIntrusionBeep error:', err);
  }
}

/**
 * Play an urgent acoustic alarm beep when a person enters or is detected inside a restricted zone.
 * Uses a tactical dual-burst alert frequency (1174.7 Hz D6 -> 1568 Hz G6) to immediately alert
 * border security operators of unauthorized human intrusion within the monitored perimeter.
 */
export function playRestrictedZonePersonBeep(force = false, minIntervalMs = 850) {
  const now = Date.now();
  if (!force && now - lastPersonZoneBeepTime < minIntervalMs) {
    return;
  }
  lastPersonZoneBeepTime = now;

  try {
    const ctx = getSharedAudioContext();
    if (!ctx) return;

    if (ctx.state === 'suspended') {
      ctx.resume().then(() => {
        doSynthesizeIntrusionBeep(ctx);
      }).catch(() => {});
    } else {
      doSynthesizeIntrusionBeep(ctx);
    }
  } catch (e) {
    console.debug('[Audio] Restricted zone person beep error:', e);
  }
}

// Backward-compatible alias
export const playPersonDetectedBeep = playRestrictedZonePersonBeep;

/**
 * Announce a critical threat verbally using browser speech synthesis.
 * Format: "Critical alert. [Object] detected in restricted zone [at Camera]."
 */
export function announceVoiceAlert(alert: {
  id?: string;
  alert_id?: string;
  object_id?: string;
  object_type?: string;
  event_type?: string;
  threat_level?: string;
  camera_id?: string;
  reason?: string;
}) {
  const alertKey = alert.id || alert.alert_id;

  // Deduplication: only announce once per unique alert incident
  if (alertKey && spokenAlertIds.has(alertKey)) {
    return;
  }
  if (alertKey) {
    spokenAlertIds.add(alertKey);
    // Keep set size bounded
    if (spokenAlertIds.size > 200) {
      const first = spokenAlertIds.values().next().value;
      if (first) spokenAlertIds.delete(first);
    }
  }

  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    try {
      const sourceLabel = alert.camera_id ? `at ${alert.camera_id}` : '';
      const text = `Critical security alert. ${alert.object_id || 'Object'} detected in restricted zone ${sourceLabel}.`;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn('[VoiceAlert] SpeechSynthesis announcement error:', e);
    }
  }
}
