import { useEffect, useRef } from 'react';
import { useStore } from '../store/useStore';
import { wsService } from '../services/websocket';
import { MockAIEngine } from '../services/mock/mockEngine';
import * as api from '../services/api';
import type { WSMessage } from '../types';
import { playAlertChime, announceVoiceAlert } from '../utils/audio';


/**
 * Manages WebSocket connection (or mock AI engine in mock mode).
 *
 * Call this ONCE at the app root level (in App.tsx).
 */
export function useWebSocket() {
  const {
    addAlert,
    updateAlertStatus,
    addDetection,
    setSystemStatus,
    setWsConnected,
    isMockMode,
  } = useStore();

  const mockEngineRef = useRef<MockAIEngine | null>(null);

  useEffect(() => {
    if (isMockMode) {
      // ── Mock mode: use in-browser mock AI engine ──────────────────────────
      setWsConnected(true); // show as connected in UI

      mockEngineRef.current = new MockAIEngine({
        onDetection: addDetection,
        onAlert: addAlert,
      });
      mockEngineRef.current.start();

      return () => {
        mockEngineRef.current?.stop();
      };
    }

    // ── Real mode: connect WebSocket ─────────────────────────────────────────

    wsService.onConnectionChange = (connected) => {
      setWsConnected(connected);
      setSystemStatus({ websocket_connected: connected });
    };

    const unsubscribe = wsService.subscribe((msg: WSMessage) => {
      switch (msg.type) {
        case 'ALERT': {
          const alertData = msg.data as Parameters<typeof addAlert>[0];
          addAlert(alertData);

          const currentSettings = useStore.getState().settings;

          // Multi-Modal Alerting (SIH Differentiator 3) - Trigger on both CRITICAL and HIGH alerts
          if (alertData.threat_level === 'CRITICAL' || alertData.threat_level === 'HIGH') {
            if (currentSettings.alertSound) {
              playAlertChime();
            }
            if (currentSettings.voiceAlerts ?? true) {
              announceVoiceAlert(alertData);
            }
          }

          // Auto-Acknowledge Low Alerts setting
          if (alertData.threat_level === 'LOW' && currentSettings.autoAcknowledge && alertData.id) {
            api.patchAlert(alertData.id, 'ACKNOWLEDGED').then(() => {
              updateAlertStatus(alertData.id, 'ACKNOWLEDGED');
            }).catch((err) => {
              console.warn('[useWebSocket] Auto-acknowledge error:', err);
            });
          }
          break;
        }

        case 'ALERT_UPDATE':
          if (msg.data?.id && msg.data?.status) {
            updateAlertStatus(msg.data.id, msg.data.status);
          }
          break;
        case 'DETECTION': {
          const det = msg.data as Parameters<typeof addDetection>[0];
          addDetection(det);
          break;
        }
        case 'ANPR_EVENT': {
          const anpr = msg.data as any;
          if (anpr) {
            addDetection({
              id: anpr.id || `anpr-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
              camera_id: anpr.camera_id,
              video_id: anpr.video_id,
              object_type: anpr.vehicle_type || 'VEHICLE',
              object_id: anpr.vehicle_label || `Vehicle Track #${anpr.vehicle_track_id}`,
              confidence: anpr.plate_confidence || 85.0,
              event_type: anpr.plate_status === 'READABLE' ? 'PLATE_DETECTED' : 'UNREADABLE_PLATE',
              bbox: anpr.bbox || { x: 0, y: 0, w: 0, h: 0 },
              timestamp: anpr.timestamp || new Date().toISOString(),
              video_time_sec: anpr.video_time_sec,
              plate_info: {
                plate_detected: true,
                plate_text: anpr.plate_text,
                plate_confidence: anpr.plate_confidence,
                plate_status: anpr.plate_status,
              }
            });
          }
          break;
        }
        case 'SYSTEM':
          setSystemStatus(msg.data as Parameters<typeof setSystemStatus>[0]);
          break;
        case 'VIDEO_PROGRESS': {
          const p = msg.data as {
            video_id: string;
            progress: number;
            current_frame: number;
            total_frames: number;
            fps: number;
            detections: number;
            tracks: number;
            events: number;
            status: string;
          };
          const setMetrics = useStore.getState().setVideoAnalysisMetrics;
          setMetrics({
            progress: p.progress,
            currentFrame: p.current_frame,
            totalFrames: p.total_frames,
            fps: p.fps,
            detections: p.detections,
            tracks: p.tracks,
            events: p.events,
            status: p.status,
          });
          break;
        }
        case 'VIDEO_STATUS': {
          const s = msg.data as { video_id: string; status: string; progress?: number };
          const activeVid = useStore.getState().activeVideoId;
          if (activeVid === s.video_id) {
            useStore.getState().setUploadStatus(s.status);
            if (s.status === 'COMPLETED') {
              useStore.getState().setVideoAnalysisMetrics({ progress: 100, status: 'COMPLETED' });
            }
          }
          break;
        }
      }
    });



    wsService.connect();

    return () => {
      unsubscribe();
      wsService.disconnect();
    };
  }, [isMockMode]);
}
