const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const React = require('react');
const esbuild = require('esbuild');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
const code = esbuild.buildSync({
  entryPoints: [path.join(root, 'src', 'planner.jsx')], bundle: true,
  platform: 'node', format: 'cjs', write: false, jsx: 'automatic',
  loader: {'.css': 'empty'},
  external: ['react', 'react/jsx-runtime', 'lucide-react']
}).outputFiles[0].text;
const compiled = new Module(path.join(root, 'src', 'planner-picker-test.cjs'), module);
compiled.filename = path.join(root, 'src', 'planner-picker-test.cjs');
compiled.paths = Module._nodeModulePaths(root);
compiled._compile(code, compiled.filename);
const {PlannerDatePicker, PlannerTimePicker} = compiled.exports;

const elementsOf = (node, type) => {
  if (!node || typeof node !== 'object') return [];
  const own = node.type === type ? [node] : [];
  return own.concat(React.Children.toArray(node.props?.children).flatMap(child => elementsOf(child, type)));
};

test('Jalali and Gregorian date pickers display the same persisted ISO date with no text input', () => {
  const iso = '2026-10-27';
  const jalali = renderToStaticMarkup(React.createElement(PlannerDatePicker, {
    value: iso, calendar: 'jalali', label: 'تاریخ انجام', onChange() {}
  }));
  const gregorian = renderToStaticMarkup(React.createElement(PlannerDatePicker, {
    value: iso, calendar: 'gregorian', label: 'تاریخ انجام', onChange() {}
  }));
  assert.match(jalali, /شمسی/);
  assert.match(gregorian, /میلادی/);
  assert.match(jalali, /۱۴۰۵/);
  assert.match(gregorian, /۲۰۲۶/);
  assert.match(jalali, /aria-expanded="false"/);
  assert.match(jalali, /پاک کردن تاریخ انجام/);
  assert.doesNotMatch(jalali + gregorian, /<input\b|type="date"/);
});

test('hour/minute selects permit exact minute precision, disable without due date, and allow clearing', () => {
  const updates = [];
  const withTime = PlannerTimePicker({value: '09:37', onChange: value => updates.push(value)});
  const [hours, minutes] = elementsOf(withTime, 'select');
  assert.equal(hours.props.value, '09');
  assert.equal(minutes.props.value, '37');
  assert.equal(elementsOf(withTime, 'option').length, 85);
  assert.equal(elementsOf(withTime, 'input').length, 0);
  minutes.props.onChange({target: {value: '59'}});
  hours.props.onChange({target: {value: '18'}});
  hours.props.onChange({target: {value: ''}});
  assert.deepEqual(updates, ['09:59', '18:37', '']);
  const disabled = PlannerTimePicker({value: '', disabled: true, onChange() {}});
  assert.equal(disabled.props.disabled, true);
  const [disabledHours, disabledMinutes] = elementsOf(disabled, 'select');
  assert.equal(disabledHours.props.value, '');
  assert.equal(disabledMinutes.props.disabled, true);
});
