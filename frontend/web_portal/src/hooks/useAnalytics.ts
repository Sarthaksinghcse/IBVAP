import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import * as api from '../services/api';
import { MOCK_ANALYTICS } from '../services/mock/mockData';

export function useAnalytics() {
  const analytics        = useStore((s) => s.analytics);
  const setAnalytics     = useStore((s) => s.setAnalytics);
  const activeVideoId    = useStore((s) => s.activeVideoId);
  const cameraMode       = useStore((s) => s.cameraMode);
  const selectedCameraId = useStore((s) => s.selectedCameraId);
  const isMock           = useStore((s) => s.isMockMode);

  useEffect(() => {
    if (isMock) {
      setAnalytics(MOCK_ANALYTICS);
      return;
    }

    const videoId = !cameraMode && activeVideoId ? activeVideoId : undefined;
    const camId   = cameraMode ? 'WEBCAM-01' : (!activeVideoId ? selectedCameraId : undefined);

    api
      .getAnalytics(videoId, camId)
      .then(setAnalytics)
      .catch((e) => console.error('[useAnalytics]', e));

    const interval = setInterval(() => {
      api.getAnalytics(videoId, camId).then(setAnalytics).catch(() => {});
    }, 15000);

    return () => clearInterval(interval);
  }, [isMock, activeVideoId, cameraMode, selectedCameraId]);

  return analytics;
}

