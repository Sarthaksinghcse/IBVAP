import { useState, useRef, useEffect, useCallback } from 'react';

export interface UseWebcamCaptureReturn {
  videoRef: React.RefObject<HTMLVideoElement>;
  isReady: boolean;
  isLoading: boolean;
  error: string | null;
  startStream: (deviceId?: string) => Promise<boolean>;
  stopStream: () => void;
  captureFrame: () => string | null;
}

export function useWebcamCapture(): UseWebcamCaptureReturn {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const [isReady, setIsReady] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch (e) {
          console.warn('[useWebcamCapture] Error stopping track:', e);
        }
      });
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsReady(false);
  }, []);

  const startStream = useCallback(async (deviceId?: string): Promise<boolean> => {
    if (typeof window === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setError('Camera access is not supported in this browser.');
      return false;
    }

    setIsLoading(true);
    setError(null);
    stopStream();

    try {
      const constraints: MediaStreamConstraints = {
        video: deviceId
          ? { deviceId: { exact: deviceId } }
          : {
              width: { ideal: 1280 },
              height: { ideal: 720 },
              facingMode: 'user',
            },
        audio: false,
      };

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (err: any) {
        // Fallback to basic video constraint if ideal resolution fails
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      }

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }

      setIsReady(true);
      setIsLoading(false);
      return true;
    } catch (err: any) {
      console.error('[useWebcamCapture] Failed to access camera:', err);
      let msg = 'Failed to access camera.';
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        msg = 'Camera permission was denied. Please allow camera access in your browser settings.';
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        msg = 'No camera device found on this system.';
      } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
        msg = 'Camera is in use by another application.';
      }
      setError(msg);
      setIsLoading(false);
      setIsReady(false);
      return false;
    }
  }, [stopStream]);

  const captureFrame = useCallback((): string | null => {
    const video = videoRef.current;
    if (!video || !isReady || video.videoWidth === 0 || video.videoHeight === 0) {
      return null;
    }

    if (!canvasRef.current) {
      canvasRef.current = document.createElement('canvas');
    }

    const canvas = canvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    // Draw full resolution frame
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.90);
  }, [isReady]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      stopStream();
    };
  }, [stopStream]);

  return {
    videoRef,
    isReady,
    isLoading,
    error,
    startStream,
    stopStream,
    captureFrame,
  };
}
