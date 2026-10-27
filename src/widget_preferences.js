// Clock/date appearance is a visual preference, never a source for event timestamps.
export const WIDGET_THEMES = Object.freeze(['light', 'dark', 'aurora']);
export const WIDGET_SIZES = Object.freeze(['compact', 'regular', 'large']);
export const WIDGET_PLACEMENTS = Object.freeze(['topbar', 'floating', 'top-left', 'top-right', 'bottom-left', 'bottom-right']);

export const DEFAULT_WIDGET_SETTINGS = Object.freeze({
  mode: 'both',
  theme: 'aurora',
  size: 'regular',
  hourFormat: '24',
  dateFormat: 'full',
  placement: 'topbar',
  position: Object.freeze({x: 0.83, y: 0.12}),
});

const choose = (value, allowed, fallback) => allowed.includes(value) ? value : fallback;
const finiteNumber = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
export const clampUnit = value => Math.max(0, Math.min(1, finiteNumber(value) ?? 0));

export function normalizeWidgetSettings(value) {
  const raw = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const legacyMode = typeof value === 'string' ? value : raw.mode;
  const position = raw.position && typeof raw.position === 'object' && !Array.isArray(raw.position) ? raw.position : {};
  return {
    mode: choose(legacyMode, ['both', 'clock', 'date', 'hidden'], DEFAULT_WIDGET_SETTINGS.mode),
    theme: choose(raw.theme, WIDGET_THEMES, DEFAULT_WIDGET_SETTINGS.theme),
    size: choose(raw.size, WIDGET_SIZES, DEFAULT_WIDGET_SETTINGS.size),
    hourFormat: choose(raw.hourFormat, ['12', '24'], DEFAULT_WIDGET_SETTINGS.hourFormat),
    dateFormat: choose(raw.dateFormat, ['compact', 'full'], DEFAULT_WIDGET_SETTINGS.dateFormat),
    placement: choose(raw.placement, WIDGET_PLACEMENTS, DEFAULT_WIDGET_SETTINGS.placement),
    position: {
      x: finiteNumber(position.x) === null ? DEFAULT_WIDGET_SETTINGS.position.x : clampUnit(position.x),
      y: finiteNumber(position.y) === null ? DEFAULT_WIDGET_SETTINGS.position.y : clampUnit(position.y),
    },
  };
}

// Position is normalized over available travel, excluding the widget's dimensions.
// This guarantees that even the last pixel of the widget remains on-screen.
export function widgetTravelArea(viewport, widget, margin = 12) {
  const width = Math.max(0, finiteNumber(viewport?.width) ?? 0);
  const height = Math.max(0, finiteNumber(viewport?.height) ?? 0);
  const widgetWidth = Math.max(0, finiteNumber(widget?.width) ?? 0);
  const widgetHeight = Math.max(0, finiteNumber(widget?.height) ?? 0);
  const insetX = Math.min(Math.max(0, margin), Math.max(0, (width - widgetWidth) / 2));
  const insetY = Math.min(Math.max(0, margin), Math.max(0, (height - widgetHeight) / 2));
  return {
    left: insetX,
    top: insetY,
    width: Math.max(0, width - widgetWidth - 2 * insetX),
    height: Math.max(0, height - widgetHeight - 2 * insetY),
  };
}

export function widgetPositionToPixels(position, viewport, widget, margin = 12) {
  const area = widgetTravelArea(viewport, widget, margin);
  return {
    left: Math.round(area.left + area.width * clampUnit(position?.x)),
    top: Math.round(area.top + area.height * clampUnit(position?.y)),
  };
}

export function widgetPixelsToPosition(pixels, viewport, widget, margin = 12) {
  const area = widgetTravelArea(viewport, widget, margin);
  return {
    x: area.width > 0 ? clampUnit(((finiteNumber(pixels?.left) ?? area.left) - area.left) / area.width) : 0.5,
    y: area.height > 0 ? clampUnit(((finiteNumber(pixels?.top) ?? area.top) - area.top) / area.height) : 0.5,
  };
}

export function nudgeWidgetPosition(position, direction, step = 0.03) {
  const delta = Math.max(0, finiteNumber(step) ?? 0.03);
  const x = clampUnit(position?.x);
  const y = clampUnit(position?.y);
  switch (direction) {
    case 'ArrowLeft': return {x: clampUnit(x - delta), y};
    case 'ArrowRight': return {x: clampUnit(x + delta), y};
    case 'ArrowUp': return {x, y: clampUnit(y - delta)};
    case 'ArrowDown': return {x, y: clampUnit(y + delta)};
    default: return {x, y};
  }
}
