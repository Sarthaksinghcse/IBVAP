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

const pick = <T>(arr: readonly T[] | T[]): T => arr[Math.floor(Math.random() * arr.length)];

const uid = () => Math.random().toString(36).slice(2, 10).toUpperCase();

const CAMERAS = ['BOP-01', 'BOP-02', 'BOP-03', 'BOP-05', 'BOP-07'];

// ─── Event Generators ─────────────────────────────────────────────────────────

function generateTrajectory(cx: number, cy: number, behaviour: string): [number, number][] {
  const points: [number, number][] = [];
  const steps = rand(6, 12);
  let curX = cx - (steps * (behaviour === 'RUNNING' ? 2.5 : 1.2));
  let curY = cy - (steps * (behaviour === 'CIRCLING' ? 1.8 : 0.6));

  for (let i = 0; i < steps; i++) {
    const jitterX = behaviour === 'ERRATIC_MOVEMENT' ? rand(-3, 3) : rand(-1, 1);
    const jitterY = behaviour === 'PACING' ? ((i % 2 === 0 ? 2 : -2)) : rand(-1, 1);
    points.push([
      Math.max(2, Math.min(98, curX + jitterX)),
      Math.max(2, Math.min(98, curY + jitterY))
    ]);
    curX += (cx - curX) / (steps - i);
    curY += (cy - curY) / (steps - i);
  }
  points.push([cx, cy]);
  return points;
}

function generatePersonDetection(cameraId: string): Detection {
  const objId = `Person #${rand(1, 25)}`;
  const inZone = Math.random() < 0.25;
  const loitering = inZone && Math.random() < 0.5;
  const behaviours: import('../../types').BehaviourLabel[] = [
    'NORMAL_TRANSIT', 'RUNNING', 'CIRCLING', 'PACING', 'ERRATIC_MOVEMENT', 'STATIONARY'
  ];
  const zoneBehaviours: import('../../types').BehaviourLabel[] = [
    'RUNNING', 'CIRCLING', 'PACING', 'ERRATIC_MOVEMENT'
  ];
  const behaviour = inZone ? pick(zoneBehaviours) : pick(behaviours);

  const bx = rand(5, 75);
  const by = rand(10, 50);
  const bw = rand(8, 16);
  const bh = rand(30, 55);
  const cx = bx + bw / 2;
  const cy = by + bh / 2;

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
      x: bx,
      y: by,
      w: bw,
      h: bh,
    },
    behaviour_label: behaviour,
    trajectory: generateTrajectory(cx, cy, behaviour),
    velocity: behaviour === 'RUNNING' ? rand(26, 42) : behaviour === 'STATIONARY' ? rand(0, 1) : rand(5, 18),
    tortuosity: behaviour === 'CIRCLING' ? Number((rand(28, 55) / 10).toFixed(1)) : 1.2,
    direction_changes: behaviour === 'PACING' ? rand(4, 8) : behaviour === 'ERRATIC_MOVEMENT' ? rand(3, 6) : rand(0, 2),
    timestamp: new Date().toISOString(),
    is_in_restricted_zone: inZone,
    loitering_duration: loitering ? rand(15, 90) : undefined,
  };
}

function generateVehicleDetection(cameraId: string): Detection {
  const bx = rand(10, 60);
  const by = rand(45, 65);
  const bw = rand(20, 35);
  const bh = rand(15, 28);
  const cx = bx + bw / 2;
  const cy = by + bh / 2;

  return {
    id: `det-${uid()}`,
    camera_id: cameraId,
    object_type: 'VEHICLE' as ObjectType,
    object_id: `Vehicle #${rand(1, 10)}`,
    confidence: rand(88, 98),
    event_type: 'VEHICLE_DETECTED' as EventType,
    bbox: {
      x: bx,
      y: by,
      w: bw,
      h: bh,
    },
    behaviour_label: 'NORMAL_TRANSIT',
    trajectory: generateTrajectory(cx, cy, 'NORMAL_TRANSIT'),
    velocity: rand(20, 45),
    tortuosity: 1.05,
    direction_changes: 0,
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
    ZONE_INTRUSION: `${det.object_id} entered ${det.zone || 'restricted zone'} (${det.behaviour_label || 'MOTION'}). Stayed for ${det.loitering_duration ?? 0}s. Confidence: ${det.confidence}%.`,
    LOITERING: `${det.object_id} detected loitering near perimeter for ${det.loitering_duration ?? 15}s.`,
    VEHICLE_DETECTED: `Unidentified vehicle (${det.object_id}) detected in monitored area.`,
    PERSON_DETECTED: `${det.object_id} detected in monitored zone. Confidence: ${det.confidence}%.`,
  };

  // Generate SVG data URI snapshot for rich mock preview
  const strokeColor = threatLevel === 'CRITICAL' ? '#ef4444' : threatLevel === 'HIGH' ? '#f97316' : '#eab308';
  const mockSvg = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" fill="%230b0f19"><rect width="640" height="360" fill="%230c101c"/><path d="M0 0h640v360H0z" fill="none" stroke="%231f293d" stroke-width="2"/><text x="20" y="35" font-family="monospace" font-size="14" font-weight="bold" fill="%2394a3b8">CAMERA: ${det.camera_id} • REALTIME AI FORENSIC SNAPSHOT</text><rect x="180" y="80" width="160" height="200" fill="none" stroke="${encodeURIComponent(strokeColor)}" stroke-width="3" stroke-dasharray="6,4"/><text x="185" y="72" font-family="monospace" font-size="13" font-weight="bold" fill="${encodeURIComponent(strokeColor)}">${threatLevel} | ${encodeURIComponent(det.object_id)}</text><text x="20" y="340" font-family="sans-serif" font-size="12" fill="%23cbd5e1">${encodeURIComponent(det.behaviour_label ? 'BEHAVIOR: ' + det.behaviour_label + ' • ' : '')}COORDINATES: X=${det.bbox.x}% Y=${det.bbox.y}%</text></svg>`;

  return {
    id: `alert-${uid()}`,
    alert_id: `ALERT-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${uid()}`,
    camera_id: det.camera_id,
    event_type: det.event_type,
    object_type: det.object_type,
    object_id: det.object_id,
    threat_level: threatLevel,
    reason: reasons[det.event_type] || `${det.event_type} detected by AI engine.`,
    confidence: det.confidence,
    bbox: det.bbox,
    behaviour_label: det.behaviour_label,
    snapshot_path: mockSvg,
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
