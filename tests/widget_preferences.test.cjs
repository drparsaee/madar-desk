const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.resolve(__dirname, '../src/widget_preferences.js'), 'utf8');
const preferences = import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

test('widget settings accept legacy mode and normalize invalid values without mutating input', async () => {
  const {normalizeWidgetSettings} = await preferences;
  assert.equal(normalizeWidgetSettings('date').mode, 'date');
  assert.equal(normalizeWidgetSettings('unknown').mode, 'both');
  const input = {mode: 'clock', theme: 'aurora', placement: 'floating', size: 'large',
    dateFormat: 'compact', hourFormat: '12', position: {x: 1.8, y: -4}, unknown: true};
  const normalized = normalizeWidgetSettings(input);
  assert.deepEqual(normalized, {
    mode: 'clock', theme: 'aurora', placement: 'floating', size: 'large', dateFormat: 'compact',
    hourFormat: '12', position: {x: 1, y: 0},
  });
  assert.deepEqual(input.position, {x: 1.8, y: -4});
  assert.deepEqual(normalizeWidgetSettings({mode: 'hidden', theme: '__proto__',
    hourFormat: '33', placement: 'offscreen', position: {x: '1', y: Infinity}}).position,
  {x: 0.83, y: 0.12});
  assert.equal(normalizeWidgetSettings(null).mode, 'both');
});

test('normalized settings are JSON-safe and have distinct nested position objects', async () => {
  const {normalizeWidgetSettings} = await preferences;
  const a = normalizeWidgetSettings({position: {x: NaN, y: -Infinity}});
  const b = normalizeWidgetSettings({});
  assert.notEqual(a.position, b.position);
  assert.deepEqual(JSON.parse(JSON.stringify(a)), a);
  assert.deepEqual(a.position, {x: 0.83, y: 0.12});
});

test('floating positions map to viewport-safe pixels in either direction', async () => {
  const {widgetPositionToPixels, widgetPixelsToPosition} = await preferences;
  const viewport = {width: 1200, height: 800};
  const widget = {width: 256, height: 136};
  assert.deepEqual(widgetPositionToPixels({x: -9, y: -1}, viewport, widget), {left: 12, top: 12});
  assert.deepEqual(widgetPositionToPixels({x: 5, y: 3}, viewport, widget), {left: 932, top: 652});
  const saved = {x: .35, y: .65};
  const pixels = widgetPositionToPixels(saved, viewport, widget);
  const recovered = widgetPixelsToPosition(pixels, viewport, widget);
  assert.ok(Math.abs(recovered.x - saved.x) < .002);
  assert.ok(Math.abs(recovered.y - saved.y) < .002);
  assert.deepEqual(widgetPixelsToPosition({left: -2000, top: 1500}, viewport, widget), {x: 0, y: 1});
});

test('widget stays reachable in tiny viewports and pathological input', async () => {
  const {widgetPositionToPixels, widgetPixelsToPosition} = await preferences;
  const viewport = {width: 160, height: 100}, widget = {width: 260, height: 170};
  assert.deepEqual(widgetPositionToPixels({x: 1, y: 1}, viewport, widget), {left: 0, top: 0});
  assert.deepEqual(widgetPixelsToPosition({left: 42, top: -2}, viewport, widget), {x: .5, y: .5});
  const point = widgetPositionToPixels({x: Infinity, y: NaN}, {width: 0, height: 0}, widget);
  assert.deepEqual(point, {left: 0, top: 0});
});

test('keyboard movement clamps, supports step variation and ignores unrelated keys', async () => {
  const {nudgeWidgetPosition} = await preferences;
  assert.deepEqual(nudgeWidgetPosition({x: .98, y: .03}, 'ArrowRight'), {x: 1, y: .03});
  assert.deepEqual(nudgeWidgetPosition({x: .98, y: .03}, 'ArrowUp', .1), {x: .98, y: 0});
  assert.deepEqual(nudgeWidgetPosition({x: .98, y: .03}, 'ArrowLeft', .1), {x: .88, y: .03});
  assert.deepEqual(nudgeWidgetPosition({x: .98, y: .03}, 'Escape'), {x: .98, y: .03});
});
