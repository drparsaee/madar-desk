'use strict';
// Browser-only acceptance. Never touches the installed EXE or APPDATA profile.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const available=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);
const stages=[{id:'planned',label:'در انتظار',subtitle:'',color:'#5678ab'}];
const fixture={version:1,workspaces:[{id:'w',name:'فضای آزمایشی',archived:false}],
  projects:[{id:'p',name:'پروژه آزمایشی',costEnabled:false,price:0}],
  boards:[{id:'b',name:'برد آزمایشی',workspaceId:'w',projectId:'p',archived:false,stages,
    labelDefinitions:[],customFields:[]}],stages,
  tasks:['کارت اول','کارت دوم'].map((title,i)=>({id:'task-'+i,projectId:'p',boardId:'b',
    listId:'planned',status:'planned',priority:'medium',title,labels:[],checklist:[],
    reports:[],description:'',cost:0,assignees:[],createdAt:'2026-11-05T10:00:00.000Z'})),
  settings:{theme:'dark',costDefault:false}};

async function freePort(){
  for(let i=0;i<40;i++){
    const server=net.createServer();
    try{return await new Promise((resolve,reject)=>{
      server.once('error',reject);
      server.listen(0,'127.0.0.1',()=>{const port=server.address().port;
        server.close(err=>err?reject(err):resolve(port));});
    });}catch(err){if(err.code!=='EADDRINUSE')throw err;}
  }
  throw Error('Could not obtain a loopback test port');
}

test('shared labels are reusable but never automatically applied; complete icon shares title row',
  {skip:!available,timeout:110000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',
      server:{host:'127.0.0.1',port:await freePort(),strictPort:true,hmr:false,
        watch:{ignored:['**/.qa-*','**/.qa-*/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      for(const [width,theme] of [[1440,'dark'],[480,'light']]){
        const context=await browser.newContext({viewport:{width,height:900},locale:'fa-IR'});
        await context.addInitScript(state=>{
          localStorage.setItem('madar-preview',JSON.stringify(state));
          localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
        },{...fixture,settings:{...fixture.settings,theme}});
        const page=await context.newPage();
        const errors=[];page.on('pageerror',err=>errors.push(err.message));
        page.setDefaultTimeout(13000);
        try{
          await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
          await page.getByRole('button',{name:'نمای کلی',exact:true}).click();
          await page.locator('.board-tabs').getByRole('button',{name:'برد کارها',exact:true}).click();
          const first=page.locator('.kanban .task-card').filter({hasText:'کارت اول'}).first();
          const second=page.locator('.kanban .task-card').filter({hasText:'کارت دوم'}).first();
          await first.waitFor();
          const geometry=await first.evaluate(node=>{
            const title=node.querySelector('.task-title').getBoundingClientRect();
            const button=node.querySelector('.task-complete-toggle').getBoundingClientRect();
            const heading=node.querySelector('.task-card-head').getBoundingClientRect();
            return {centerDiff:Math.abs((title.top+title.bottom)/2-(button.top+button.bottom)/2),
              buttonWidth:button.width,buttonHeight:button.height,headerHeight:heading.height,
              titleWidth:title.width};
          });
          assert.ok(geometry.centerDiff<=8,JSON.stringify(geometry));
          assert.ok(geometry.buttonWidth<=20&&geometry.buttonHeight<=20,JSON.stringify(geometry));
          assert.ok(geometry.titleWidth>60&&geometry.headerHeight<38,JSON.stringify(geometry));

          await first.locator('.task-title').click();
          let drawer=page.getByRole('dialog',{name:'جزئیات کار'});
          await drawer.waitFor();
          await drawer.getByRole('button',{name:'برچسب',exact:true}).click();
          let picker=drawer.locator('.task-quick-popover');
          await picker.getByRole('button',{name:'ساخت برچسب مشترک'}).click();
          await picker.getByRole('textbox',{name:'نام برچسب جدید'}).fill('بازبینی');
          await picker.getByRole('button',{name:'افزودن برچسب'}).click();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).settings.labelLibrary?.some(l=>l.name==='بازبینی')===true);
          let state=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')));
          assert.deepEqual(state.tasks.map(t=>t.labels),[[],[]],
            'creating a label cannot silently check it on any card');
          await picker.getByRole('checkbox',{name:'انتخاب برچسب بازبینی'}).check();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].labels.includes('بازبینی'));
          await picker.getByRole('button',{name:'ویرایش برچسب بازبینی'}).click();
          await picker.getByRole('textbox',{name:'نام جدید برچسب بازبینی'}).fill('آماده');
          await picker.getByRole('button',{name:'ذخیره',exact:true}).click();
          await page.waitForFunction(()=>{
            const state=JSON.parse(localStorage.getItem('madar-preview'));
            return state.settings.labelLibrary?.some(l=>l.name==='آماده')&&state.tasks[0].labels.includes('آماده');
          });
          await drawer.getByRole('button',{name:'بستن',exact:true}).first().click();
          assert.equal(await first.locator('.colored-label').count(),1);
          assert.equal(await second.locator('.colored-label').count(),0);

          await second.locator('.task-title').click();
          drawer=page.getByRole('dialog',{name:'جزئیات کار'});
          await drawer.getByRole('button',{name:'برچسب',exact:true}).click();
          picker=drawer.locator('.task-quick-popover');
          const availableLabel=picker.getByRole('checkbox',{name:'انتخاب برچسب آماده'});
          assert.equal(await availableLabel.isChecked(),false,
            'other cards should see the shared label as an unchecked option');
          await availableLabel.check();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[1].labels.includes('آماده'));
          await availableLabel.uncheck();
          await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[1].labels.length===0);
          state=await page.evaluate(()=>JSON.parse(localStorage.getItem('madar-preview')));
          assert.deepEqual(state.tasks.map(t=>t.labels),[['آماده'],[]]);
          assert.equal(state.settings.labelLibrary[0].name,'آماده');
          assert.deepEqual(errors,[]);
          console.log('SHARED_LABEL_CARD_RUNTIME_PASSED',width,theme,geometry);
        }finally{await context.close();}
      }
    }finally{await browser?.close();await server.close();}
  });
