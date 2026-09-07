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
