'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const net=require('node:net');
const {createApp}=require('../server/index.cjs');
const {createUser}=require('../server/storage.cjs');

const root=path.resolve(__dirname,'..');
const chrome=[process.env.MADAR_CHROME_PATH,
  path.join(process.env.PROGRAMFILES||'C:\\Program Files','Google','Chrome','Application','chrome.exe'),
  path.join(process.env.LOCALAPPDATA||'','Google','Chrome','Application','chrome.exe'),
].find(value=>value&&fs.existsSync(value));
let playwright=null;
for(const candidate of ['playwright',path.join(process.env.APPDATA||'','npm','node_modules','playwright')]){
  try{playwright=require(candidate);break;}catch{/* Try an alternate module location. */}
}
function freePort(){
  return new Promise((resolve,reject)=>{
    const server=net.createServer();
    server.once('error',reject);
    server.listen(0,'127.0.0.1',()=>{
      const port=server.address().port;
      server.close(error=>error?reject(error):resolve(port));
    });
  });
}

test('real SQLite web API: browser account, durable write, financial isolation and second-device import',
  {skip:!chrome||!playwright,timeout:95000},async()=>{
    const {createServer}=await import('vite');
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'madar-web-pwa-real-browser-'));
    const appPort=await freePort();
    const backendPort=await freePort();
    const publicOrigin='http://127.0.0.1:'+appPort;
    const app=createApp({dbPath:path.join(dir,'web.sqlite'),publicOrigin});
    createUser(app.db,{username:'browser-admin',displayName:'مدیر آزمایشی مرورگر',
      password:'only-for-real-browser-test-1234',role:'admin',workspaceId:'browser-team'});
    let vite=null,browser=null;
    const contexts=[];
    try{
      await new Promise((resolve,reject)=>{
        app.server.once('error',reject);
        app.server.listen(backendPort,'127.0.0.1',resolve);
      });
      vite=await createServer({root,mode:'web',logLevel:'error',
        server:{host:'127.0.0.1',port:appPort,strictPort:true,hmr:false,
          proxy:{'/api/web/v1':{target:'http://127.0.0.1:'+backendPort,
            changeOrigin:false}}}});
      await vite.listen();
      browser=await playwright.chromium.launch({headless:true,executablePath:chrome});
      const makePage=async()=>{
        const context=await browser.newContext({viewport:{width:1360,height:900},
          locale:'fa-IR',acceptDownloads:true});
        contexts.push(context);
        const page=await context.newPage();
        page.on('dialog',prompt=>prompt.accept());
        const errors=[];
        page.on('pageerror',error=>errors.push(error.message));
        await page.goto(publicOrigin,{waitUntil:'domcontentloaded'});
        await page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor();
        await page.getByRole('button',{name:'اتصال آنلاین'}).click();
        const dialog=page.getByRole('dialog',{name:'اتصال آنلاین مدار'});
        await dialog.getByLabel('نام کاربری').waitFor({timeout:12000});
        await dialog.getByLabel('نام کاربری').fill('browser-admin');
        await dialog.getByLabel('گذرواژه').fill('only-for-real-browser-test-1234');
        await dialog.getByRole('button',{name:'ورود به حساب مدار'}).click();
        await dialog.getByText('مدیر آزمایشی مرورگر').waitFor();
        return {context,page,dialog,errors};
      };
      const first=await makePage();
      await first.dialog.getByRole('button',{name:'همگام‌سازی اکنون'}).click();
      await first.dialog.getByText('همگام‌سازی سرور تأیید شد.').waitFor();
      assert.equal(app.db.prepare('SELECT count(*) c FROM web_workspace_heads').get().c,1);

      // The real web app's seed, stages, boards and UX fields are sent through
      // the actual browser client. Sensitive native cost/path fields stay local.
      await first.page.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const store=createWebStorage();
        const state=await store.read(()=>null);
        const stage=state.stages[0];
        const project={id:'real-project',name:'پروژه مرورگر',color:'#228877',
          costEnabled:true,price:90000,fileLinks:['C:/private/project']};
        const board={id:'real-board',workspaceId:state.workspaces[0].id,
          projectId:project.id,name:'برد مرورگر',color:'#228877',archived:false,
          stages:state.stages,labelDefinitions:[],customFields:[]};
        const task={id:'real-task',projectId:project.id,boardId:board.id,
          listId:stage.id,status:stage.id,title:'کارت مرورگر',description:'ثبت واقعی',
          priority:'medium',completed:false,labels:[],checklist:[{id:'step',
            text:'گام اول',done:false,cost:500}],reports:[{id:'report',
            agent:'Tester',summary:'گزارش عادی کار',createdAt:'2026-11-06T12:00:00.000Z'}],
          assignees:[],cost:999,invoiceId:'invoice-secret',
          fileLinks:['C:/private/invoice.pdf'],createdAt:'2026-11-06T12:00:00.000Z'};
        await store.save({...state,projects:[...state.projects,project],
          boards:[...state.boards,board],tasks:[...state.tasks,task],
          settings:{...state.settings,googleClientId:'secret-app-client-id'}});
      });
      await first.dialog.getByRole('button',{name:'همگام‌سازی اکنون'}).click();
      await first.dialog.getByText('همگام‌سازی سرور تأیید شد.').waitFor();
      const remote=JSON.parse(app.db.prepare(`SELECT state_json FROM web_workspace_heads
        WHERE workspace_id=?`).get('browser-team').state_json);
      assert.equal(remote.tasks[0].title,'کارت مرورگر');
      assert.equal(remote.tasks[0].cost,undefined);
      assert.equal(remote.tasks[0].invoiceId,undefined);
      assert.equal(remote.tasks[0].fileLinks,undefined);
      assert.equal(remote.tasks[0].checklist[0].cost,undefined);
      assert.equal(remote.projects[0].price,undefined);
      assert.equal(remote.settings.googleClientId,undefined);
      assert.equal(remote.tasks[0].reports[0].summary,'گزارش عادی کار');

      const second=await makePage();
      await second.dialog.getByText('دو نسخهٔ متفاوت وجود دارد').waitFor({timeout:10000});
      const originalRevision=app.db.prepare(`SELECT revision FROM web_workspace_heads
        WHERE workspace_id=?`).get('browser-team').revision;
      const pendingDownload=second.page.waitForEvent('download');
      await second.dialog.getByRole('button',{name:'پذیرش نسخهٔ سرور'}).click();
      await pendingDownload;
      await second.dialog.getByText('نسخهٔ سرور پذیرفته شد؛ خروجی محلی نیز برای نگهداری آماده شد.').waitFor();
      const imported=await second.page.evaluate(async()=>{
        const {createWebStorage}=await import('/src/web_storage.js');
        const state=await createWebStorage().read(()=>null);
        return {title:state.tasks[0].title,localCost:state.tasks[0].cost,
          reports:state.tasks[0].reports.length};
      });
      assert.equal(imported.title,'کارت مرورگر');
      assert.equal(imported.localCost,undefined);
      assert.equal(imported.reports,1);
      assert.equal(app.db.prepare(`SELECT revision FROM web_workspace_heads
        WHERE workspace_id=?`).get('browser-team').revision,originalRevision);
      assert.deepEqual(first.errors,[]);
      assert.deepEqual(second.errors,[]);
    } finally {
      for(const context of contexts)await context.close();
      if(browser)await browser.close();
      if(vite)await vite.close();
      await app.close();
      fs.rmSync(dir,{recursive:true,force:true});
    }
  });
