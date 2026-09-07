/**
 * Mock AI Engine — simulates real-time AI detection events in the browser.
 *
 * In MOCK MODE this replaces the real Python AI engine.
 * It dispatches events through the same Zustand store actions that
 * the real WebSocket handler would use — so no component changes needed
 * when switching to the real YOLO engine.
 */
import type { Alert, Detection, EventType, ObjectType, ThreatLevel } from '../../types';

// ─── Random Helpers ───────────────────────────────────────────────────────────

const rand = (min: number, max: number) =>
  Math.floor(Math.random() * (max - min + 1)) + min;

const pick = <T>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];

const uid = () => Math.random().toString(36).slice(2, 10).toUpperCase();

const CAMERAS = ['BOP-01', 'BOP-02', 'BOP-03', 'BOP-05', 'BOP-07'];

// ─── Event Generators ─────────────────────────────────────────────────────────

function generatePersonDetection(cameraId: string): Detection {
  const objId = `Person #${rand(1, 25)}`;
  const inZone = Math.random() < 0.25;
  const loitering = inZone && Math.random() < 0.5;

  return {
    id: `det-${uid()}`,
    camera_id: cameraId,
    object_type: 'PERSON' as ObjectType,
    object_id: objId,
    confidence: rand(82, 99),
    zone: inZone ? 'Restricted Zone A' : undefined,
    event_type: inZone
      ? 'ZONE_INTRUSION'
      : loitering
      ? 'LOITERING'
      : ('PERSON_DETECTED' as EventType),
    bbox: {
      x: rand(5, 75),
      y: rand(10, 50),
      w: rand(8, 16),
      h: rand(30, 55),
    },
    timestamp: new Date().toISOString(),
    is_in_restricted_zone: inZone,
    loitering_duration: loitering ? rand(15, 90) : undefined,
  };
}

function generateVehicleDetection(cameraId: string): Detection {
  return {
    id: `det-${uid()}`,
    camera_id: cameraId,
    object_type: 'VEHICLE' as ObjectType,
    object_id: `Vehicle #${rand(1, 10)}`,
    confidence: rand(88, 98),
    event_type: 'VEHICLE_DETECTED' as EventType,
    bbox: {
      x: rand(10, 60),
      y: rand(45, 65),
      w: rand(20, 35),
      h: rand(15, 28),
    },
    timestamp: new Date().toISOString(),
    is_in_restricted_zone: false,
  };
}

function generateAlertFromDetection(det: Detection): Alert {
  const isIntrusion = det.event_type === 'ZONE_INTRUSION';
  const isLoitering = det.event_type === 'LOITERING';

  let threatLevel: ThreatLevel = 'LOW';
  if (isIntrusion && (det.loitering_duration ?? 0) > 25) threatLevel = 'CRITICAL';
  else if (isIntrusion) threatLevel = 'HIGH';
  else if (isLoitering) threatLevel = 'HIGH';
  else if (det.object_type === 'VEHICLE') threatLevel = 'MEDIUM';

  const reasons: Record<string, string> = {
    ZONE_INTRUSION: `${det.object_id} entered ${det.zone || 'restricted zone'} and stayed for ${det.loitering_duration ?? 0}s. Confidence: ${det.confidence}%.`,
    LOITERING: `${det.object_id} detected loitering near perimeter for ${det.loitering_duration ?? 15}s.`,
    VEHICLE_DETECTED: `Unidentified vehicle (${det.object_id}) detected in monitored area.`,
    PERSON_DETECTED: `${det.object_id} detected in monitored zone. Confidence: ${det.confidence}%.`,
  };

  return {
    id: `alert-${uid()}`,
    alert_id: `ALERT-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${uid()}`,
    camera_id: det.camera_id,
    event_type: det.event_type,
    object_type: det.object_type,
    object_id: det.object_id,
    threat_level: threatLevel,
    reason: reasons[det.event_type] || `${det.event_type} detected by AI engine.`,
    status: 'NEW',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

// ─── Mock Engine Class ────────────────────────────────────────────────────────

interface MockEngineCallbacks {
  onDetection: (d: Detection) => void;
  onAlert: (a: Alert) => void;
}

export class MockAIEngine {
  private timer: ReturnType<typeof setInterval> | null = null;
  private callbacks: MockEngineCallbacks;

  constructor(callbacks: MockEngineCallbacks) {
    this.callbacks = callbacks;
  }

  start(): void {
    if (this.timer) return;

    // Initial events on start
    setTimeout(() => this.fireEvent(), 1500);

    // Recurring events every 8–18 seconds
    this.timer = setInterval(() => this.fireEvent(), rand(8000, 18000));
    console.info('[MockAI] Engine started — simulating detection events');
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private fireEvent(): void {
    const cameraId = pick(CAMERAS);
    const isVehicle = Math.random() < 0.3;

    const detection = isVehicle
      ? generateVehicleDetection(cameraId)
      : generatePersonDetection(cameraId);

    this.callbacks.onDetection(detection);

    // Only generate alert for notable events
    const notable =
      detection.event_type === 'ZONE_INTRUSION' ||
      detection.event_type === 'LOITERING' ||
      (detection.object_type === 'VEHICLE' && Math.random() < 0.4);

    if (notable) {
      const alert = generateAlertFromDetection(detection);
      // Small delay so detection appears first
      setTimeout(() => this.callbacks.onAlert(alert), 500);
    }
  }
}
