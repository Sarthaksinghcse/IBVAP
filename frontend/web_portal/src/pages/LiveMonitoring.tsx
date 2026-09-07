import { useEffect } from 'react';
import { UploadPanel } from '../components/monitoring/UploadPanel';
import { CCTVPanel } from '../components/dashboard/CCTVPanel';
import { DetectionLog } from '../components/monitoring/DetectionLog';
import { useCameras } from '../hooks/useCameras';
import { useStore } from '../store/useStore';
import * as api from '../services/api';

export default function LiveMonitoring() {
  useCameras();
  const selectedCamId  = useStore((s) => s.selectedCameraId);
  const activeVideoId  = useStore((s) => s.activeVideoId);
  const activeVideoUrl = useStore((s) => s.activeVideoUrl);
  const setDetections  = useStore((s) => s.setDetections);

  useEffect(() => {
    if (!activeVideoUrl) {
      api.getDetections(selectedCamId, undefined, 100)
        .then((dets) => {
          if (dets && dets.length > 0) {
            setDetections(dets);
          }
        })
        .catch((e) => console.warn('[LiveMonitoring] Failed to fetch initial detections:', e));
    }
  }, [selectedCamId, activeVideoUrl, setDetections]);

  return (
    <div className="space-y-4">
      {/* Upload Panel */}
      <UploadPanel />

      {/* Main monitoring area */}
      <div className="grid grid-cols-12 gap-4 min-h-[580px]">
        {/* Live feed with detection overlay */}
        <div className="col-span-12 lg:col-span-8 flex flex-col">
          <CCTVPanel />
        </div>

        {/* Detection log */}
        <div className="col-span-12 lg:col-span-4 flex flex-col">
          <DetectionLog cameraId={selectedCamId} />
        </div>
      </div>
    </div>
  );
}

