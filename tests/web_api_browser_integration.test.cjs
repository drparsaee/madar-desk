'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const http=require('node:http');
const {createMadarWebApiStub}=require('./helpers/madar_web_api_stub.cjs');

const root=path.resolve(__dirname,'..');
const chrome=[process.env.MADAR_CHROME_PATH,
  path.join(process.env.PROGRAMFILES||'C:\\Program Files','Google','Chrome','Application','chrome.exe'),
  path.join(process.env.LOCALAPPDATA||'','Google','Chrome','Application','chrome.exe'),
].find(candidate=>candidate&&fs.existsSync(candidate));
let playwright=null;
for(const candidate of ['playwright',path.join(process.env.APPDATA||'',
  'npm','node_modules','playwright')]){
  try{playwright=require(candidate);break;}catch{/* Try another installed location. */}
}

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

test('browser login, first-upload confirmation, conditional sync, conflict preservation and remote acceptance',
  {skip:!chrome||!playwright,timeout:90000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=playwright;
    const apiStub=createMadarWebApiStub();
    const apiServer=http.createServer(apiStub.handler);
    const apiPort=await reservePort();
    await new Promise((resolve,reject)=>{
      apiServer.once('error',reject);
      apiServer.listen(apiPort,'127.0.0.1',resolve);
    });
    const server=await createServer({root,mode:'web',logLevel:'error',
      server:{host:'127.0.0.1',port:await reservePort(),strictPort:true,hmr:false,
        proxy:{'/api/web/v1':{target:'http://127.0.0.1:'+apiPort,changeOrigin:false}}}});
    let browser;
    const contexts=[];
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1360,height:900},locale:'fa-IR',acceptDownloads:true});
      contexts.push(context);
      const page=await context.newPage();
      const pageErrors=[];
      page.on('pageerror',error=>pageErrors.push(error.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor();
      await page.getByRole('button',{name:'اتصال آنلاین'}).click();
      const dialog=page.getByRole('dialog',{name:'اتصال آنلاین مدار'});
      await dialog.waitFor();
      // The health/session probes run asynchronously after the dialog opens.
      await dialog.getByLabel('نام کاربری').waitFor({timeout:12000});
      const dialogText=await dialog.innerText();
      if(!dialogText.includes('نام کاربری'))
        throw Error('Test API did not expose login form: '+JSON.stringify({
          dialog:dialogText,requests:apiStub.requests}));
      await dialog.getByLabel('نام کاربری').fill('web-admin');
      await dialog.getByLabel('گذرواژه').fill('test-password');
      await dialog.getByRole('button',{name:'ورود به حساب مدار'}).click();
      const syncButton=dialog.getByRole('button',{name:'همگام‌سازی اکنون'});
      await syncButton.waitFor();
      page.on('dialog',prompt=>prompt.accept());
      await syncButton.click();
      await dialog.getByText('همگام‌سازی سرور تأیید شد.').waitFor();
      assert.equal(apiStub.revision,1,'The first explicit bootstrap must create exactly one remote revision');
      assert.ok(apiStub.snapshot);

      const localSave=await page.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const store=createWebStorage();
        const current=await store.read(()=>null);
        const task={id:'web-api-card-1',title:'کارت همگام‌سازی آزمایشی',
          description:'synthetic only',checklist:[{id:'step-1',title:'مرحله آزمایشی',
            done:false,cost:777,expenseItems:[{amount:777}]}],
          labels:[],reports:[],priority:'medium',cost:12345,
          invoiceId:'synthetic-invoice-id',linkedFinanceIds:['synthetic-finance-id'],
          fileLinks:['C:/private/customer-file.pdf']};
        const result=await store.save({...current,tasks:[...current.tasks,task]});
        return result.localRevision;
      });
      assert.ok(localSave>0);
      await syncButton.click();
      await dialog.getByText('همگام‌سازی سرور تأیید شد.').waitFor();
      assert.equal(apiStub.revision,2,'The next conditional write must advance the remote revision once');
      const remoteTask=apiStub.snapshot.tasks.find(task=>task.id==='web-api-card-1');
      assert.ok(remoteTask);
      assert.equal(remoteTask.cost,undefined);
      assert.equal(remoteTask.invoiceId,undefined);
      assert.equal(remoteTask.linkedFinanceIds,undefined);
      assert.equal(remoteTask.fileLinks,undefined);
      assert.equal(remoteTask.checklist[0].cost,undefined);
      assert.equal(remoteTask.checklist[0].expenseItems,undefined);
      const localOnly=await page.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const store=createWebStorage();
        const local=await store.read(()=>null);
        const journal=await store.readSyncState();
        return {cost:local.tasks.find(task=>task.id==='web-api-card-1').cost,
          invoiceId:local.tasks.find(task=>task.id==='web-api-card-1').invoiceId,
          remoteRevision:journal.remoteRevision,
          storageHasCsrf:JSON.stringify(journal).includes('csrfToken'),
          cookieHasSession:document.cookie.includes('madar_web_session')};
      });
      assert.equal(localOnly.cost,12345,'Local browser data remains intact after safe API projection');
      assert.equal(localOnly.invoiceId,'synthetic-invoice-id');
      assert.equal(localOnly.remoteRevision,'r2');
      assert.equal(localOnly.storageHasCsrf,false);
      assert.equal(localOnly.cookieHasSession,false);
      assert.equal(apiStub.idempotencyCount,2);

      const secondContext=await browser.newContext({viewport:{width:1360,height:900},
        locale:'fa-IR',acceptDownloads:true});
      contexts.push(secondContext);
      const secondPage=await secondContext.newPage();
      const secondErrors=[];
      secondPage.on('pageerror',error=>secondErrors.push(error.message));
      // The second browser must explicitly accept its own confirmation dialog.
      // Playwright dismisses unhandled confirm dialogs by default.
      secondPage.on('dialog',prompt=>prompt.accept());
      await secondPage.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await secondPage.getByRole('button',{name:'اتصال آنلاین'}).click();
      const secondDialog=secondPage.getByRole('dialog',{name:'اتصال آنلاین مدار'});
      await secondDialog.waitFor();
      await secondDialog.getByLabel('نام کاربری').waitFor({timeout:12000});
      await secondDialog.getByLabel('نام کاربری').fill('web-admin');
      await secondDialog.getByLabel('گذرواژه').fill('test-password');
      await secondDialog.getByRole('button',{name:'ورود به حساب مدار'}).click();
      try {await secondDialog.getByText('دو نسخهٔ متفاوت وجود دارد').waitFor({timeout:12000});}
      catch(error){throw Error('Second-device conflict did not appear: '+JSON.stringify({
        dialog:await secondDialog.innerText(),errors:secondErrors,
        requests:apiStub.requests,
        journal:await secondPage.evaluate(async()=>{
          const {createWebStorage}=await import('/src/web_storage.js');
          return createWebStorage().readSyncState();
        })})+' | '+error.message);}
      assert.equal(apiStub.revision,2,'A fresh device must not overwrite an existing workspace');
      assert.equal(apiStub.snapshot.tasks.find(task=>task.id==='web-api-card-1').title,
        'کارت همگام‌سازی آزمایشی');
      assert.equal(await secondDialog.getByRole('button',{name:'پذیرش نسخهٔ سرور'}).count(),1);

      const backupDownload=secondPage.waitForEvent('download');
      await secondDialog.getByRole('button',{name:'پذیرش نسخهٔ سرور'}).click();
      const downloaded=await backupDownload;
      assert.match(downloaded.suggestedFilename(),/^madar-web-backup-/);
      try{await secondDialog.getByText('نسخهٔ سرور پذیرفته شد؛ خروجی محلی نیز برای نگهداری آماده شد.').waitFor({timeout:6000});}
      catch(error){throw Error('Remote conflict acceptance did not finish: '+JSON.stringify({
        dialog:await secondDialog.innerText(),errors:secondErrors,
        journal:await secondPage.evaluate(async()=>{
          const {createWebStorage}=await import('/src/web_storage.js');
          return createWebStorage().readSyncState();
        })})+' | '+error.message);}
      const acceptedRemote=await secondPage.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const state=await createWebStorage().read(()=>null);
        return {title:state?.tasks?.find(task=>task.id==='web-api-card-1')?.title,
          revision:state?.__localRevision,keys:Object.keys(state||{})};
      });
      assert.equal(acceptedRemote.title,'کارت همگام‌سازی آزمایشی');
      assert.ok(acceptedRemote.revision>0);
      assert.equal(apiStub.revision,2,'Accepting the server copy must not create a new remote write');

      // A disconnected second device must retain a durable local outbox.
      await secondPage.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const storage=createWebStorage();
        const state=await storage.read(()=>null);
        await storage.save({...state,tasks:[...state.tasks,{
          id:'offline-card',title:'کارت آفلاین دوم',description:'queued while offline',
          checklist:[],labels:[],reports:[],priority:'medium',
        }]});
      });
      await secondContext.setOffline(true);
      await secondDialog.getByRole('button',{name:'همگام‌سازی اکنون'}).click();
      const offlineJournal=await secondPage.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        return createWebStorage().readSyncState();
      });
      assert.ok(offlineJournal.pending||offlineJournal.inFlight,
        'Network loss must never discard local edits');
      assert.equal(apiStub.revision,2,'Offline changes must not reach the server');
      await secondContext.setOffline(false);
      await secondDialog.getByRole('button',{name:'همگام‌سازی اکنون'}).click();
      // The app's online listener can finish the retry before the manual
      // click, in which case the dialog correctly says "already synced".
      for(let attempt=0;apiStub.revision!==3&&attempt<100;attempt++)
        await new Promise(resolve=>setTimeout(resolve,100));
      if(apiStub.revision!==3)throw Error('Offline replay did not reach the stub: '+
        JSON.stringify({dialog:await secondDialog.innerText(),
          journal:await secondPage.evaluate(async()=>{
            const {createWebStorage}=await import('/src/web_storage.js');
            return createWebStorage().readSyncState();
          }),requests:apiStub.requests}));
      assert.equal(apiStub.revision,3);
      assert.ok(apiStub.snapshot.tasks.some(task=>task.id==='offline-card'));

      // Exercise the HTTP contract directly, independently of the React UI.
      const protocol=await secondPage.evaluate(async()=>{
        const route='/api/web/v1';
        const session=await (await fetch(route+'/session',{cache:'no-store'})).json();
        const read=await fetch(route+'/state',{cache:'no-store'});
        const state=(await read.json()).state;
        const etag=read.headers.get('etag');
        const body=JSON.stringify({schemaVersion:1,state});
        const headers={'Content-Type':'application/json',
          'X-CSRF-Token':session.csrfToken,'Idempotency-Key':'browser-replay-1',
          'If-Match':etag};
        const first=await fetch(route+'/state',{method:'PUT',headers,body});
        const firstPayload=await first.json();
        const replay=await fetch(route+'/state',{method:'PUT',headers,body});
        const replayPayload=await replay.json();
        const changedBody=JSON.stringify({schemaVersion:1,state:{...state,
          settings:{...state.settings,theme:'light'}}});
        const changed=await fetch(route+'/state',{method:'PUT',headers,body:changedBody});
        const noCsrf=await fetch(route+'/state',{method:'PUT',headers:{...headers,
          'Idempotency-Key':'browser-no-csrf-1','X-CSRF-Token':''},body});
        const stale=await fetch(route+'/state',{method:'PUT',headers:{...headers,
          'Idempotency-Key':'browser-stale-1'},body});
        const anonymous=await fetch(route+'/state',{credentials:'omit'});
        return {first:first.status,firstPayload,replay:replay.status,replayPayload,
          changed:changed.status,noCsrf:noCsrf.status,stale:stale.status,
          anonymous:anonymous.status};
      });
      assert.equal(protocol.first,200);
      assert.equal(protocol.replay,200);
      assert.deepEqual(protocol.firstPayload,protocol.replayPayload);
      assert.equal(protocol.changed,409,'Reusing a key for another body must fail');
      assert.equal(protocol.noCsrf,403,'Missing CSRF must fail');
      assert.equal(protocol.stale,409,'A stale ETag must not overwrite the server');
      assert.equal(protocol.anonymous,401,'Anonymous reads must be forbidden');
      assert.equal(apiStub.revision,4,'Identical requests must produce only one revision');
      assert.equal(apiStub.idempotencyCount,4);

      // First device still has revision r2. Its subsequent write must conflict.
      await page.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const storage=createWebStorage();
        const state=await storage.read(()=>null);
        await storage.save({...state,tasks:[...state.tasks,{
          id:'competing-card',title:'کارت هم‌زمان دستگاه اول',
          checklist:[],labels:[],reports:[],priority:'medium',
        }]});
      });
      await syncButton.click();
      await dialog.getByText('دو نسخهٔ متفاوت وجود دارد').waitFor();
      const concurrent=await page.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const store=createWebStorage();
        return {local:await store.read(()=>null),journal:await store.readSyncState()};
      });
      assert.ok(concurrent.local.tasks.some(task=>task.id==='competing-card'));
      assert.ok(concurrent.journal.conflict.localSnapshot.tasks.some(task=>task.id==='competing-card'));
      assert.ok(concurrent.journal.conflict.remoteSnapshot.tasks.some(task=>task.id==='offline-card'));
      assert.equal(apiStub.revision,4,'A stale client must not advance the server');

      await secondDialog.getByRole('button',{name:'خروج از حساب'}).click();
      await secondDialog.getByLabel('نام کاربری').waitFor();
      const afterLogout=await secondPage.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const local=await createWebStorage().read(()=>null);
        const session=await fetch('/api/web/v1/session');
        return {hasOfflineCard:local.tasks.some(task=>task.id==='offline-card'),
          sessionStatus:session.status};
      });
      assert.equal(afterLogout.hasOfflineCard,true);
      assert.equal(afterLogout.sessionStatus,401);
      assert.deepEqual(pageErrors,[]);
      assert.deepEqual(secondErrors,[]);
    }finally{
      for(const context of contexts)await context.close();
      if(browser)await browser.close();
      await server.close();
      await new Promise(resolve=>apiServer.close(resolve));
    }
  });
