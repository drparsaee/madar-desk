// The calendar's "today" button follows the computer's local civil date.
// Stored task dates remain Gregorian ISO strings without timezone conversion.
export function localTodayISO(now = new Date()) {
  const pad = value => String(value).padStart(2, '0');
  return [now.getFullYear(), pad(now.getMonth() + 1), pad(now.getDate())].join('-');
}
