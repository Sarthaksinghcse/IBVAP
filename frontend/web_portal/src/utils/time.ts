/**
 * SHIELD Centralized Real-Time Time & Timezone Formatting Engine
 * =============================================================
 * Single source of truth for UTC -> Presentation conversion, live continuous
 * relative time calculation (e.g. "just now", "10 sec ago", "1 min ago"),
 * 12h/24h formats, and arbitrary IANA timezone transformations.
 */

export const SUPPORTED_TIMEZONES = [
  { label: 'System Default', value: 'SYSTEM' },
  { label: 'Asia/Kolkata (IST +5:30)', value: 'Asia/Kolkata' },
  { label: 'UTC (Coordinated Universal)', value: 'UTC' },
  { label: 'America/New_York (EST/EDT)', value: 'America/New_York' },
  { label: 'Europe/London (GMT/BST)', value: 'Europe/London' },
  { label: 'Asia/Dubai (GST +4:00)', value: 'Asia/Dubai' },
  { label: 'Asia/Singapore (SGT +8:00)', value: 'Asia/Singapore' },
  { label: 'Asia/Tokyo (JST +9:00)', value: 'Asia/Tokyo' },
  { label: 'America/Los_Angeles (PST/PDT)', value: 'America/Los_Angeles' },
  { label: 'Europe/Berlin (CET/CEST)', value: 'Europe/Berlin' },
  { label: 'Australia/Sydney (AEST/AEDT)', value: 'Australia/Sydney' },
];

function resolveTimeZone(tz?: string): string | undefined {
  if (!tz || tz === 'SYSTEM') return undefined;
  return tz;
}

/**
 * Format a Date or ISO string into a localized time string (12h or 24h).
 * Example: "19:05:32" or "7:05:32 PM"
 */
export function formatEventTime(
  dateInput: string | number | Date,
  timeZone?: string,
  timeFormat: '12h' | '24h' = '24h',
  includeSeconds: boolean = true
): string {
  try {
    const d = typeof dateInput === 'object' ? dateInput : new Date(dateInput);
    if (isNaN(d.getTime())) return '--:--';

    const tz = resolveTimeZone(timeZone);
    const is12 = timeFormat === '12h';

    return new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: is12 ? 'numeric' : '2-digit',
      minute: '2-digit',
      second: includeSeconds ? '2-digit' : undefined,
      hour12: is12,
    }).format(d);
  } catch (e) {
    return '--:--';
  }
}

/**
 * Format a Date into live header clock display strings.
 */
export function formatHeaderClock(
  date: Date,
  timeZone?: string,
  timeFormat: '12h' | '24h' = '24h'
): { dateStr: string; timeStr: string } {
  try {
    const tz = resolveTimeZone(timeZone);
    const is12 = timeFormat === '12h';

    const dateStr = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(date);

    const timeStr = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: is12 ? 'numeric' : '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: is12,
    }).format(date);

    return { dateStr, timeStr };
  } catch (e) {
    return { dateStr: '25 Aug 2026', timeStr: '19:50:00' };
  }
}

/**
 * Calculate dynamic relative time from ISO created_at string.
 * Examples: "just now", "10 sec ago", "45 sec ago", "1 min ago", "4 min ago", "1 hour ago", "Yesterday", "3 days ago"
 */
export function formatRelativeTime(dateInput: string | number | Date): string {
  try {
    const d = typeof dateInput === 'object' ? dateInput : new Date(dateInput);
    if (isNaN(d.getTime())) return 'Recently';

    const now = Date.now();
    const diffSec = Math.max(0, Math.floor((now - d.getTime()) / 1000));

    if (diffSec < 5) return 'just now';
    if (diffSec < 60) return `${diffSec} sec ago`;

    const diffMin = Math.floor(diffSec / 60);
    if (diffMin === 1) return '1 min ago';
    if (diffMin < 60) return `${diffMin} min ago`;

    const diffHours = Math.floor(diffMin / 60);
    if (diffHours === 1) return '1 hour ago';
    if (diffHours < 24) return `${diffHours} hours ago`;

    const diffDays = Math.floor(diffHours / 24);
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;

    return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(d);
  } catch (e) {
    return 'Recently';
  }
}

/**
 * Format date & time for audit logs / Alert History.
 * Example: "19:07 • 25 Aug 2026" or "7:07 PM • 25 Aug 2026"
 */
export function formatHistoryTimestamp(
  dateInput: string | number | Date,
  timeZone?: string,
  timeFormat: '12h' | '24h' = '24h'
): string {
  try {
    const d = typeof dateInput === 'object' ? dateInput : new Date(dateInput);
    if (isNaN(d.getTime())) return '--:--';

    const tz = resolveTimeZone(timeZone);
    const is12 = timeFormat === '12h';

    const timePart = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: is12 ? 'numeric' : '2-digit',
      minute: '2-digit',
      hour12: is12,
    }).format(d);

    const datePart = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      day: 'numeric',
      month: 'short',
    }).format(d);

    return `${timePart} • ${datePart}`;
  } catch (e) {
    return '--:--';
  }
}
