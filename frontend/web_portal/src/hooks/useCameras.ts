import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import * as api from '../services/api';
import { MOCK_CAMERAS, MOCK_SYSTEM_STATUS } from '../services/mock/mockData';

/**
 * Initialises cameras in the store.
 * In MOCK mode: loads from mockData.
 * In REAL mode: fetches from GET /api/cameras
 */
export function useCameras() {
  const { cameras, setCameras, setSystemStatus } = useStore();
  const isMock = import.meta.env.VITE_USE_MOCK === 'true';

  useEffect(() => {
    if (isMock) {
      setCameras(MOCK_CAMERAS);
      setSystemStatus(MOCK_SYSTEM_STATUS);
      return;
    }

    api
      .getCameras()
      .then((cams) => {
        setCameras(cams);
        const hasRunning = cams.some((c) => c.status === 'ONLINE' && c.ai_status === 'RUNNING');
        const activeRunning = cams.filter((c) => c.status === 'ONLINE' && c.ai_status === 'RUNNING');
        const avgFps = activeRunning.length > 0 ? activeRunning.reduce((acc, c) => acc + (c.fps || 0), 0) / activeRunning.length : 0.0;
        setSystemStatus({
          backend_status: 'ONLINE',
          database_status: 'OK',
          ai_engine_status: hasRunning ? 'RUNNING' : 'STOPPED',
          fps: Math.round(avgFps * 10) / 10,
          processing_time_ms: hasRunning ? 42 : 0,
        });
      })
      .catch((e) => {
        console.error('[useCameras]', e);
        setSystemStatus({ backend_status: 'OFFLINE', ai_engine_status: 'STOPPED', fps: 0 });
      });
  }, []);

  return cameras;
}

