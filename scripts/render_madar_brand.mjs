// Render the committed SVG, not a hand-drawn replacement, into an RGBA PNG.
// Uses an already installed Chrome, no network dependencies or source mutation.
import { spawn } from 'node:child_process';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const chrome = process.env.CHROME_BIN || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const svg = resolve(process.argv[2] || 'assets/madar-final.svg');
const output = resolve(process.argv[3] || 'assets/madar-logo-rgba-1024.png');
const profile = await mkdtemp(join(tmpdir(), 'madar-logo-render-'));
let processHandle;
let socket;
const delay = ms => new Promise(r => setTimeout(r, ms));

async function connect(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    const reject = e => rej(e.error || e);
    ws.addEventListener('error', reject, { once: true });
    ws.addEventListener('open', () => res(ws), { once: true });
  });
}

try {
  processHandle = spawn(chrome, [
    '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--disable-extensions', '--remote-debugging-port=0', '--user-data-dir=' + profile,
    'about:blank'
  ], { windowsHide: true, stdio: 'ignore' });
  let port;
  for (let i = 0; i < 100; i++) {
    if (processHandle.exitCode !== null) throw new Error('Headless Chrome exited');
    try {
      port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]);
      if (port > 0) break;
    } catch {}
    await delay(100);
  }
  if (!port) throw new Error('Cannot establish isolated Chrome DevTools port');
  const targets = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
  const target = targets.find(item => item.type === 'page');
  if (!target) throw new Error('No Chromium page target');
  socket = await connect(target.webSocketDebuggerUrl);
  const pending = new Map();
  let nextId = 0;
  socket.addEventListener('message', ({data}) => {
    const result = JSON.parse(data);
    if (!result.id || !pending.has(result.id)) return;
    const entry = pending.get(result.id);
    pending.delete(result.id);
    if (result.error) entry.reject(new Error(result.error.message));
    else entry.resolve(result.result);
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
  await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',
    {width: 1024, height: 1024, deviceScaleFactor: 1, mobile: false});
  await send('Emulation.setDefaultBackgroundColorOverride',
    {color: {r: 0, g: 0, b: 0, a: 0}});
  await send('Page.navigate', {url: pathToFileURL(svg).href});
  const ready = async () => {
    for (let i = 0; i < 100; i++) {
      const evaluation = await send('Runtime.evaluate', {
        expression: "document.readyState === 'complete' && document.documentElement.localName === 'svg'",
        returnByValue: true
      });
      if (evaluation.result?.value) return;
      await delay(100);
    }
    throw new Error('SVG failed to load');
  };
  await ready();
  await delay(150);
  const shot = await send('Page.captureScreenshot',
    {format: 'png', fromSurface: true, captureBeyondViewport: false});
  const bytes = Buffer.from(shot.data, 'base64');
  if (!bytes.subarray(1, 4).equals(Buffer.from('PNG'))) throw new Error('Not PNG');
  await writeFile(output, bytes);
  console.log('SVG_RASTERIZED', output, bytes.length);
} finally {
  if (socket) socket.close();
  if (processHandle) processHandle.kill();
  await delay(200);
  await rm(profile, {recursive: true, force: true, maxRetries: 6, retryDelay: 300});
}
