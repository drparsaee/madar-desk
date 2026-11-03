const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
const bundled = esbuild.buildSync({entryPoints: [path.join(root, 'src/labels.jsx')],
  bundle: true, platform: 'node', format: 'cjs', write: false, jsx: 'automatic',
  loader: {'.css': 'empty'}, external: ['react', 'react/jsx-runtime', 'lucide-react']}).outputFiles[0].text;
const loader = new Module(path.join(root, 'src/labels-test.cjs'), module);
loader.filename = path.join(root, 'src/labels-test.cjs');
loader.paths = Module._nodeModulePaths(root);
loader._compile(bundled, loader.filename);
const {normalizeTaskLabels, editTaskLabels, TaskLabelChip, LabelEditor, validLabelColor} = loader.exports;

test('normalizes legacy strings and transitional objects into string-compatible task labels', () => {
  const original = ['  طراحی  ', {name: 'ارسال', color: '#AABBCC'}, 'طراحی', '  ', null];
  const custom = {'طراحی': '#008877'};
  const result = normalizeTaskLabels(original, custom);
  assert.deepEqual(result, {labels: ['طراحی', 'ارسال'],
    labelColors: {'طراحی': '#008877', 'ارسال': '#aabbcc'}});
  assert.equal(original[0], '  طراحی  ');
  assert.deepEqual(custom, {'طراحی': '#008877'});
  assert.equal(validLabelColor('red'), null);
  assert.equal(validLabelColor('#123456'), '#123456');
});

test('assigns stable legacy colors, even for object-prototype-shaped names', () => {
  const first = normalizeTaskLabels(['نمونه', '__proto__']);
  const second = normalizeTaskLabels(['نمونه', '__proto__']);
  assert.deepEqual(first, second);
  assert.equal(first.labels[1], '__proto__');
  assert.match(first.labelColors['__proto__'], /^#[a-f\d]{6}$/);
  assert(Object.hasOwn(first.labelColors, '__proto__'));
  assert.equal(({}).polluted, undefined);
});

test('editing color, name, and removal preserves expected colors and prunes orphan colors', () => {
  const initial = {labels: ['بررسی', 'ارسال'], labelColors: {'بررسی': '#112233', 'ارسال': '#aabbcc'}};
  const colored = editTaskLabels(initial.labels, initial.labelColors, {action: 'color', index: 0, color: '#FF0000'});
  assert.equal(colored.labelColors['بررسی'], '#ff0000');
  const renamed = editTaskLabels(colored.labels, colored.labelColors, {action: 'rename', index: 0, name: 'فوری'});
  assert.deepEqual(renamed.labels, ['فوری', 'ارسال']);
  assert.equal(renamed.labelColors['فوری'], '#ff0000');
  assert(!Object.hasOwn(renamed.labelColors, 'بررسی'));
  const removed = editTaskLabels(renamed.labels, renamed.labelColors, {action: 'remove', index: 1});
  assert.deepEqual(removed, {labels: ['فوری'], labelColors: {'فوری': '#ff0000'}});
  assert.deepEqual(initial.labels, ['بررسی', 'ارسال']);
});

test('rejects duplicates, blanks, and invalid palette values without losing other labels', () => {
  const labels = ['مهم', 'ارسال'];
  const colors = {'مهم': '#ff0000', 'ارسال': '#00ff00'};
  assert.equal(editTaskLabels(labels, colors, {action: 'add', name: '  مهم  '}).error, 'duplicate');
  assert.equal(editTaskLabels(labels, colors, {action: 'rename', index: 0, name: 'ارسال'}).error, 'duplicate');
  assert.equal(editTaskLabels(labels, colors, {action: 'add', name: '   '}).error, 'empty');
  assert.equal(editTaskLabels(labels, colors, {action: 'color', index: 0, color: 'tomato'}).error, 'color');
  assert.deepEqual(editTaskLabels(labels, colors, {action: 'add', name: 'کیفیت', color: '#8899AA'}),
    {labels: ['مهم', 'ارسال', 'کیفیت'], labelColors: {'مهم': '#ff0000', 'ارسال': '#00ff00', 'کیفیت': '#8899aa'}});
  assert.deepEqual(labels, ['مهم', 'ارسال']);
});

test('renders a unified color picker per label with accessible freeform inputs', () => {
  const html = renderToStaticMarkup(React.createElement(LabelEditor, {
    labels: ['کار', 'مهم'], colors: {'کار': '#123456'}, onChange: () => {}}));
  assert.equal((html.match(/type="color"/g) || []).length, 3);
  assert.equal((html.match(/class="madar-common-colors__details"/g) || []).length, 3);
  assert.match(html, /aria-label="رنگ برچسب کار"/);
  assert.match(html, /aria-label="نام برچسب جدید"/);
  assert.match(html, /aria-label="افزودن برچسب"/);
  assert.match(html, /value="#123456"/);
  const chip = renderToStaticMarkup(React.createElement(TaskLabelChip, {label: 'کار', colors: {'کار': '#123456'}}));
  assert.match(chip, /--label-color:#123456/);
  const disabled = renderToStaticMarkup(React.createElement(LabelEditor, {labels: ['کار'], disabled: true}));
  assert(!disabled.includes('نام برچسب جدید'));
  assert.match(disabled, /disabled=""/);
});
