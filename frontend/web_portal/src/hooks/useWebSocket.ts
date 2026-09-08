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

          // Multi-Modal Alerting (SIH Differentiator 3)
          if (alertData.threat_level === 'CRITICAL') {
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
        case 'DETECTION':
          addDetection(msg.data as Parameters<typeof addDetection>[0]);
          break;
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
          if (p.status === 'PROCESSING' || p.status === 'AI_ANALYZING') {
            setSystemStatus({ ai_engine_status: 'RUNNING', fps: p.fps || 25.0 });
          }
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
