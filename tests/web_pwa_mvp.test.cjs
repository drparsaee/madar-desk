'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);

const stage={id:'todo',label:'انجام‌دادنی',color:'#5672ca'};
const stamp='2026-11-06T10:00:00Z';
const synthetic={
  version:1,
  projects:[{id:'web-project',name:'پروژه وب آزمایشی',color:'#5672ca',costEnabled:false,price:0}],
  workspaces:[{id:'web-workspace',name:'فضای آزمایشی',archived:false}],
  boards:[{id:'web-board',workspaceId:'web-workspace',projectId:'web-project',
    name:'برد وب آزمایشی',archived:false,stages:[stage]}],
  stages:[stage],
  tasks:[{id:'web-card',boardId:'web-board',projectId:'web-project',
    listId:'todo',status:'todo',title:'کارت تست وب',description:'',
    labels:[],reports:[],checklist:[],priority:'medium',
    createdAt:stamp,updatedAt:stamp}],
  settings:{theme:'light',costDefault:false}
};
function reservePort(){
  return new Promise((resolve,reject)=>{
    const socket=net.createServer();
    socket.once('error',reject);
    socket.listen(0,'127.0.0.1',()=>{
      const port=socket.address().port;
      socket.close(error=>error?reject(error):resolve(port));
    });
  });
}

test('web app isolates state from preview, persists IndexedDB, exports and rejects stale tab saves',
  {skip:!runnable,timeout:90000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,mode:'web',logLevel:'error',
      server:{host:'127.0.0.1',port:await reservePort(),strictPort:true,hmr:false}});
    let browser;
    try {
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1400,height:900},locale:'fa-IR'});
      const page=await context.newPage();
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      const banner=page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'});
      await banner.waitFor();
      assert.match(await banner.innerText(),/برای استفادهٔ چنددستگاهی حساب را متصل کنید/);
      assert.equal(await page.locator('a[rel="manifest"]').count(),0);
      assert.equal(await page.locator('link[rel="manifest"]').count(),1);
      await banner.getByRole('button',{name:'اتصال آنلاین'}).click();
      const syncDialog=page.getByRole('dialog',{name:'اتصال آنلاین مدار'});
      try{await syncDialog.waitFor({timeout:5000});}
      catch(error){throw Error('Web sync dialog did not open: '+JSON.stringify({
        body:(await page.locator('body').innerText()).slice(0,3000),pageErrors:errors})+' | '+error.message);}
      await syncDialog.getByText('زیرساخت سرور هنوز در دسترس نیست').waitFor();
      assert.match(await syncDialog.innerText(),/\/api\/web\/v1/);
      await syncDialog.getByRole('button',{name:'بستن اتصال آنلاین'}).click();
      await page.getByRole('button',{name:'تنظیمات مدار'}).first().click();
      const settingsDialog=page.getByRole('dialog',{name:'تنظیمات مدار'});
      await settingsDialog.waitFor();
      assert.equal(await settingsDialog.getByText('مدیریت هزینه‌ها').count(),0,
        'Financial settings must remain unavailable in the browser edition');
      await settingsDialog.getByRole('button',{name:'بستن'}).click();
      const first=await page.evaluate(async fixture=>{
        const {createWebStorage,decodeWebBackup,WEB_BACKUP_FORMAT}=await import('/src/web_storage.js');
        const store=createWebStorage();
        const initial=await store.read(()=>fixture);
        if(initial.__localRevision!==0)throw Error('Unexpected revision');
        const saved=await store.save({...fixture,__localRevision:0});
        const backup=await store.backup();
        const extracted=decodeWebBackup(backup);
        return {revision:saved.localRevision,format:JSON.parse(backup).format,
          importedTitle:extracted.tasks[0].title,
          preview:localStorage.getItem('madar-preview')};
      },synthetic);
      assert.deepEqual(first,{revision:1,format:'madar-web-local-backup',
        importedTitle:'کارت تست وب',preview:null});
      await page.reload({waitUntil:'domcontentloaded'});
      await page.getByText('کارت تست وب').first().waitFor();
      assert.equal(await page.getByRole('button',{name:'تعریف کاربران'}).count(),0);
      await page.getByRole('button',{name:'پشتیبان‌گیری',exact:true}).first().click();
      const backupDialog=page.getByRole('dialog',{name:'پشتیبان محلی نسخهٔ وب'});
      await backupDialog.waitFor();
      assert.match(await backupDialog.innerText(),/فقط در حافظهٔ همین مرورگر/);
      const downloadPromise=page.waitForEvent('download');
      await backupDialog.getByRole('button',{name:'دریافت پشتیبان JSON'}).click();
      assert.match((await downloadPromise).suggestedFilename(),/^madar-web-backup-\d{4}-\d{2}-\d{2}\.json$/);
      page.on('dialog',prompt=>prompt.accept());
      await backupDialog.locator('input[type=file]').setInputFiles({
        name:'synthetic-web-backup.json',mimeType:'application/json',
        buffer:Buffer.from(JSON.stringify({format:'madar-web-local-backup',
          schema:1,state:synthetic}),'utf8')
      });
      let restored=false;
      for(let attempt=0;attempt<35;attempt++){
        restored=await page.evaluate(async()=>{
          const {createWebStorage}=await import('/src/web_storage.js');
          const state=await createWebStorage().read(()=>null);
          return state.__localRevision===2&&state.tasks.length===1;
        });
        if(restored)break;
        await page.waitForTimeout(100);
      }
      assert.equal(restored,true,'Imported web backup must be durably committed');
      await backupDialog.waitFor({state:'hidden'});
      await page.locator('.kanban-lane .lane-add-card').first().click();
      await page.getByRole('textbox',{name:'عنوان کارت جدید'}).fill('کارت جدید از وب');
      await page.locator('.lane-quick-add__save').first().click();
      let cardSaved=false;
      for(let attempt=0;attempt<45;attempt++){
        cardSaved=await page.evaluate(async()=>{
          const {createWebStorage}=await import('/src/web_storage.js');
          const state=await createWebStorage().read(()=>null);
          return state.__localRevision>=3&&state.tasks.some(card=>card.title==='کارت جدید از وب');
        });
        if(cardSaved)break;
        await page.waitForTimeout(100);
      }
      assert.equal(cardSaved,true,'New card must be durably saved before browser reload');
      await page.reload({waitUntil:'domcontentloaded'});
      try {
        await page.getByText('کارت جدید از وب').first().waitFor({timeout:8000});
      } catch(error) {
        const diagnosis=await page.evaluate(async()=>{
          const {createWebStorage}=await import('/src/web_storage.js');
          const stored=await createWebStorage().read(()=>null);
          return {titles:stored.tasks.map(item=>({title:item.title,boardId:item.boardId,listId:item.listId,deleted:item.deleted})),
            revision:stored.__localRevision,visible:document.body.innerText.slice(0,2200),
            error:document.querySelector('.loading')?.innerText||null};
        });
        throw Error('Post-reload web card not visible: '+JSON.stringify(diagnosis)+' | '+error.message);
      }

      const concurrent=await page.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const store=createWebStorage();
        const old=await store.read(()=>null);
        await store.save({...old,tasks:old.tasks.map(card=>({...card,title:'نسخه جدید'}))});
        const before=await store.readSyncState();
        try {
          await store.save({...old,tasks:old.tasks.map(card=>({...card,title:'تغییر قدیمی'}))});
          return 'overwrite';
        }catch(error){
          const after=await store.readSyncState();
          return {message:String(error.message),
            pendingTitle:after.pending?.snapshot?.tasks?.[0]?.title,
            pendingIdPreserved:after.pending?.id===before.pending?.id};
        }
      });
      assert.match(concurrent.message,/تب دیگر تغییر کرده/);
      assert.equal(concurrent.pendingTitle,'نسخه جدید');
      assert.equal(concurrent.pendingIdPreserved,true);
      const latest=await page.evaluate(async()=>{
        const {createWebStorage,decodeWebBackup}=await import('/src/web_storage.js');
        const store=createWebStorage();
        let invalid=false;
        try{decodeWebBackup(JSON.stringify({format:'other',schema:1,state:{}}));}
        catch{invalid=true;}
        const state=await store.read(()=>null);
        return {title:state.tasks[0].title,revision:state.__localRevision,invalid};
      });
      assert.deepEqual(latest,{title:'نسخه جدید',revision:4,invalid:true});
      assert.deepEqual(errors,[]);
    }finally{
      if(browser)await browser.close();
      await server.close();
    }
  });

test('web distribution contains install manifest and shell-only service worker',()=>{
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'public','manifest.webmanifest'),'utf8'));
  const sw=fs.readFileSync(path.join(root,'public','service-worker.js'),'utf8');
  assert.equal(manifest.display,'standalone');
  assert.equal(manifest.lang,'fa');
  assert.match(sw,/request\.method!=='GET'/);
  assert.match(sw,/url\.origin!==self\.location\.origin/);
  assert.match(sw,/url\.pathname\.startsWith\('\/api\/'\)/);
  assert.doesNotMatch(sw,/localStorage|indexedDB/);
});

test('IndexedDB v1 upgrades without data loss and v2 atomically journals pending and uncertain sync writes',
  {skip:!runnable,timeout:60000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,mode:'web',logLevel:'error',
      server:{host:'127.0.0.1',port:await reservePort(),strictPort:true,hmr:false}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const page=await browser.newPage();
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      const result=await page.evaluate(async fixture=>{
        const dbName='madar-web-sync-qa-'+Date.now();
        const legacy=await new Promise((resolve,reject)=>{
          const request=indexedDB.open(dbName,1);
          request.onupgradeneeded=()=>request.result.createObjectStore('documents');
          request.onsuccess=()=>resolve(request.result);
          request.onerror=()=>reject(request.error);
        });
        await new Promise((resolve,reject)=>{
          const tx=legacy.transaction('documents','readwrite');
          tx.objectStore('documents').put(fixture,'board-state');
          tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);
        });
        legacy.close();
        const {createWebStorage,WEB_DB_VERSION}=await import('/src/web_storage.js');
        const storage=createWebStorage(indexedDB,{dbName});
        const secondTabStorage=createWebStorage(indexedDB,{dbName});
        const loaded=await storage.read(()=>fixture);
        const preferencesBefore=await storage.getPreferences();
        const firstSave=await storage.save({...loaded,__localRevision:0});
        const firstJob=await storage.claimPending();
        const secondSnapshot={...loaded,tasks:loaded.tasks.map(card=>({...card,title:'ویرایش دوم'}))};
        const secondSave=await storage.save({...secondSnapshot,__localRevision:firstSave.localRevision});
        const whileInFlight=await storage.readSyncState();
        const blockedOtherTab=await secondTabStorage.claimPending();
        await storage.acknowledge(firstJob.id,{revision:'remote-1',etag:'"remote-1"'});
        const secondJob=await storage.claimPending();
        await storage.markUncertain(secondJob.id,{code:'network_unavailable',message:'قطع ارتباط آزمایشی'});
        const retry=await secondTabStorage.claimPending();
        const retryStable=retry.id===secondJob.id&&
          JSON.stringify(retry.snapshot)===JSON.stringify(secondJob.snapshot);
        const remoteSnapshot={...loaded,tasks:loaded.tasks.map(card=>({...card,title:'نسخه سرور'}))};
        const localNow=await storage.read(()=>fixture);
        await storage.recordConflict({localSnapshot:localNow,remoteSnapshot,
          remoteRevision:'remote-2',remoteEtag:'"remote-2"',reason:'revision_conflict'});
        const localResolution=await storage.resolveConflict('local');
        const localJournal=await storage.readSyncState();
        await storage.recordConflict({localSnapshot:await storage.read(()=>fixture),
          remoteSnapshot,remoteRevision:'remote-3',remoteEtag:'"remote-3"'});
        const remoteResolution=await storage.resolveConflict('remote');
        await storage.setPreferences({calendar:'gregorian',widgetSettings:{mode:'compact'}});
        const preferencesAfter=await storage.getPreferences();
        await storage.saveRecovery(remoteSnapshot);
        const recovery=(await storage.getRecovery()).tasks[0].title;
        await storage.clearRecovery();
        const clearedRecovery=await storage.getRecovery();
        const finalState=await storage.read(()=>fixture);
        const localStorageKeys=Object.keys(localStorage);
        await new Promise(resolve=>{
          const request=indexedDB.deleteDatabase(dbName);
          request.onsuccess=request.onerror=request.onblocked=resolve;
        });
        return {
          version:WEB_DB_VERSION,legacyTitle:loaded.tasks[0].title,
          firstRevision:firstSave.localRevision,secondRevision:secondSave.localRevision,
          inFlightPreserved:whileInFlight.inFlight.id===firstJob.id,
          secondTabBlocked:blockedOtherTab===null,
          pendingCoalesced:whileInFlight.pending.snapshot.tasks[0].title==='ویرایش دوم',
          ackRevision:(await Promise.resolve(localJournal.remoteRevision)),
          retryStable,localResolutionTitle:localResolution.tasks[0].title,
          localResolutionQueued:!!localJournal.pending,
          remoteResolutionTitle:remoteResolution.tasks[0].title,
          preferencesBefore,preferencesAfter,recovery,clearedRecovery,
          finalRevision:finalState.__localRevision,
          localStorageHasPreferences:localStorageKeys.includes('madar-preferences'),
        };
      },synthetic);
      assert.equal(result.version,2);
      assert.equal(result.legacyTitle,'کارت تست وب');
      assert.equal(result.firstRevision,1);
      assert.equal(result.secondRevision,2);
      assert.equal(result.inFlightPreserved,true);
      assert.equal(result.secondTabBlocked,true);
      assert.equal(result.pendingCoalesced,true);
      assert.equal(result.ackRevision,'remote-2');
      assert.equal(result.retryStable,true);
      assert.equal(result.localResolutionTitle,'ویرایش دوم');
      assert.equal(result.localResolutionQueued,true);
      assert.equal(result.remoteResolutionTitle,'نسخه سرور');
      assert.equal(result.preferencesBefore.calendar,'jalali');
      assert.equal(result.preferencesAfter.calendar,'gregorian');
      assert.equal(result.recovery,'نسخه سرور');
      assert.equal(result.clearedRecovery,null);
      assert.equal(result.finalRevision,3);
      assert.equal(result.localStorageHasPreferences,false);
    }finally{
      if(browser)await browser.close();
      await server.close();
    }
  });

test('production PWA installs offline shell and reopens without network',
  {skip:!runnable||!fs.existsSync(path.join(root,'dist-web','index.html')),timeout:70000},
  async()=>{
    const {preview}=await import('vite');
    const {chromium}=require(playwrightHome);
    const port=await reservePort();
    const server=await preview({root,mode:'web',build:{outDir:'dist-web'},
      preview:{host:'127.0.0.1',port,strictPort:true}});
    let browser;
    try{
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:420,height:860}});
      const page=await context.newPage();
      const failures=[];
      const networkFailures=[];
      page.on('pageerror',err=>failures.push(err.message));
      page.on('requestfailed',request=>networkFailures.push({
        url:request.url(),error:request.failure()?.errorText}));
      await page.goto('http://127.0.0.1:'+port+'/',{waitUntil:'load'});
      await page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor();
      const service=await page.evaluate(async()=>{
        const ready=await navigator.serviceWorker.ready;
        await new Promise((resolve,reject)=>{
          if(navigator.serviceWorker.controller)return resolve();
          const timeout=setTimeout(()=>reject(Error('Service worker did not claim page')),6000);
          navigator.serviceWorker.addEventListener('controllerchange',()=>{
            clearTimeout(timeout);resolve();
          },{once:true});
        });
        const cache=await caches.open('madar-pwa-shell-1.0.22-2');
        const keys=(await cache.keys()).map(entry=>new URL(entry.url).pathname);
        return {scope:ready.scope,css:keys.some(key=>/\.css$/.test(key)),
          js:keys.some(key=>/\.js$/.test(key)),html:keys.some(key=>/index\.html$/.test(key))};
      });
      assert.equal(service.css,true,'Stylesheets must be cached from first install');
      assert.equal(service.js,true,'Entrypoint JS must be cached from first install');
      assert.equal(service.html,true,'Offline page must be cached');
      // Chrome's module loader may attempt its first controlled reload before
      // the newly claiming worker has settled; exercise one online controlled
      // navigation before cutting network access.
      await page.reload({waitUntil:'domcontentloaded'});
      await page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor();
      await context.setOffline(true);
      await page.reload({waitUntil:'domcontentloaded'});
      try {
        await page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor({timeout:7000});
      } catch(error) {
        const diagnosis=await page.evaluate(async()=>{
          const names=await caches.keys();
          const keys=await caches.open('madar-pwa-shell-1.0.22-2').then(c=>c.keys());
          const script=keys.find(item=>item.url.endsWith('.js'));
          const jsResponse=script?await caches.match(script):null;
          let fetched=null;
          try {
            const response=await fetch(script.url);
            fetched={ok:response.ok,status:response.status};
          }catch(error){fetched=String(error.message||error);}
          return {href:location.href,readyState:document.readyState,
            body:document.body.innerText.slice(0,1200),
            html:document.documentElement.outerHTML.slice(0,1000),
            cacheNames:names,cacheKeys:keys.map(item=>item.url),
            controller:navigator.serviceWorker.controller?.scriptURL,
            cacheJs:jsResponse?{ok:jsResponse.ok,status:jsResponse.status,
              length:Number(jsResponse.headers.get('content-length')||0)}:null,
            fetchJs:fetched};
        });
        throw Error('Offline PWA failed: '+JSON.stringify({
          diagnosis,networkFailures,pageerrors:failures})+' | '+error.message);
      }
      assert.deepEqual(failures,[]);
    } finally {
      if(browser)await browser.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });
