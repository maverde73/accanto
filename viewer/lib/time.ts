/** Italian relative time.
 *
 * Every timestamp shown in this app is an `occurred_at` from the backend: when
 * something actually happened, never when the server heard about it. A batch of
 * old samples arriving now must not read as current activity.
 */

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

const MONTHS = [
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];

export function clock(value: string | Date): string {
  const d = toDate(value);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "adesso", "4 minuti fa", "alle 12:34", "ieri alle 23:10", "il 3 giugno alle 09:00" */
export function relative(value: string | Date | null, now: Date = new Date()): string {
  if (value === null) return "mai";
  const d = toDate(value);
  const elapsed = now.getTime() - d.getTime();

  // A device clock running slightly fast must read as "just now", never as a
  // time in the future.
  if (elapsed < MINUTE) return "adesso";

  if (elapsed < HOUR) {
    const minutes = Math.floor(elapsed / MINUTE);
    return `${minutes} ${minutes === 1 ? "minuto" : "minuti"} fa`;
  }

  if (isSameDay(d, now)) return `alle ${clock(d)}`;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (isSameDay(d, yesterday)) return `ieri alle ${clock(d)}`;

  return `il ${d.getDate()} ${MONTHS[d.getMonth()]} alle ${clock(d)}`;
}

/** "2h 15m", "34 min" — for durations of silence. */
export function duration(fromValue: string | Date | null, now: Date = new Date()): string {
  if (fromValue === null) return "—";
  const elapsed = Math.max(0, now.getTime() - toDate(fromValue).getTime());
  const hours = Math.floor(elapsed / HOUR);
  const minutes = Math.floor((elapsed % HOUR) / MINUTE);
  if (hours === 0) return `${minutes} min`;
  return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
}

/** Whether a clock is fresh enough to still count as evidence. */
export function isFresh(
  value: string | Date | null,
  windowMinutes: number,
  now: Date = new Date(),
): boolean {
  if (value === null) return false;
  const elapsed = now.getTime() - toDate(value).getTime();
  return elapsed <= windowMinutes * MINUTE;
}

function toDate(value: string | Date): Date {
  return value instanceof Date ? value : new Date(value);
}

function pad(n: number): string {
  return n.toString().padStart(2, "0");
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}
