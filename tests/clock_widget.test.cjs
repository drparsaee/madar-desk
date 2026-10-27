const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
const css = fs.readFileSync(path.join(root, 'src/clock_widget.css'), 'utf8');
const jsx = fs.readFileSync(path.join(root, 'src/clock_widget.jsx'), 'utf8');
const bundled = esbuild.buildSync({
  entryPoints:[path.join(root, 'src/clock_widget.jsx')],
  bundle:true, platform:'node', format:'cjs', write:false, jsx:'automatic',
  loader:{'.css':'empty'}, external:['react','react-dom','react/jsx-runtime'],
}).outputFiles[0].text;
const loaded = new Module(path.join(root,'src/clock-widget-test.cjs'), module);
loaded.filename = path.join(root,'src/clock-widget-test.cjs');
loaded.paths = Module._nodeModulePaths(root);
loaded._compile(bundled,loaded.filename);
const {ClockWidget,formatClockParts,WidgetSettings} = loaded.exports;

test('Persian date displays weekday, day, month, year in requested order', () => {
  const date = new Date(2026, 9, 27, 23, 2, 47);
  const result = formatClockParts(date, 'jalali');
  assert.equal(result.date, 'سه‌شنبه، ۵ آبان ۱۴۰۵');
  assert.equal(result.hour, '23');
  assert.equal(result.minute, '02');
  assert.equal(formatClockParts(date, 'gregorian').date,'سه‌شنبه، ۲۷ اکتبر ۲۰۲۶');
  assert.equal(formatClockParts(new Date(2026,9,27,0,7,58)).hour,'00');
  assert.equal(formatClockParts(new Date(2026,9,27,0,7,58)).minute,'07');
});

test('fixed flip clock shows HH:MM and date without seconds or adjacent controls', () => {
  const html = renderToStaticMarkup(React.createElement(ClockWidget,{calendar:'jalali'}));
  assert.match(html,/clock-widget--fixed/);
  assert.match(html,/clock-widget__tiles/);
  assert.match(html,/data-unit="hour"/);
  assert.match(html,/data-unit="minute"/);
  assert.match(html,/clock-widget__date/);
  assert.match(html,/role="timer"/);
  assert.match(html,/aria-live="off"/);
  assert.equal((html.match(/clock-widget__flip-page/g)||[]).length,2);
  assert.doesNotMatch(html,/<button|<select|<input|<details|aria-haspopup|clock-widget__handle|clock-widget__trigger/);
  assert.doesNotMatch(jsx,/setInterval\(.*1000\)/);
  assert.match(jsx,/60_000 - Date\.now\(\) % 60_000/);
});

test('stale settings cannot hide, move, or resize the new fixed clock', () => {
  const old = renderToStaticMarkup(React.createElement(ClockWidget,{
    calendar:'jalali',settings:{mode:'hidden',placement:'floating',theme:'aurora',size:'compact'},
    onChange:()=>{},onOpenSettings:()=>{},
  }));
  const fresh = renderToStaticMarkup(React.createElement(ClockWidget,{calendar:'jalali'}));
  assert.equal(old,fresh);
  assert.equal(renderToStaticMarkup(React.createElement(WidgetSettings,{settings:{mode:'both'}})), '');
  assert.doesNotMatch(jsx,/createPortal|onPointerDown|onPointerMove|onPointerUp|nudgeWidgetPosition/);
});

test('flip tiles are larger and visually split while small screens retain a bounded size',()=>{
  assert.match(css,/\.clock-widget--fixed \.clock-widget__flip-page\s*\{/);
  assert.match(css,/font-size:38px/);
  assert.match(css,/\.clock-widget--fixed \.clock-widget__flip-page::after/);
  assert.match(css,/@media \(max-width:480px\)/);
  assert.match(css,/pointer-events:none/);
});
