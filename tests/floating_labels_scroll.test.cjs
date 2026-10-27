'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/floating_labels.js'), 'utf8');
const styles = fs.readFileSync(path.join(__dirname, '../src/floating_labels.css'), 'utf8');
const modulePromise = import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

const rect = (left, top, width, height) => ({
  left, top, width, height, right:left + width, bottom:top + height,
});
function classList() {
  const names = new Set();
  return {
    add: name => names.add(name),
    remove: name => names.delete(name),
    contains: name => names.has(name),
    toggle(name, selected) {if (selected) names.add(name); else names.delete(name);},
  };
}
function element(name = 'DIV') {
  const props = new Map();
  return {
    tagName:name, classList:classList(), children:[], attributes:new Map(),
    style:{
      setProperty: (key, value) => props.set(key, value),
      removeProperty: key => props.delete(key),
      getPropertyValue: key => props.get(key),
    },
    setAttribute(name, value) {this.attributes.set(name, value);},
    getAttribute(name) {return this.attributes.get(name) ?? null;},
    removeAttribute(name) {this.attributes.delete(name);},
    appendChild(child) {this.children.push(child);},
    remove() {this.removed = true;},
  };
}

function harness() {
  const docListeners = new Map();
  const viewListeners = new Map();
  const rootListeners = new Map();
  const frames = [];
  let observer;
  let scrollTop = 0;
  const root = element();
  const outer = element();
  const inner = element();
  outer.overflowY = 'auto';
  outer.getBoundingClientRect = () => rect(30, 90, 380, 230);
  outer.clientWidth = 380;
  outer.clientHeight = 230;
  inner.overflowY = 'auto';
  inner.overflowX = 'auto';
  inner.getBoundingClientRect = () => rect(40, 130, 320, 130);
  inner.clientWidth = 320;
  inner.clientHeight = 130;
  inner.parentElement = outer;
  const nativeLabel = element('LABEL');
  const control = element('INPUT');
  control.type = 'text';
  control.value = '';
  control.disabled = false;
  control.isConnected = true;
  control.setAttribute('placeholder', 'نام مرحله');
  control.labels = [nativeLabel];
  nativeLabel.childNodes = [{nodeType:3,textContent:'نام مرحله'},control];
  nativeLabel.children = [control];
  nativeLabel.parentElement = inner;
  control.parentElement = nativeLabel;
  control.closest = selector => selector === 'label' ? nativeLabel : null;
  control.matches = () => false;
  control.getBoundingClientRect = () => rect(55, 170 - scrollTop, 280, 42);
  root.querySelectorAll = () => [control];
  root.addEventListener = (name, listener) => rootListeners.set(name, listener);
  root.removeEventListener = name => rootListeners.delete(name);
  const view = {
    innerWidth: 550, innerHeight: 440,
    getComputedStyle: el => ({
      fontSize:'12px',
      overflowX:el.overflowX || 'visible',
      overflowY:el.overflowY || 'visible',
    }),
    requestAnimationFrame: fn => {frames.push(fn); return frames.length;},
    MutationObserver: class {
      constructor(fn) {observer = fn;}
      observe() {}
      disconnect() {}
    },
    ResizeObserver: class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
    addEventListener: (name, fn) => viewListeners.set(name, fn),
    removeEventListener: name => viewListeners.delete(name),
  };
  const body = element('BODY');
  const doc = {
    defaultView:view,
    body,
    querySelector:()=>null,
    createElement: tag => element(tag.toUpperCase()),
    addEventListener: (name, fn) => docListeners.set(name, fn),
    removeEventListener: name => docListeners.delete(name),
  };
  root.ownerDocument = doc;
  control.ownerDocument = doc;
  function flush() {
    let calls = 0;
    while (frames.length) {
      assert.ok(++calls < 30, 'no runaway rAF scheduling loop');
      frames.shift()();
    }
  }
  function scroll(value) {
    scrollTop = value;
    docListeners.get('scroll')?.({type:'scroll',target:inner});
  }
  return {doc,root,control,nativeLabel,inner,outer,body,
    scroll,flush,observer: () => observer, rootListeners,docListeners,viewListeners};
}

test('fixed captions never animate top while an overflow container scrolls', () => {
  const transitions = Array.from(styles.matchAll(/transition:\s*([^;]+);/g)).map(match => match[1]);
  assert.ok(transitions.some(value => value.includes('font-size')));
  assert.ok(transitions.every(value => !/(?:^|[,\s])top\s/.test(value)), 'top interpolation causes floating captions to trail rows');
});

test('inner scroll immediately hides portal and RAF updates position or clips caption', async () => {
  const {installFloatingLabels} = await modulePromise;
  const h = harness();
  const dispose = installFloatingLabels(h.root);
  h.flush();
  const layer = h.body.children[0];
  const caption = layer.children[0];
  assert.equal(caption.hidden, false);
  assert.equal(caption.style.getPropertyValue('--madar-fl-top-y'), '177px');
  assert.equal(h.control.getAttribute('aria-label'), null, 'native label is retained, not overridden');
  assert.equal(h.nativeLabel.children[0], h.control, 'React-owned element stays in its original label');
  h.scroll(60); // field top 110, above inner clipped region beginning at 130
  assert.equal(layer.style.visibility, 'hidden', 'no stale overlay before layout frame');
  h.flush();
  assert.equal(layer.style.visibility, '', 'portal returns after recomputing all field positions');
  assert.equal(caption.hidden, true, 'partially clipped input cannot paint caption over another row');
  h.scroll(20);
  h.flush();
  assert.equal(caption.hidden, false);
  assert.equal(caption.style.getPropertyValue('--madar-fl-top-y'), '157px');
  assert.equal(caption.style.getPropertyValue('--madar-fl-right'), '224px', 'RTL right offset follows viewport');
  h.scroll(300);
  h.flush();
  assert.equal(caption.hidden, true, 'scrolled completely out of view');
  dispose();
  assert.equal(layer.removed, true);
  assert.equal(h.docListeners.size, 0, 'scroll capture event listener cleaned up');
  assert.equal(h.viewListeners.size, 0, 'resize event listener cleaned up');
});

test('scroll boundaries include horizontal clipping and nested outer containers', async () => {
  const {isFieldFullyVisible} = await modulePromise;
  const h = harness();
  const view = h.doc.defaultView;
  assert.equal(isFieldFullyVisible(h.control,h.control.getBoundingClientRect(),view),true);
  h.inner.clientWidth = 180; // clip by horizontal overflow inside a right-to-left form
  assert.equal(isFieldFullyVisible(h.control,h.control.getBoundingClientRect(),view),false);
  h.inner.clientWidth = 320;
  h.outer.clientHeight = 80;
  assert.equal(isFieldFullyVisible(h.control,h.control.getBoundingClientRect(),view),false);
  h.outer.clientHeight = 230;
  h.control.getBoundingClientRect = () => rect(55,390,280,42);
  assert.equal(isFieldFullyVisible(h.control,h.control.getBoundingClientRect(),view),false);
});

test('repeated mutation scans settle and do not replace native label semantics', async () => {
  const {installFloatingLabels} = await modulePromise;
  const h = harness();
  const dispose = installFloatingLabels(h.root);
  h.flush();
  h.observer()([{type:'attributes',attributeName:'aria-label'}]);
  h.flush();
  assert.equal(h.body.children[0].children.length,1,'no new caption on a repeated scan');
  assert.equal(h.control.getAttribute('aria-label'),null);
  assert.equal(h.nativeLabel.children[0],h.control);
  dispose();
});
