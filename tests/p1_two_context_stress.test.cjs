'use strict';

// Fully synthetic regression against the built Web PWA, the real Node API,
// and a disposable SQLite database. No Windows profile or LAN service is used.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const {createApp} = require('../server/index.cjs');
const {createUser} = require('../server/storage.cjs');

const root = path.resolve(__dirname, '..');
const webRoot = path.join(root, 'dist-web');
const chrome = [
  process.env.MADAR_CHROME_PATH,
  path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Google', 'Chrome',
    'Application', 'chrome.exe'),
  path.join(process.env.LOCALAPPDATA || '', 'Google', 'Chrome', 'Application',
    'chrome.exe')
].find(value => value && fs.existsSync(value));
let playwright = null;
for (const candidate of ['playwright',
  path.join(process.env.APPDATA || '', 'npm', 'node_modules', 'playwright')]) {
  try { playwright = require(candidate); break; }
  catch { /* The next known local installation might exist. */ }
}

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

const mime = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.webmanifest': 'application/manifest+json'
};

function builtFrontend(frontPort, apiPort) {
  return http.createServer((request, response) => {
    let pathname;
    try { pathname = decodeURIComponent(new URL(request.url,
      'http://127.0.0.1:' + frontPort).pathname); }
    catch { response.writeHead(400); response.end(); return; }

    if (pathname === '/api/web/v1' || pathname.startsWith('/api/web/v1/')) {
      const upstream = http.request({
        hostname: '127.0.0.1', port: apiPort, method: request.method,
        path: request.url,
        headers: {...request.headers, host: '127.0.0.1:' + apiPort}
      }, serverResponse => {
        response.writeHead(serverResponse.statusCode || 502, serverResponse.headers);
        serverResponse.pipe(response);
      });
      upstream.on('error', () => {
        if (!response.headersSent) {
          response.writeHead(502, {'Content-Type': 'application/json'});
          response.end('{"error":"upstream_unavailable"}');
        }
      });
      request.pipe(upstream);
      return;
    }

    const target = path.resolve(webRoot, '.' + pathname);
    if (target !== webRoot && !target.startsWith(webRoot + path.sep)) {
      response.writeHead(403); response.end(); return;
    }
    const send = file => fs.stat(file, (error, stats) => {
      if (error || !stats.isFile()) {
        if (!path.extname(pathname) && file !== path.join(webRoot, 'index.html'))
          return send(path.join(webRoot, 'index.html'));
        response.writeHead(404); response.end(); return;
      }
      response.writeHead(200, {
        'Content-Type': mime[path.extname(file).toLowerCase()] ||
          'application/octet-stream',
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store'
      });
      fs.createReadStream(file).pipe(response);
    });
    send(target === webRoot ? path.join(webRoot, 'index.html') : target);
  });
}

function syntheticSnapshot() {
  const stage = {id: 'todo', label: 'Todo'};
  return {
    version: 1,
    workspaces: [{id: 'w1', name: 'Synthetic workspace'}],
    projects: [{id: 'p1', name: 'Visible'}, {id: 'p2', name: 'Hidden'}],
    boards: [
      {id: 'b1', workspaceId: 'w1', projectId: 'p1', name: 'One',
        stages: [stage]},
      {id: 'b2', workspaceId: 'w1', projectId: 'p2', name: 'Two',
        stages: [stage]}
    ],
    tasks: [
      {id: 't1', projectId: 'p1', boardId: 'b1', listId: 'todo',
        status: 'todo', title: 'Accessible', checklist: [], labels: []},
      {id: 't2', projectId: 'p2', boardId: 'b2', listId: 'todo',
        status: 'todo', title: 'Private', checklist: [], labels: []}
    ],
    stages: [stage],
    settings: {theme: 'dark'}
  };
}

async function browserRequest(page, method, endpoint, body, headers = {}) {
  return page.evaluate(async input => {
    const response = await fetch('/api/web/v1' + input.endpoint, {
      method: input.method,
      headers: {
        ...(input.body === undefined ? {} : {'Content-Type': 'application/json'}),
        ...input.headers
      },
      ...(input.body === undefined ? {} : {body: JSON.stringify(input.body)})
    });
    return {
      status: response.status, etag: response.headers.get('etag'),
      payload: response.status === 204 ? null : await response.json()
    };
  }, {method, endpoint, body, headers});
}

async function storeLocalChangeOffline(page, fallback) {
  return page.evaluate(async seed => {
    // The production bundle has no /src imports; use the same on-disk
    // IndexedDB database and document key as its browser storage module.
    const db = await new Promise((resolve, reject) => {
      const request = indexedDB.open('madar-web-local-v1', 2);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const update = async () => new Promise((resolve, reject) => {
      const transaction = db.transaction('documents', 'readwrite');
      const documents = transaction.objectStore('documents');
      const existing = documents.get('board-state');
      let stored;
      existing.onsuccess = () => {
        const prior = existing.result || seed;
        stored = {...prior, settings: {...prior.settings, theme: 'light'}};
        documents.put(stored, 'board-state');
      };
      transaction.oncomplete = () => resolve(stored.settings.theme);
      transaction.onabort = () => reject(transaction.error);
      transaction.onerror = () => reject(transaction.error);
    });
    try {
      const theme = await update();
      const stored = await new Promise((resolve, reject) => {
        const tx = db.transaction('documents', 'readonly');
        const request = tx.objectStore('documents').get('board-state');
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      return {theme, reloadedTheme: stored.settings.theme};
    } finally {
      db.close();
    }
  }, fallback);
}

test('P1 two Chromium contexts: SQLite project ACL, replay, stale conflict, offline and isolated logout',
  {skip: !chrome || !playwright || !fs.existsSync(path.join(webRoot, 'index.html')),
    timeout: 95000}, async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'madar-p1-two-context-'));
    const frontPort = await freePort();
    const apiPort = await freePort();
    const origin = 'http://127.0.0.1:' + frontPort;
    const app = createApp({dbPath: path.join(tempDir, 'synthetic.sqlite'),
      publicOrigin: origin});
    const password = 'synthetic-stress-secret-12345';
    for (const [username, role, projectIds] of [
      ['stress-editor', 'editor', ['p1']],
      ['stress-viewer', 'viewer', ['p1']]
    ]) {
      createUser(app.db, {username, password, role, projectIds, workspaceId: 'team'});
    }
    const seed = syntheticSnapshot();
    // A real SQLite head starts the test at a shared revision; all tested
    // updates and permissions still travel through the live HTTP API.
    app.db.prepare(`INSERT INTO web_workspace_heads
      (workspace_id, revision, state_json, updated_at) VALUES (?,?,?,?)`)
      .run('team', 'baseline-r1', JSON.stringify(seed), new Date().toISOString());

    const frontend = builtFrontend(frontPort, apiPort);
    let frontendListening = false;
    let apiListening = false;
    let browser = null;
    const contexts = [];
    try {
      await new Promise((resolve, reject) => {
        app.server.once('error', reject);
        app.server.listen(apiPort, '127.0.0.1', resolve);
      });
      apiListening = true;
      await new Promise((resolve, reject) => {
        frontend.once('error', reject);
        frontend.listen(frontPort, '127.0.0.1', resolve);
      });
      frontendListening = true;
      browser = await playwright.chromium.launch({
        headless: true, executablePath: chrome
      });

      async function signIn(username) {
        const context = await browser.newContext({
          viewport: {width: 430, height: 800},
          locale: 'fa-IR', serviceWorkers: 'block'
        });
        contexts.push(context);
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(origin, {waitUntil: 'domcontentloaded'});
        await page.getByRole('status',
          {name: 'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor();
        await page.getByRole('button', {name: 'اتصال آنلاین'}).click();
        const dialog = page.getByRole('dialog', {name: 'اتصال آنلاین مدار'});
        await dialog.getByLabel('نام کاربری').fill(username);
        await dialog.getByLabel('گذرواژه').fill(password);
        await dialog.getByRole('button', {name: 'ورود به حساب مدار'}).click();
        await dialog.locator('.web-sync-user strong').waitFor({timeout: 15000});
        assert.equal((await dialog.locator('.web-sync-user strong').textContent())
          .trim(), username);
        const session = await browserRequest(page, 'GET', '/session');
        assert.equal(session.status, 200);
        return {context, page, dialog, errors, session};
      }

      const editor = await signIn('stress-editor');
      const viewer = await signIn('stress-viewer');
      assert.equal(editor.session.payload.user.role, 'editor');
      assert.equal(viewer.session.payload.user.role, 'viewer');
      assert.deepEqual(viewer.session.payload.user.projectIds, ['p1']);
      const editorToken = (await editor.context.cookies())
        .find(item => item.name === 'madar_web_session')?.value;
      const viewerToken = (await viewer.context.cookies())
        .find(item => item.name === 'madar_web_session')?.value;
      assert.ok(editorToken && viewerToken);
      assert.notEqual(editorToken, viewerToken);

      const editorRead = await browserRequest(editor.page, 'GET', '/state');
      const viewerRead = await browserRequest(viewer.page, 'GET', '/state');
      assert.equal(editorRead.status, 200);
      assert.equal(viewerRead.status, 200);
      assert.deepEqual(viewerRead.payload.state.projects.map(p => p.id), ['p1']);
      assert.deepEqual(viewerRead.payload.state.tasks.map(t => t.id), ['t1']);
      assert.equal(JSON.stringify(viewerRead.payload).includes('Private'), false);
      assert.equal(JSON.stringify(viewerRead.payload).includes('p2'), false);

      const viewerDenied = await browserRequest(viewer.page, 'PUT', '/state',
        {schemaVersion: 1, state: viewerRead.payload.state}, {
          'X-CSRF-Token': viewer.session.payload.csrfToken,
          'Idempotency-Key': 'viewer-denied',
          'If-Match': viewerRead.etag
        });
      assert.equal(viewerDenied.status, 403);

      const updated = structuredClone(editorRead.payload.state);
      updated.tasks[0].title = 'Edited only visible card';
      const editorHeaders = {
        'X-CSRF-Token': editor.session.payload.csrfToken,
        'Idempotency-Key': 'editor-save',
        'If-Match': editorRead.etag
      };
      const editorSaved = await browserRequest(editor.page, 'PUT', '/state',
        {schemaVersion: 1, state: updated}, editorHeaders);
      assert.equal(editorSaved.status, 200, JSON.stringify(editorSaved.payload));
      const replay = await browserRequest(editor.page, 'PUT', '/state',
        {schemaVersion: 1, state: updated}, editorHeaders);
      assert.equal(replay.status, 200);
      assert.equal(replay.payload.revision, editorSaved.payload.revision);
      assert.equal(replay.etag, editorSaved.etag);

      const stale = structuredClone(editorRead.payload.state);
      stale.tasks[0].title = 'Forbidden stale overwrite';
      const conflict = await browserRequest(editor.page, 'PUT', '/state',
        {schemaVersion: 1, state: stale}, {
          'X-CSRF-Token': editor.session.payload.csrfToken,
          'Idempotency-Key': 'stale-save',
          'If-Match': editorRead.etag
        });
      assert.equal(conflict.status, 409);
      const stored = JSON.parse(app.db.prepare(`SELECT state_json
        FROM web_workspace_heads WHERE workspace_id=?`).get('team').state_json);
      assert.deepEqual(stored.tasks.map(task => task.title),
        ['Edited only visible card', 'Private']);
      assert.equal(app.db.prepare('SELECT COUNT(*) AS n FROM web_workspace_snapshots')
        .get().n, 1, 'replay and stale write must not create another snapshot');

      await viewer.context.setOffline(true);
      const offlineBlocked = await viewer.page.evaluate(async () => {
        try { await fetch('/api/web/v1/session'); return false; }
        catch { return true; }
      });
      assert.equal(offlineBlocked, true);
      const local = await storeLocalChangeOffline(viewer.page, seed);
      assert.deepEqual(local, {theme: 'light', reloadedTheme: 'light'});

      await viewer.context.setOffline(false);
      const reconnected = await browserRequest(viewer.page, 'GET', '/session');
      assert.equal(reconnected.status, 200);
      await viewer.dialog.getByRole('button', {name: 'خروج از حساب'}).click();
      await viewer.dialog.getByRole('button',
        {name: 'ورود به حساب مدار'}).waitFor();
      const loggedOut = await browserRequest(viewer.page, 'GET', '/session');
      assert.equal(loggedOut.status, 401);
      const editorStillActive = await browserRequest(editor.page, 'GET', '/session');
      assert.equal(editorStillActive.status, 200);
      assert.deepEqual([...editor.errors, ...viewer.errors], []);
    } finally {
      for (const context of contexts) await context.close();
      if (browser) await browser.close();
      if (frontendListening) {
        await new Promise(resolve => {
          frontend.close(resolve);
          frontend.closeAllConnections();
        });
      }
      if (apiListening) await app.close();
      else app.db.close();
      fs.rmSync(tempDir, {recursive: true, force: true});
    }
  });
