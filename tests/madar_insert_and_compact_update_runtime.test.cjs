'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const available=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);
const stage={id:'todo',label:'انجام',color:'#4e9dcd',subtitle:''};
const timestamp='2026-10-20T12:00:00Z';
const fixture={
  version:1,
  projects:[{id:'p',name:'پروژه ایزوله',color:'#4e9dcd',costEnabled:false,price:0}],
  workspaces:[{id:'w',name:'فضای ایزوله',archived:false}],
  boards:[{id:'b',workspaceId:'w',projectId:'p',name:'برد درج کارت',archived:false,stages:[stage]}],
  stages:[stage],
  tasks:['اول','دوم'].map((title,i)=>({id:'c'+i,boardId:'b',projectId:'p',listId:'todo',
    status:'todo',title,description:'',priority:'medium',cardOrder:i*1024,
    labels:[],checklist:[],reports:[],dueDate:'',createdAt:timestamp,updatedAt:timestamp})),
  settings:{theme:'dark',costDefault:false}
};

const freePort=()=>new Promise((resolve,reject)=>{
  const socket=net.createServer();
  socket.once('error',reject);
  socket.listen(0,'127.0.0.1',()=>{
    const port=socket.address().port;
    socket.close(error=>error?reject(error):resolve(port));
  });
});

test('inserting between existing cards reserves space immediately and outside click cancels empty draft',
  {skip:!available,timeout:60000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',server:{host:'127.0.0.1',
      port:await freePort(),strictPort:true,hmr:false}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const page=await browser.newPage({viewport:{width:1440,height:900},locale:'fa-IR'});
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.addInitScript(data=>localStorage.setItem('madar-preview',JSON.stringify(data)),fixture);
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      const lane=page.locator('.kanban-lane').first();
      await lane.locator('.task-card').first().waitFor();
      assert.equal(await lane.locator('.task-card').count(),2);

      const insertion=lane.getByRole('button',{name:'افزودن کارت پیش از دوم'});
      await insertion.hover();
      await insertion.click();
      const composer=lane.locator('.lane-insert-slot .lane-quick-add');
      await composer.waitFor({state:'visible'});
      const measurements=await lane.evaluate(el=>{
        const form=el.querySelector('.lane-insert-slot .lane-quick-add');
        const slot=form?.closest('.lane-insert-slot');
        const next=form?.closest('.progressive-lane-card')?.querySelector('.task-card');
        const formBox=form?.getBoundingClientRect();
        const nextBox=next?.getBoundingClientRect();
        return {slotHeight:slot?.getBoundingClientRect().height||0,
          formBottom:formBox?.bottom||0,secondTop:nextBox?.top||0};
      });
      assert.ok(measurements.slotHeight>=measurements.formBottom-measurements.secondTop+1,
        'Composer slot must occupy its own height '+JSON.stringify(measurements));
      assert.ok(measurements.secondTop>=measurements.formBottom-2,
        'Second card must not overlap open composer '+JSON.stringify(measurements));

      await lane.locator('.lane-head').click();
      assert.equal(await lane.locator('.lane-quick-add').count(),0,
        'Outside click should cancel an empty insertion without Enter');
      assert.equal(await lane.locator('.task-card').count(),2);
      const data=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')));
      assert.equal(data.tasks.length,2,'Cancelled composer must not create any cards');

      const dock=page.locator('.vitrea-quickdock');
      await dock.locator('.vitrea-quickdock__refresh').hover();
      assert.ok((await dock.boundingBox()).width<=65,'Hover must not expand sidebar rail');
      assert.equal(await dock.locator('.vitrea-quickdock__update').count(),1);
      await dock.locator('.vitrea-quickdock__main').click();
      const sidebar=page.locator('#madar-sidebar');
      await sidebar.waitFor({state:'visible'});
      assert.ok((await sidebar.boundingBox()).width<=276,'Expanded menu should remain compact');
      assert.equal(await sidebar.locator('.sidebar-update').count(),1);
      assert.equal(await sidebar.getByRole('button',{name:'مدیریت برچسب‌ها'}).count(),1);
      assert.deepEqual(errors,[]);
    }finally{
      if(browser)await browser.close();
      await server.close();
    }
  });
