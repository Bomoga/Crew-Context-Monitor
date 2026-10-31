/** "1 h 59 min", "42 min", "30 s": a duration in seconds as plain words. */
export function formatDuration(seconds: number): string {
  const total = Math.max(Math.round(seconds), 0);
  if (total < 60) return `${total} s`;
  const minutes = Math.round(total / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

/** HH:MM in UTC from unix seconds; the monitor works in UTC. */
export function clockTime(t: number): string {
  return new Date(t * 1000).toISOString().slice(11, 16);
}

/** HH:MM:SS in UTC from unix seconds. */
export function clockTimeSeconds(t: number): string {
  return new Date(t * 1000).toISOString().slice(11, 19);
}

/** A reading for display: whole numbers stay whole, others get one decimal; null is a dash. */
export function formatValue(value: number | null): string {
  if (value === null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
