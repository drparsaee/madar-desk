'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/floating_labels.js'), 'utf8');
const modulePromise = import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function classes() {
  const items = new Set();
  return {
    add: name => items.add(name),
    remove: name => items.delete(name),
    contains: name => items.has(name),
    toggle(name, force) { if (force) items.add(name); else items.delete(name); },
  };
}
function style() {
  const values = new Map();
  return {
    setProperty: (key, value) => values.set(key, value),
    removeProperty: key => values.delete(key),
    getPropertyValue: key => values.get(key),
  };
}
function field(attrs = {}) {
  const attributes = {...attrs};
  const control = {
    tagName: 'INPUT', type: 'text', value: '', disabled: false,
    labels: [], isConnected: true,
    classList: classes(), style: style(),
    getAttribute: key => attributes[key] ?? null,
    setAttribute: (key, value) => { attributes[key] = value; },
    removeAttribute: key => { delete attributes[key]; },
    closest: () => null,
    matches: () => false,
    getBoundingClientRect: () => ({left:30, right:230, top:30, bottom:72, width:200, height:42}),
  };
  return control;
}

test('candidate filtering skips non-typable controls, but covers selects and textarea', async () => {
  const {isFloatingCandidate} = await modulePromise;
  const control = field();
  assert.equal(isFloatingCandidate(control), true);
  control.type = 'checkbox';
  assert.equal(isFloatingCandidate(control), false);
  control.type = 'file';
  assert.equal(isFloatingCandidate(control), false);
  control.tagName = 'SELECT';
  assert.equal(isFloatingCandidate(control), true);
  control.tagName = 'TEXTAREA';
  assert.equal(isFloatingCandidate(control), true);
});

test('native label is favored over option text, then aria and placeholder', async () => {
  const {floatingLabelText} = await modulePromise;
  const control = field({placeholder:'نامشخص'});
  const native = {
    childNodes: [
      {nodeType:3, textContent:'شرح  فروش'},
      control,
    ],
  };
  control.labels = [native];
  assert.equal(floatingLabelText(control), 'شرح فروش');
  control.labels = [];
  assert.equal(floatingLabelText(control), 'نامشخص');
  control.setAttribute('aria-label', 'مبلغ پرداخت');
  assert.equal(floatingLabelText(control), 'مبلغ پرداخت');
  control.setAttribute('aria-labelledby', 'amount-label');
  assert.equal(floatingLabelText(control, {
    getElementById: id => id === 'amount-label' ? {textContent:'عنوان مبلغ'} : null,
  }), 'عنوان مبلغ');
});

test('captions are outside React tree, survive rerenders and cleanup correctly', async () => {
  const {installFloatingLabels} = await modulePromise;
  const listeners = new Map();
  const root = {
    nodeType:1,
    controls: [],
    querySelectorAll() { return this.controls; },
    addEventListener(type, fn) { listeners.set(type, fn); },
    removeEventListener(type) { listeners.delete(type); },
  };
  let observer;
  const view = {
    innerWidth:800, innerHeight:600,
    MutationObserver: class {
      constructor(callback) { observer = callback; }
      observe() {}
      disconnect() {}
    },
    ResizeObserver: class { observe() {} unobserve() {} disconnect() {} },
    requestAnimationFrame: callback => callback(),
    getComputedStyle: () => ({fontSize:'12px'}),
    addEventListener() {}, removeEventListener() {},
  };
  const bodyChildren = [];
  const doc = {
    defaultView:view,
    querySelector: () => null,
    body: {appendChild: node => {bodyChildren.push(node);}},
    createElement: () => ({
      className:'', classList:classes(), style:style(),
      setAttribute() {}, appendChild(child) {this.children ||= []; this.children.push(child);},
      remove() {this.removed = true;},
    }),
    addEventListener() {}, removeEventListener() {},
  };
  root.ownerDocument = doc;
  const control = field({placeholder:'عنوان کار'});
  control.parentElement = {children: [control]};
  control.ownerDocument = doc;
  root.controls = [control];
  const dispose = installFloatingLabels(root);
  assert.equal(bodyChildren.length, 1, 'only the external portal is appended');
  assert.equal(bodyChildren[0].children.length, 1);
  assert.deepEqual(control.parentElement.children, [control], 'React node hierarchy unchanged');
  assert.equal(control.getAttribute('aria-label'), 'عنوان کار');

  control.value = 'پروژه مدار';
  listeners.get('input')({target:control, type:'input'});
  assert.equal(bodyChildren[0].children[0].classList.contains('madar-fl-raised'), true);
  observer([{type:'childList', addedNodes:[{nodeType:1,matches:()=>true}], removedNodes:[]}]);
  assert.equal(bodyChildren[0].children.length, 1, 'no duplicate on React rerender');

  root.controls = [];
  control.isConnected = false;
  observer([{type:'childList', addedNodes:[], removedNodes:[{nodeType:1,matches:()=>true}]}]);
  assert.equal(bodyChildren[0].children[0].removed, true);
  assert.equal(control.getAttribute('aria-label'), null);
  dispose();
  assert.equal(bodyChildren[0].removed, true);
  assert.equal(listeners.size, 0);
});
