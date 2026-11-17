'use strict';
// Deterministic source/behavior tests. No installed Madar, host, ledger or
// real notification inbox is opened or modified.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const os = require('node:os');
const esbuild = require('esbuild');

const root = path.resolve(__dirname, '..');
const file = path.join(root, 'src', 'mtr_sileo_feedback.jsx');
const appSource = fs.readFileSync(path.join(root, 'src', 'App.jsx'), 'utf8');
const feedbackSource = fs.readFileSync(file, 'utf8');
const css = fs.readFileSync(path.join(root, 'src', 'mtr_sileo_feedback.css'), 'utf8');

function loadFeedback() {
  const fakeCalls = [];
  const sender = Object.fromEntries(['success', 'error', 'warning', 'info'].map(type => [
    type, options => {fakeCalls.push({type, ...options}); return 'synthetic-'+type;}
  ]));
  const build = esbuild.buildSync({
    entryPoints: [file], bundle: true, write: false, platform: 'node',
    format: 'cjs', logLevel: 'silent',
    external: ['react', 'react/jsx-runtime', 'sileo'],
    loader: {'.css': 'empty'},
  });
  const module = {exports: {}};
  const requireSafe = name => {
    if(name === 'sileo')return {sileo: sender, Toaster: () => null};
    if(name === 'react')return require('react');
    if(name === 'react/jsx-runtime')return require('react/jsx-runtime');
    throw Error('Untrusted imported module: '+name);
  };
  const context = vm.createContext({
    module, exports: module.exports, require: requireSafe,
    process: {env: {}}, console,
  });
  vm.runInContext(build.outputFiles[0].text, context, {timeout: 3000});
  return {exports: module.exports, calls: fakeCalls, sender};
}

test('exact one real Sileo root mount, all app modes, no duplicated legacy toast', () => {
  assert.equal((appSource.match(/<MadarSileoFeedback\b/g)||[]).length, 1);
  assert.equal((feedbackSource.match(/<Toaster\b/g)||[]).length, 1);
  assert.match(feedbackSource, /import\s*\{sileo,\s*Toaster\}\s*from\s*'sileo'/);
  assert.match(appSource, /<MadarSileoFeedback\s+message=\{toast\}\s+errorMessage=\{savingError\}/);
  assert.doesNotMatch(appSource, /\{toast&&<div className="toast"/);
  assert.match(appSource, /\{notificationsOpen&&<NotificationsDialog\b/);
  assert.match(appSource, /<CardContextMenu\b/);
  assert.match(appSource, /<TrelloImportPanel\b/);
  assert.match(appSource, /<LanPanel\b/);
  assert.match(appSource, /<TaskEditor\b/);
  assert.match(appSource, /<SettingsPanel\b/);
  assert.match(appSource, /<WebSyncDialog\b/);
});

test('real App mounts only one opt-in contextual help for live mode/modal/role state', () => {
  assert.match(appSource, /import\s*\{MadarContextHelp\}\s*from\s*'\.\/mtr_context_help\.jsx'/);
  assert.equal((appSource.match(/<MadarContextHelp\b/g)||[]).length,1);
  assert.match(appSource, /<MadarContextHelp\s+currentSection=\{helpCurrentSection\}\s+availableSections=\{helpAvailableSections\}/);
  assert.match(appSource, /notificationsOpen\?'notifications'/);
  assert.match(appSource, /lanOpen\?\(lanInitialView==='users'/);
  assert.match(appSource, /editorId\?'cards'/);
  assert.match(appSource, /mode==='board'&&selected==='all'\?'overview':mode/);
  assert.match(appSource, /canManage&&show\('secureApiKeys'\)/);
  assert.match(appSource, /canManage\?\['lan-users'\]:\[\]/);
  assert.match(appSource, /\['api-keys'\]/);
  assert.doesNotMatch(appSource, /setHelpOpen\(true\)/);
});

test('reduced-motion, accessibility, RTL, compact Sileo surface', () => {
  assert.match(css, /\[data-sileo-viewport\]/);
  assert.match(css, /direction:\s*rtl/);
  assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(feedbackSource, /position="top-center"/);
  assert.match(feedbackSource, /options=\{\{duration:\s*4500\}\}/);
});

test('explicit success/error/warning/info reach matching Sileo calls', () => {
  const {exports: feedback, calls, sender} = loadFeedback();
  for(const type of ['success', 'error', 'warning', 'info']){
    const value = feedback.emitMadarFeedback({type, title: 'تست '+type}, sender);
    assert.equal(value, 'synthetic-'+type);
  }
  assert.deepEqual(calls.map(c => c.type), ['success', 'error', 'warning', 'info']);
  assert.ok(calls.every(c => c.position === 'top-center'));
});

test('legacy optimistic messages default info, not durable success', () => {
  const {exports: feedback} = loadFeedback();
  for(const message of ['پروژه ساخته شد.', 'برد جدید در پروژه ساخته شد.',
    'ساختار ستون کپی شد', 'کارت به زباله‌دان منتقل شد', 'اطلاعات بازیابی شد.']){
    assert.equal(feedback.normalizeMadarFeedback(message).type, 'info', message);
  }
});

test('warnings and failures never present green success, even with forged type', () => {
  const {exports: feedback, calls, sender} = loadFeedback();
  for(const text of ['خطای ذخیره: token=secret', 'ذخیره کارت موفق نبود',
    'عملیات انجام نشد', 'پاسخ نامعتبر است']){
    assert.equal(feedback.normalizeMadarFeedback({type:'success', title:text}).type,
                 'error', text);
    feedback.emitMadarFeedback({type:'success',title:text}, sender);
  }
  for(const text of ['تعارض نسخه پیدا شد', 'کارت در صف آفلاین ثبت شد',
    'نتیجه هنوز تأیید نشده', 'ارسال دستی خاموش است']){
    assert.equal(feedback.normalizeMadarFeedback(text).type, 'warning', text);
  }
  assert.ok(calls.every(call => call.type === 'error'));
});

test('sileo never emits stringified backend objects, secrets, paths or links', () => {
  const {exports: feedback, calls, sender} = loadFeedback();
  assert.equal(feedback.emitMadarFeedback(null, sender), null);
  assert.equal(feedback.emitMadarFeedback({type:'success',title:{secret:'x'}}, sender), null);
  const message = feedback.safeFeedbackText('token=abc-secret password=hunter2 Bearer qwerty https://example.com/path C:\\Users\\Real\\Profile');
  assert.doesNotMatch(message, /abc-secret|hunter2|qwerty|example\.com|Users\\Real/);
  const error = feedback.emitMadarFeedback({type:'error',title:
    'خطای ذخیره: password=hunter2 C:\\Users\\Real\\Profile'}, sender);
  assert.equal(error,'synthetic-error');
  assert.doesNotMatch(calls.at(-1).title, /hunter2|Users|Real/);
  assert.ok(calls.at(-1).title.length <= 170);
});

test('no automatic success on mount, error banner stays durable and visible', () => {
  assert.match(appSource, /\{savingError&&<div className="error-toast recovery-alert"/);
  assert.match(appSource, /pendingRecovery&&<div className="recovery-actions"/);
  assert.match(feedbackSource, /if\(message && message !== seen\.current\.message\)/);
  assert.match(feedbackSource, /if\(errorMessage && errorMessage !== seen\.current\.error\)/);
  assert.match(feedbackSource, /seen\.current\.message = message \|\| ''/);
  assert.doesNotMatch(feedbackSource, /window\.addEventListener\('madar:feedback'/);
  assert.doesNotMatch(feedbackSource, /new CustomEvent/);
  assert.doesNotMatch(feedbackSource, /localStorage|sessionStorage|fetch\(|postMessage/);
});

test('save ack checked, queue vs saved distinct, no finance or peer success claim', () => {
  assert.match(appSource, /const result=await api\.saveState\(snapshot\);[\s\S]{0,370}result===false/);
  assert.match(appSource, /result\?\.offline===true\s*\?\{type:'warning'/);
  assert.match(appSource, /result===undefined\|\|result===null/);
  assert.match(appSource, /:\{type:'success',title:'کارت ذخیره شد/);
  assert.match(appSource, /result\?\.postingPerformed!==false/);
  assert.match(appSource, /result\?\.id!==targetId/);
  assert.match(appSource, /result\?\.launchRequested!==true/);
  assert.match(appSource, /outcome\?\.verified!==true/);
  assert.match(appSource, /outcome\?\.scheduledAfterExit!==true/);
  assert.match(appSource, /kind==='rejected'/);
  assert.doesNotMatch(feedbackSource, /collabCommand|mtrNoticeCommand|standaloneAccountingCommand/);
});

test('Trello and calendar import only report local staging, not backend success', () => {
  assert.match(appSource, /<TrelloImportPanel[^\n]+onImport=\{next=>/);
  assert.match(appSource, /throw Error\('ورود در این وضعیت مجاز نیست\.'/);
  assert.match(appSource, /ورود اطلاعات به تغییرات محلی اضافه شد؛ تأیید ذخیره جداگانه/);
  assert.match(appSource, /رویدادهای تقویم به تغییرات محلی اضافه شدند؛ تأیید ذخیره جداگانه/);
});

test('complete Vite-compatible App and Sileo bundle compiles in memory', async () => {
  const result = await esbuild.build({
    entryPoints: [path.join(root, 'src', 'App.jsx')],
    bundle:true, write:false, platform:'browser', format:'iife',
    define:{'import.meta.env.MODE':JSON.stringify('production')},
    loader:{'.css':'css','.svg':'dataurl','.png':'dataurl','.jpg':'dataurl',
      '.woff':'dataurl','.woff2':'dataurl'},
    outdir:'mtr-sileo-build-check', logLevel:'silent',
  });
  const js = result.outputFiles.find(f=>f.path.endsWith('.js'));
  assert.ok(js && js.contents.length > 100000);
  assert.match(js.text, /data-sileo-viewport/);
  assert.match(js.text, /tarazIntegrationQueue/);
  assert.match(js.text, /NotificationsDialog|اعلان‌ها/);
});

const chrome = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const playwrightPath = path.join(process.env.USERPROFILE || '', 'AppData',
  'Roaming', 'npm', 'node_modules', 'playwright');
const browserAvailable = fs.existsSync(chrome) && fs.existsSync(
  path.join(playwrightPath, 'package.json'));

test('real Chromium renders one actual Sileo toast on user action, not on mount',
  {skip:!browserAvailable, timeout:60000}, async () => {
    const {chromium} = require(playwrightPath);
    const component = [
      "import React from 'react';",
      "import {createRoot} from 'react-dom/client';",
      "import {MadarSileoFeedback} from './src/mtr_sileo_feedback.jsx';",
      "const root=createRoot(document.getElementById('root'));",
      "window.madarSileoQA={render:(message='',errorMessage='')=>",
      " root.render(<MadarSileoFeedback message={message} errorMessage={errorMessage}/>)};",
      "window.madarSileoQA.render();",
    ].join('\n');
    const built = await esbuild.build({
      stdin:{contents:component,resolveDir:root,sourcefile:'madar-sileo-chromium-qa.jsx',
        loader:'jsx'}, bundle:true,platform:'browser',format:'iife',
      write:false,logLevel:'silent',outdir:'sileo-chromium-qa',
      loader:{'.css':'css'},
    });
    const js = built.outputFiles.find(file=>file.path.endsWith('.js'));
    assert.ok(js);
    const cssOutput = built.outputFiles.find(file=>file.path.endsWith('.css'));
    const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(),'madar-sileo-disposable-'));
    const profile = path.join(tempRoot,'edge-qa-profile');
    let context;
    try{
      const environment = Object.fromEntries(Object.entries(process.env).filter(([key])=>
        /^(?:PATH|SYSTEMROOT|WINDIR|PATHEXT|COMSPEC|PROCESSOR_ARCHITECTURE)$/i.test(key)));
      for(const key of ['APPDATA','LOCALAPPDATA','TEMP','TMP','HOME','USERPROFILE']){
        const location=path.join(tempRoot,key.toLowerCase());
        fs.mkdirSync(location,{recursive:true});
        environment[key]=location;
      }
      context=await chromium.launchPersistentContext(profile,{
        executablePath:chrome,headless:true,viewport:{width:1080,height:740},
        locale:'fa-IR',env:environment,
        args:['--no-first-run','--disable-background-networking',
          '--disable-default-apps','--disable-sync','--no-default-browser-check'],
      });
      await context.route('**/*',route=>route.abort());
      const page=context.pages()[0] || await context.newPage();
      const browserErrors=[];
      page.on('pageerror',error=>browserErrors.push(String(error?.message||error)));
      await page.emulateMedia({reducedMotion:'reduce'});
      await page.setContent('<html lang="fa" dir="rtl"><body><div id="root"></div></body></html>');
      if(cssOutput)await page.addStyleTag({content:cssOutput.text});
      await page.addScriptTag({content:js.text});
      assert.equal(await page.evaluate(()=>typeof window.madarSileoQA?.render),'function',
                   'Compiled React/Sileo test harness did not load: '+browserErrors.join(';'));
      assert.equal(await page.locator('[data-sileo-toast]').count(),0);
      await page.evaluate(()=>window.madarSileoQA.render({
        type:'info',title:'اطلاعات برای بررسی آماده است.'
      }));
      await page.locator('[data-sileo-toast][data-state="info"]').first()
        .waitFor({timeout:10000}).catch(err=>{
          throw Error(String(err.message)+'; browser errors='+browserErrors.join(';'));
        });
      assert.match(await page.locator('[data-sileo-title]').last().innerText(),/اطلاعات/);
      const before=await page.locator('[data-sileo-toast]').count();
      // Untrusted arbitrary events cannot forge a persisted operation.
      await page.evaluate(()=>window.dispatchEvent(
        new CustomEvent('madar:feedback',{detail:{type:'success',
          title:'سند مالی با موفقیت ثبت شد'}})));
      await page.waitForTimeout(120);
      assert.equal(await page.locator('[data-sileo-toast]').count(),before);
      await page.evaluate(()=>window.madarSileoQA.render({
        type:'success',title:'خطای ذخیره: token=hunter2'
      }));
      await page.locator('[data-sileo-toast][data-state="error"]').first()
        .waitFor({timeout:10000});
      const descriptions=await page.locator('[data-sileo-title]').allInnerTexts();
      assert.ok(descriptions.some(text=>text.includes('ذخیره انجام نشد')));
      assert.ok(descriptions.every(text=>!text.includes('hunter2')));
      assert.equal(await page.evaluate(() => matchMedia(
        '(prefers-reduced-motion: reduce)').matches),true);

      // The actual App, not a standalone help demonstration, must expose '?'.
      const appBuilt=await esbuild.build({
        entryPoints:[path.join(root,'src','main.jsx')],
        bundle:true,platform:'browser',format:'iife',
        write:false,logLevel:'silent',outdir:'madar-full-app-help-qa',
        define:{'import.meta.env.MODE':'"production"',
          'import.meta.env.PROD':'false','import.meta.env.BASE_URL':'"/"'},
        external:['/fonts/*'],
        loader:{'.css':'css','.svg':'dataurl','.png':'dataurl',
          '.jpg':'dataurl','.woff':'dataurl','.woff2':'dataurl'},
      });
      const appJs=appBuilt.outputFiles.find(f=>f.path.endsWith('.js'));
      const appCss=appBuilt.outputFiles.find(f=>f.path.endsWith('.css'));
      assert.ok(appJs && appJs.contents.length>100000);
      const appPage=await context.newPage();
      const appErrors=[];
      appPage.on('pageerror',error=>appErrors.push(String(error?.message||error)));
      await appPage.setContent('<html lang="fa" dir="rtl"><body><div id="root"></div></body></html>');
      // No installed host, no user profile or network. Isolated in-memory
      // browser preview storage is enough for the real App mockBridge.
      await appPage.evaluate(()=>{
        const store=new Map();
        const storage={
          getItem:key=>store.has(String(key))?store.get(String(key)):null,
          setItem:(key,value)=>store.set(String(key),String(value)),
          removeItem:key=>store.delete(String(key)),
          clear:()=>store.clear(),
          key:index=>Array.from(store.keys())[index]||null,
        };
        Object.defineProperty(storage,'length',{get:()=>store.size});
        Object.defineProperty(window,'localStorage',{configurable:true,value:storage});
      });
      if(appCss)await appPage.addStyleTag({content:appCss.text});
      await appPage.addScriptTag({content:appJs.text});
      await appPage.locator('.app-shell').waitFor({timeout:15000})
        .catch(err=>{throw Error(err.message+'; real App errors='+appErrors.join(';'));});
      const help=appPage.locator('.mtr-context-help__trigger');
      await help.waitFor({timeout:6000});
      assert.equal(await help.count(),1);
      assert.match(await help.getAttribute('aria-label'),/راهنمای نمای کلی/);
      await help.click();
      const panel=appPage.getByRole('region',{name:'راهنمای مدار'});
      await panel.waitFor();
      assert.ok((await panel.locator('ol li').count())>=1);
      assert.ok((await panel.locator('ol li').count())<=3);
      assert.match(await panel.innerText(),/نمای کلی/);
      await panel.getByRole('searchbox',{name:'جست‌وجوی راهنما'}).press('Escape');
      await panel.waitFor({state:'detached'});
      assert.equal(await help.getAttribute('aria-expanded'),'false');
      assert.equal(await help.evaluate(element=>document.activeElement===element),true);
      await appPage.getByRole('button',{name:'فهرست',exact:true}).first().click();
      await appPage.locator('.mtr-context-help__trigger[aria-label="راهنمای نمای فهرست"]').waitFor();
      await appPage.locator('button[aria-label="تازه‌سازی اتصال"]').first().click();
      await appPage.locator('[data-sileo-toast][data-state="info"]').first()
        .waitFor({timeout:12000});
      assert.equal(await appPage.locator('.mtr-context-help__trigger').count(),1);
      assert.equal(await appPage.locator('[data-sileo-viewport]').count(),1);
      // Actual notifications dialog remains durable; help is a separate,
      // nonmutating surface and its trigger stays visible over the dialog.
      await appPage.locator('button[aria-label="اعلان‌ها"]').first().click();
      await appPage.locator('.mtr-context-help__trigger[aria-label="راهنمای اعلان‌ها"]').waitFor();
      await help.click();
      await panel.waitFor();
      assert.match(await panel.innerText(),/اعلان/);
      assert.ok((await panel.locator('ol li').count())<=3);
      await panel.getByRole('searchbox',{name:'جست‌وجوی راهنما'}).press('Escape');
      assert.equal(await help.evaluate(element=>document.activeElement===element),true);
      assert.equal(await appPage.locator('.mtr-context-help__trigger').count(),1);
      await appPage.close();
    }finally{
      if(context)await context.close();
      fs.rmSync(tempRoot,{recursive:true,force:true});
    }
  });
