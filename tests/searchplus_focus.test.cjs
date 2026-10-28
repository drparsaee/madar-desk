'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const project = path.resolve(__dirname, '..');
const chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightRoot = 'C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable = fs.existsSync(chrome) && fs.existsSync(playwrightRoot);

test('Chromium: search has one rounded focus ring and still accepts keyboard input in light and dark modes',
  {skip: !runnable, timeout: 60000}, async () => {
    const {chromium} = require(playwrightRoot);
    const {createServer} = await import('vite');
    const server = await createServer({root: project, logLevel: 'error',
      server: {host: '127.0.0.1', port: 0, strictPort: false,
        watch: {ignored: ['**/.*', '**/.*/**', '**/*.mdf', '**/*.ldf',
          '**/*.sqlite3', '**/*.sqlite3-*', '**/research/**', '**/release/**', '**/dist/**']}}});
    let browser;
    try {
      await server.listen();
      browser = await chromium.launch({headless: true, executablePath: chrome});
      const context = await browser.newContext({viewport: {width: 1440, height: 900}, locale: 'fa-IR'});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem('madar-preview', JSON.stringify({
          version: 1,
          workspaces: [{id: 'qa-space', name: 'فضای آزمایشی'}],
          projects: [{id: 'qa-project', name: 'پروژه آزمایشی'}],
          boards: [{id: 'qa-board', projectId: 'qa-project', workspaceId: 'qa-space',
            name: 'برد آزمایشی', stages: [{id: 'planned', label: 'برنامه‌ریزی'}]}],
          tasks: [{id: 'qa-task', projectId: 'qa-project', boardId: 'qa-board',
            title: 'عنوان آزمایشی', status: 'planned', listId: 'planned',
            labels: [], checklist: [], reports: []}],
          stages: [{id: 'planned', label: 'برنامه‌ریزی'}],
          settings: {theme: 'dark'},
        }));
        localStorage.setItem('madar-preferences', JSON.stringify({calendar: 'jalali', clockWidget: 'hidden'}));
      });
      await page.goto('http://127.0.0.1:' + server.httpServer.address().port + '/index.html',
        {waitUntil: 'domcontentloaded', timeout: 20000});
      const input = page.locator('.searchplus-control .searchplus-input');
      const control = page.locator('.searchplus-control');
      await input.waitFor({state: 'visible'});
      const evidence = [];
      for (const width of [1440, 480]) {
        await page.setViewportSize({width, height: 900});
        for (const theme of ['dark', 'light']) {
          await page.evaluate(value => {document.documentElement.dataset.theme = value;}, theme);
          await input.click();
          await input.fill('عنوان آزمایشی');
          const focus = await page.evaluate(() => {
            const field = document.querySelector('.searchplus-input');
            const outer = field.closest('.searchplus-control');
            const insideStyle = getComputedStyle(field);
            const outerStyle = getComputedStyle(outer);
            const bounds = outer.getBoundingClientRect();
            return {
              active: document.activeElement === field,
              focusVisible: field.matches(':focus-visible'),
              inputOutline: insideStyle.outlineStyle,
              inputBoxShadow: insideStyle.boxShadow,
              outerBorderRadius: outerStyle.borderTopLeftRadius,
              outerBorder: outerStyle.borderTopColor,
              outerBoxShadow: outerStyle.boxShadow,
              within: outer.matches(':focus-within'),
              inputValue: field.value,
              borderFitsViewport: bounds.left >= 0 && bounds.right <= innerWidth,
            };
          });
          evidence.push({width, theme, ...focus});
          assert.equal(focus.active, true);
          assert.equal(focus.focusVisible, true);
          assert.equal(focus.inputOutline, 'none', JSON.stringify({width, theme, focus}));
          assert.equal(focus.inputBoxShadow, 'none', JSON.stringify({width, theme, focus}));
          assert.equal(focus.within, true);
          assert.notEqual(focus.outerBoxShadow, 'none', JSON.stringify({width, theme, focus}));
          assert.equal(focus.outerBorderRadius, '12px');
          assert.equal(focus.inputValue, 'عنوان آزمایشی');
          assert.equal(focus.borderFitsViewport, true);
          await input.press('ControlOrMeta+A');
          await input.press('Backspace');
          await page.keyboard.type('title:qa');
          await assert.doesNotReject(input.inputValue());
          assert.equal(await input.inputValue(), 'title:qa');
          await input.press('Escape');
          assert.equal(await input.inputValue(), '');
          assert.equal(await control.locator('input').count(), 1);
        }
      }
      await page.locator('.searchplus-help-button').focus();
      const helpOutline = await page.locator('.searchplus-help-button').evaluate(el => getComputedStyle(el).outlineStyle);
      assert.notEqual(helpOutline, 'none', 'keyboard focus must remain visible on search action buttons');
      assert.deepEqual(errors, []);
      console.log('Search focus Chromium evidence:', JSON.stringify(evidence));
      await context.close();
    } finally {
      if (browser) await browser.close();
      await server.close();
    }
  });
