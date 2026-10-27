// Visual preference only. Never changes event timestamps or accounting dates.
export const CLOCK_WIDGET_MODES = Object.freeze(['both', 'clock', 'date', 'hidden']);

export function normalizeClockWidget(value) {
  return CLOCK_WIDGET_MODES.includes(value) ? value : 'both';
}

export const CLOCK_WIDGET_CHOICES = Object.freeze([
  {id:'both', label:'ساعت و تاریخ'},
  {id:'clock', label:'فقط ساعت'},
  {id:'date', label:'فقط تاریخ'},
  {id:'hidden', label:'مخفی'},
]);
