'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const {pathToFileURL} = require('node:url');

const chromePaths = process.platform === 'win32'
  ? ['C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe']
  : ['/usr/bin/chromium', '/usr/bin/google-chrome', '/usr/bin/chromium-browser'];
const chrome = chromePaths.find(candidate => fs.existsSync(candidate));
const jsSource = fs.readFileSync(path.join(__dirname, '../src/floating_labels.js'), 'utf8');
const cssSource = fs.readFileSync(path.join(__dirname, '../src/floating_labels.css'), 'utf8');

test('real Chromium DOM: a nested scrolling dialog never leaves drifting captions', {skip:!chrome}, () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'madar-fl-dom-'));
  try {
    const fixture = `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>
body{margin:0;overflow:hidden;font:14px sans-serif}
.overlay{width:440px;margin:10px;background:#edf0f6;padding:8px}
.dialog{height:240px;overflow:hidden;background:white;padding:4px}
.dialog-body{height:100%;overflow-y:auto;padding:8px}
.dialog-body label{display:flex;flex-direction:column;gap:8px}
.dialog-body input{width:240px;height:42px;border:1px solid #aaa}
${cssSource}
</style></head><body><div id="root"><div class="overlay"><div class="dialog">
<div class="dialog-body" id="pane"><div style="height:98px"></div>
<label id="native-label">نام مرحله<input id="field" placeholder="نام مرحله"></label>
<div style="height:350px"></div></div></div></div></div>
<script type="module">
${jsSource}
// Headless --virtual-time-budget can stop compositor animation frames after
// parsing. Keep the real DOM/scroll layout but drive RAF via virtual timers.
window.requestAnimationFrame = callback => setTimeout(() => callback(performance.now()), 0);
const frame = () => new Promise(resolve => setTimeout(resolve, 100));
(async () => {
  const dispose = installFloatingLabels(document);
  await frame();
  const field = document.getElementById('field');
  const pane = document.getElementById('pane');
  const caption = document.querySelector('.madar-fl-caption');
  const initialTop = parseFloat(caption?.style.getPropertyValue('--madar-fl-top-y') || 'NaN');
  const initialVisible = caption && !caption.hidden;
  const nativeAssociation = field.labels?.[0] === document.getElementById('native-label') &&
    !field.hasAttribute('aria-label');
  pane.scrollTop = 180;
  // Chromium's virtual-time headless mode does not dispatch compositor scroll
  // events. Dispatch the same bubbling/capture path against the real DOM.
  pane.dispatchEvent(new Event('scroll'));
  await frame();
  const clippedHidden = caption.hidden;
  pane.scrollTop = 30;
  pane.dispatchEvent(new Event('scroll'));
  await frame();
  const repositioned = !caption.hidden &&
    Math.abs(parseFloat(caption.style.getPropertyValue('--madar-fl-top-y')) -
      (field.getBoundingClientRect().top + 7)) < 1;
  const moved = parseFloat(caption.style.getPropertyValue('--madar-fl-top-y')) < initialTop;
  document.getElementById('native-label').click();
  const clickFocusWorks = document.activeElement === field;
  const transition = getComputedStyle(caption).transitionProperty;
  dispose();
  document.body.dataset.results = encodeURIComponent(JSON.stringify({
    initialVisible,nativeAssociation,clippedHidden,repositioned,moved,clickFocusWorks,
    noTopAnimation:!transition.split(',').map(v => v.trim()).includes('top'),
    disposed:!document.querySelector('.madar-fl-layer'),
  }));
})().catch(error => {document.body.dataset.results = encodeURIComponent(JSON.stringify({
  error:String(error),html:document.body.innerHTML.slice(-900),
  inputs:document.querySelectorAll('input').length,
  captions:document.querySelectorAll('.madar-fl-caption').length,
}));});
</script></body></html>`;
    const file = path.join(directory, 'nested-scroll.html');
    fs.writeFileSync(file, fixture, 'utf8');
    const result = spawnSync(chrome, [
      '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
      '--disable-extensions', '--virtual-time-budget=3000', '--window-size=900,700',
      `--user-data-dir=${path.join(directory,'profile')}`, '--dump-dom',
      pathToFileURL(file).href,
    ], {timeout:18000, maxBuffer:5*1024*1024, encoding:'utf8'});
    assert.equal(result.error, undefined, `Chromium failed to start: ${result.error?.message}`);
    assert.equal(result.status, 0, `Chromium exited ${result.status}: ${result.stderr?.slice(0,500)}`);
    const match = result.stdout.match(/data-results="([^"]+)"/);
    assert.ok(match, `Chromium did not complete DOM scenario: ${result.stdout.slice(-1500)} stderr=${result.stderr?.slice(-400)}`);
    const report = JSON.parse(decodeURIComponent(match[1]));
    assert.deepEqual(report, {
      initialVisible:true,nativeAssociation:true,clippedHidden:true,
      repositioned:true,moved:true,clickFocusWorks:true,
      noTopAnimation:true,disposed:true,
    });
  } finally {
    fs.rmSync(directory,{recursive:true,force:true});
  }
});

test('real Chromium DOM: deleting and reordering stages cleans orphan captions before paint', {skip:!chrome}, () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'madar-fl-stage-'));
  try {
    const fixture = `<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>
body{margin:0;font:14px sans-serif}
.stages{width:400px;margin:24px;padding:8px;background:#eee}
.stage{height:86px;padding:8px;box-sizing:border-box}
.stage label{display:flex;flex-direction:column}
.stage input{height:42px;width:240px;box-sizing:border-box}
.spacer{height:12px}.spacer.expanded{height:75px}
${cssSource}
</style></head><body><div id="root"><div class="stages" id="stages">
<div class="stage" id="stage-a"><label>مرحله اول<input id="a"></label></div>
<div class="spacer" id="spacer"></div>
<div class="stage" id="stage-b"><label>مرحله دوم<input id="b"></label></div>
<div class="stage" id="stage-c"><label>مرحله سوم<input id="c"></label></div>
</div></div>
<script type="module">
${jsSource}
window.requestAnimationFrame = callback => setTimeout(() => callback(performance.now()), 0);
const frame = () => new Promise(resolve => setTimeout(resolve, 85));
const readTop = id => {
  const input = document.getElementById(id);
  const caption = Array.from(document.querySelectorAll('.madar-fl-caption'))
    .find(node => node.textContent === input?.labels?.[0]?.textContent?.trim());
  return caption ? parseFloat(caption.style.getPropertyValue('--madar-fl-top-y')) : NaN;
};
const aligned = id => Math.abs(readTop(id) - (document.getElementById(id).getBoundingClientRect().top + 7)) < 1;
(async () => {
  const dispose = installFloatingLabels(document);
  await frame();
  const layer = document.querySelector('.madar-fl-layer');
  const stages = document.getElementById('stages');
  const a = document.getElementById('stage-a');
  const c = document.getElementById('stage-c');
  const initial = aligned('a') && aligned('b') && aligned('c');
  const beforeMove = readTop('a');
  stages.insertBefore(c, a);
  await Promise.resolve(); // deliver MutationObserver before its scheduled RAF
  const hiddenDuringMove = layer.style.visibility === 'hidden';
  await frame();
  const movedAndAligned = readTop('a') > beforeMove && aligned('a') && aligned('b') && aligned('c');

  const captionCountBeforeRemoval = document.querySelectorAll('.madar-fl-caption').length;
  c.remove();
  await Promise.resolve();
  const removedSynchronously = document.querySelectorAll('.madar-fl-caption').length ===
    captionCountBeforeRemoval - 1;
  const hiddenDuringRemoval = layer.style.visibility === 'hidden';
  await frame();
  const shiftedAfterRemoval = aligned('a') && aligned('b') && readTop('a') === beforeMove;

  const beforeClassChange = readTop('b');
  document.getElementById('spacer').classList.add('expanded');
  await Promise.resolve();
  const hiddenDuringClassChange = layer.style.visibility === 'hidden';
  await frame();
  const shiftedAfterClassChange = aligned('b') && readTop('b') > beforeClassChange;

  const plain = document.createElement('div');
  plain.style.height = '50px';
  stages.insertBefore(plain, document.getElementById('stage-b'));
  await Promise.resolve();
  const hiddenDuringPlainInsertion = layer.style.visibility === 'hidden';
  await frame();
  const movedAfterPlainInsertion = aligned('b') && readTop('b') > beforeClassChange + 50;

  dispose();
  document.body.dataset.results = encodeURIComponent(JSON.stringify({
    initial,hiddenDuringMove,movedAndAligned,removedSynchronously,hiddenDuringRemoval,
    shiftedAfterRemoval,hiddenDuringClassChange,shiftedAfterClassChange,
    hiddenDuringPlainInsertion,movedAfterPlainInsertion,disposed:!document.querySelector('.madar-fl-layer'),
  }));
})().catch(error => {document.body.dataset.results = encodeURIComponent(JSON.stringify({error:String(error)}));});
</script></body></html>`;
    const file = path.join(directory, 'stage-mutations.html');
    fs.writeFileSync(file, fixture, 'utf8');
    const result = spawnSync(chrome, [
      '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
      '--disable-extensions', '--virtual-time-budget=4000', '--window-size=900,700',
      `--user-data-dir=${path.join(directory,'profile')}`, '--dump-dom', pathToFileURL(file).href,
    ], {timeout:18000,maxBuffer:5*1024*1024,encoding:'utf8'});
    assert.equal(result.error,undefined,`Chromium failed to start: ${result.error?.message}`);
    assert.equal(result.status,0,`Chromium exited ${result.status}: ${result.stderr?.slice(0,500)}`);
    const match = result.stdout.match(/data-results="([^"]+)"/);
    assert.ok(match,`Chromium did not complete stage mutation scenario: ${result.stdout.slice(-1000)}`);
    assert.deepEqual(JSON.parse(decodeURIComponent(match[1])),{
      initial:true,hiddenDuringMove:true,movedAndAligned:true,removedSynchronously:true,
      hiddenDuringRemoval:true,shiftedAfterRemoval:true,hiddenDuringClassChange:true,
      shiftedAfterClassChange:true,hiddenDuringPlainInsertion:true,movedAfterPlainInsertion:true,disposed:true,
    });
  } finally {
    fs.rmSync(directory,{recursive:true,force:true});
  }
});
