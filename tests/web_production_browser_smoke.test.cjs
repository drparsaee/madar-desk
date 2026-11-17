'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const http=require('node:http');
const net=require('node:net');
const os=require('node:os');
const path=require('node:path');
const {createApp}=require('../server/index.cjs');
const {createUser}=require('../server/storage.cjs');

const root=path.resolve(__dirname,'..');
const webRoot=path.join(root,'dist-web');
const chrome=[process.env.MADAR_CHROME_PATH,
  path.join(process.env.PROGRAMFILES||'C:\\Program Files','Google','Chrome','Application','chrome.exe'),
  path.join(process.env.LOCALAPPDATA||'','Google','Chrome','Application','chrome.exe'),
].find(value=>value&&fs.existsSync(value));
let playwright=null;
for(const candidate of ['playwright',path.join(process.env.APPDATA||'','npm','node_modules','playwright')]){
  try{playwright=require(candidate);break;}catch{/* Try an alternate module location. */}
}
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
  '.mjs':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8',
  '.svg':'image/svg+xml','.png':'image/png','.ico':'image/x-icon',
  '.webmanifest':'application/manifest+json','.woff':'font/woff',
  '.woff2':'font/woff2'};
function freePort(){
  return new Promise((resolve,reject)=>{
    const server=net.createServer();server.once('error',reject);
    server.listen(0,'127.0.0.1',()=>{
      const port=server.address().port;
      server.close(error=>error?reject(error):resolve(port));
    });
  });
}
function createProductionFront({port,apiPort}){
  const csp="default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'";
  const server=http.createServer((req,res)=>{
    const url=new URL(req.url,'http://127.0.0.1:'+port);
    if(url.pathname==='/api/web/v1'||url.pathname.startsWith('/api/web/v1/')){
      const proxy=http.request({hostname:'127.0.0.1',port:apiPort,
        method:req.method,path:req.url,headers:{...req.headers,host:'127.0.0.1:'+apiPort}},upstream=>{
        res.writeHead(upstream.statusCode||502,upstream.headers);upstream.pipe(res);
      });
      proxy.on('error',()=>{if(!res.headersSent){res.writeHead(502,{'Content-Type':'application/json'});res.end('{"error":"upstream_unavailable"}');}});
      req.pipe(proxy);return;
    }
    let pathname;
    try{pathname=decodeURIComponent(url.pathname);}catch{res.writeHead(400);res.end();return;}
    let file=path.resolve(webRoot,'.'+pathname);
    if(file!==webRoot&&!file.startsWith(webRoot+path.sep)){res.writeHead(403);res.end();return;}
    const serve=target=>{
      fs.stat(target,(error,stat)=>{
        if(error||!stat.isFile()){
          if(!path.extname(pathname)&&target!==path.join(webRoot,'index.html'))
            return serve(path.join(webRoot,'index.html'));
          res.writeHead(404);res.end();return;
        }
        const extension=path.extname(target).toLowerCase();
        res.setHeader('Content-Type',mime[extension]||'application/octet-stream');
        res.setHeader('X-Content-Type-Options','nosniff');
        res.setHeader('X-Frame-Options','DENY');
        res.setHeader('Referrer-Policy','strict-origin-when-cross-origin');
        res.setHeader('Permissions-Policy','camera=(), microphone=(), geolocation=()');
        res.setHeader('Content-Security-Policy',csp);
        if(pathname.startsWith('/assets/'))res.setHeader('Cache-Control','public, max-age=31536000, immutable');
        else if(['/','/index.html','/service-worker.js','/manifest.webmanifest'].includes(pathname))
          res.setHeader('Cache-Control','no-cache');
        res.writeHead(200);
        if(req.method==='HEAD'){res.end();return;}
        fs.createReadStream(target).pipe(res);
      });
    };
    serve(file===webRoot?path.join(webRoot,'index.html'):file);
  });
  return server;
}

test('production PWA bundle is served same-origin with real SQLite API and remains navigable offline',
  {skip:!chrome||!playwright||!fs.existsSync(path.join(webRoot,'index.html')),timeout:95000},async()=>{
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'madar-web-prod-smoke-'));
    const frontPort=await freePort(),apiPort=await freePort();
    const origin='http://127.0.0.1:'+frontPort;
    const app=createApp({dbPath:path.join(dir,'web.sqlite'),publicOrigin:origin});
    createUser(app.db,{username:'prod-smoke-admin',displayName:'مدیر تست تولید',
      password:'production-smoke-only-password',role:'admin',workspaceId:'production-smoke'});
    const front=createProductionFront({port:frontPort,apiPort});
    let browser=null;
    const contexts=[];
    try{
      await new Promise((resolve,reject)=>{app.server.once('error',reject);app.server.listen(apiPort,'127.0.0.1',resolve);});
      await new Promise((resolve,reject)=>{front.once('error',reject);front.listen(frontPort,'127.0.0.1',resolve);});
      browser=await playwright.chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1360,height:900},locale:'fa-IR',
        serviceWorkers:'allow',acceptDownloads:true});contexts.push(context);
      const page=await context.newPage();
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      page.on('dialog',dialog=>dialog.accept());
      await page.goto(origin,{waitUntil:'domcontentloaded'});
      await page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor();
      await page.getByRole('button',{name:'اتصال آنلاین'}).click();
      const dialog=page.getByRole('dialog',{name:'اتصال آنلاین مدار'});
      await dialog.getByLabel('نام کاربری').waitFor({timeout:12000});
      await dialog.getByLabel('نام کاربری').fill('prod-smoke-admin');
      await dialog.getByLabel('گذرواژه').fill('production-smoke-only-password');
      await dialog.getByRole('button',{name:'ورود به حساب مدار'}).click();
      await dialog.getByText('مدیر تست تولید').waitFor();
      await dialog.getByRole('button',{name:'همگام‌سازی اکنون'}).click();
      await dialog.getByText('همگام‌سازی سرور تأیید شد.').waitFor();
      const stored=app.db.prepare('SELECT state_json FROM web_workspace_heads WHERE workspace_id=?')
        .get('production-smoke');
      assert.ok(stored,'The production-built browser must persist its snapshot through the API.');
      assert.ok(JSON.parse(stored.state_json).tasks.length>=0);
      const serviceWorker=await page.evaluate(async()=>{
        const registration=await navigator.serviceWorker.ready;
        if(!navigator.serviceWorker.controller)await new Promise(resolve=>{
          navigator.serviceWorker.addEventListener('controllerchange',resolve,{once:true});
        });
        return {scope:registration.scope,controlled:!!navigator.serviceWorker.controller};
      });
      assert.equal(serviceWorker.controlled,true);
      await page.reload({waitUntil:'domcontentloaded'});
      await page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor();
      await context.setOffline(true);
      await page.goto(origin,{waitUntil:'domcontentloaded'});
      await page.getByRole('status',{name:'وضعیت ذخیره‌سازی نسخهٔ وب'}).waitFor();
      assert.equal(await page.title(),'مدار | فضای کار من');
      await context.setOffline(false);
      assert.deepEqual(errors,[]);
    } finally {
      await Promise.all(contexts.map(context=>context.close()));
      if(browser)await browser.close();
      await new Promise(resolve=>front.close(resolve));
      await app.close();
      fs.rmSync(dir,{recursive:true,force:true});
    }
  });
