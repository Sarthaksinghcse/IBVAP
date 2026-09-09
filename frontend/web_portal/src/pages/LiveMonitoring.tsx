import { useEffect } from 'react';
import { UploadPanel } from '../components/monitoring/UploadPanel';
import { CCTVPanel } from '../components/dashboard/CCTVPanel';
import { DetectionLog } from '../components/monitoring/DetectionLog';
import { ErrorBoundary } from '../components/ui/ErrorBoundary';
import { useCameras } from '../hooks/useCameras';
import { useStore } from '../store/useStore';

export default function LiveMonitoring() {
  useCameras();
  const selectedCamId  = useStore((s) => s.selectedCameraId);
  const activeVideoId  = useStore((s) => s.activeVideoId);
  const activeVideoUrl = useStore((s) => s.activeVideoUrl);
  const setDetections  = useStore((s) => s.setDetections);

  useEffect(() => {
    // Zero preloaded detections for live cameras (only when not analyzing or playing a video).
    // Live detection events arrive strictly in real-time from active frames via WebSocket.
    if (!activeVideoUrl && !activeVideoId) {
      setDetections([]);
    }
  }, [selectedCamId, activeVideoUrl, activeVideoId, setDetections]);

  return (
    <div className="space-y-4">
      {/* Upload Panel */}
      <ErrorBoundary
        fallbackTitle="Video Upload Component Error"
        fallbackMessage="The video upload component encountered an issue. Video analysis in the background remains unaffected."
      >
        <UploadPanel />
      </ErrorBoundary>

      {/* Main monitoring area */}
      <div className="grid grid-cols-12 gap-4 min-h-[580px]">
        {/* Live feed with detection overlay */}
        <div className="col-span-12 lg:col-span-8 flex flex-col">
          <ErrorBoundary
            fallbackTitle="Live Monitor / CCTV Panel Error"
            fallbackMessage="An error occurred while displaying the camera viewport. The detection stream and control panels remain operational."
          >
            <CCTVPanel />
          </ErrorBoundary>
        </div>

        {/* Detection log */}
        <div className="col-span-12 lg:col-span-4 flex flex-col">
          <ErrorBoundary
            fallbackTitle="Detection Log Display Error"
            fallbackMessage="An error occurred while rendering detection events. Tracking engine continues in the background."
          >
            <DetectionLog cameraId={selectedCamId} />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}


