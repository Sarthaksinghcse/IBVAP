import { useEffect } from 'react';
import { useStore } from '../store/useStore';
import * as api from '../services/api';
import { MOCK_DETECTIONS } from '../services/mock/mockData';

/**
 * Loads initial detections for the selected camera.
 */
export function useDetections(cameraId?: string) {
  const { detections, setDetections } = useStore();
  const isMock = import.meta.env.VITE_USE_MOCK === 'true';

  useEffect(() => {
    if (isMock) {
      setDetections(MOCK_DETECTIONS);
      return;
    }

    api
      .getDetections(cameraId)
      .then(setDetections)
      .catch((e) => console.error('[useDetections]', e));
  }, [cameraId]);

  const cameraDetections = cameraId
    ? detections.filter((d) => d.camera_id === cameraId)
    : detections;

  return cameraDetections;
}
