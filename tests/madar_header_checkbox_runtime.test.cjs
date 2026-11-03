'use strict';

const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);

const seed={
  version:1,projects:[{id:'qa-project',name:'پروژه آزمون',color:'#6482b1'}],
  workspaces:[{id:'qa-space',name:'فضای QA',archived:false}],
  boards:[{id:'qa-board',name:'برد QA',workspaceId:'qa-space',projectId:'qa-project',
    stages:[{id:'planned',label:'برنامه‌ریزی',color:'#6482b1'}],archived:false}],
  stages:[{id:'planned',label:'برنامه‌ریزی',color:'#6482b1'}],
  tasks:[{id:'qa-task',title:'آزمون محل تیک',status:'planned',listId:'planned',
    projectId:'qa-project',boardId:'qa-board',priority:'medium',description:'',
    checklist:[{id:'qa-step',text:'مرحله بررسی',done:false}],
    labels:[],assignees:[],reports:[],createdAt:'2026-10-20T10:00:00Z',
    updatedAt:'2026-10-20T10:00:00Z'}],
  settings:{theme:'light',costDefault:false}
};

test('Chromium: compact user identity, centered native/custom checkmarks and reduced motion', {
  skip:!runnable,timeout:100000,
},async()=>{
  const {chromium}=require(playwrightHome);
  const {createServer}=await import('vite');
  const server=await createServer({root,logLevel:'error',
    server:{host:'127.0.0.1',port:0,strictPort:false,hmr:false,
      fs:{allow:[root,path.resolve(root,'../madar-desk/node_modules')]},
      watch:{ignored:['**/.*','**/.*/**','**/*.mdf','**/*.ldf',
        '**/*.sqlite3','**/research/**','**/release/**','**/dist/**']}}});
  let browser;
  try{
    await server.listen();
    const port=server.httpServer.address().port;
    browser=await chromium.launch({headless:true,executablePath:chrome});
    const evidence=[];
    for(const width of [1440,480]){
      for(const theme of ['light','dark']){
        for(const reducedMotion of ['no-preference','reduce']){
          const context=await browser.newContext({viewport:{width,height:900},locale:'fa-IR',
            reducedMotion,colorScheme:theme});
          try{
            await context.addInitScript(state=>{
              localStorage.setItem('madar-preview',JSON.stringify(state));
              localStorage.setItem('madar-preferences',JSON.stringify({
                calendar:'jalali',clockWidget:'hidden'}));
            },{...seed,settings:{...seed.settings,theme}});
            const page=await context.newPage();
            page.setDefaultTimeout(10000);
            const errors=[];
            page.on('pageerror',error=>errors.push(error.message));
            await page.goto('http://127.0.0.1:'+port+'/index.html',{waitUntil:'domcontentloaded'});
            const account=page.getByRole('button',{name:'نمایش پروفایل من'});
            await account.waitFor({state:'visible'});
            const accountDims=await account.evaluate(el=>{
              const r=el.getBoundingClientRect();
              const a=el.querySelector('.person-avatar').getBoundingClientRect();
              return {width:r.width,height:r.height,avatarWidth:a.width,avatarHeight:a.height,
                label:el.getAttribute('aria-label'),title:el.querySelector('.person-avatar').title,
                hit:el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))};
            });
            assert.ok(accountDims.width<=40&&accountDims.height<=40,JSON.stringify(accountDims));
            assert.ok(accountDims.avatarWidth<=30&&accountDims.avatarHeight<=30);
            assert.ok(accountDims.hit,'profile control must remain clickable');
            assert.match(accountDims.title,/کاربر محلی · مدیر/,'avatar must preserve human label and role');
            assert.doesNotMatch(accountDims.title,/@local|^local/);

            await account.click();
            const profile=page.locator('.member-modal');
            await profile.waitFor({state:'visible'});
            assert.equal(await profile.getByText('کاربر محلی').count(),1);
            assert.equal(await profile.getByText('@local').count(),0);
            await profile.locator('.dialog-head button').click();

            await page.getByRole('button',{name:'نمای کلی',exact:true}).click();
            await page.locator('.vitrea-overview-task').filter({hasText:'آزمون محل تیک'}).first().click();
            const drawer=page.locator('.drawer');
            await drawer.waitFor({state:'visible'});
            await drawer.locator('#task-section-checklist > summary').click();
            const step=drawer.getByRole('button',{name:'تغییر وضعیت مرحله بررسی'});
            await step.waitFor({state:'visible'});
            await step.click();
            const animation=await step.evaluate(el=>getComputedStyle(el).animationName);
            await page.waitForTimeout(400);
            const custom=await step.evaluate(el=>{
              const r=el.getBoundingClientRect();
              const svg=el.querySelector('svg');
              const icon=svg.getBoundingClientRect();
              return {checked:el.classList.contains('checked'),
                deltaX:Math.abs((icon.x+icon.width/2)-(r.x+r.width/2)),
                deltaY:Math.abs((icon.y+icon.height/2)-(r.y+r.height/2)),
                animation:getComputedStyle(el).animationName,
                label:el.getAttribute('aria-label')};
            });
            assert.ok(custom.checked,JSON.stringify(custom));
            assert.ok(custom.deltaX<=1&&custom.deltaY<=1,JSON.stringify(custom));
            assert.equal(animation,reducedMotion==='reduce'?'none':'madar-check-pop');
            assert.ok(custom.label);

            // Exercise native checklist styling under the real app stylesheet.
            const native=await page.evaluate(()=>{
              const label=document.createElement('label');
              label.className='inline-check-items';
              label.innerHTML='<input type="checkbox" aria-label="مرحله تست بومی"><span>مرحله تست بومی</span>';
              document.querySelector('.drawer-scroll').append(label);
              const input=label.querySelector('input');
              input.click();
              const style=getComputedStyle(input);
              return {checked:input.checked,
                position:style.backgroundPosition,image:style.backgroundImage,
                animation:style.animationName,appearance:style.appearance};
            });
            await page.waitForTimeout(400);
            const nativeSize=await page.locator('.drawer .inline-check-items input[type="checkbox"]')
              .last().evaluate(el=>{const r=el.getBoundingClientRect();
                return {width:r.width,height:r.height};});
            assert.equal(native.checked,true);
            assert.equal(nativeSize.width,18);
            assert.equal(nativeSize.height,18);
            assert.equal(native.position,'50% 50%');
            assert.match(native.image,/data:image\/svg\+xml/);
            assert.equal(native.appearance,'none');
            assert.equal(native.animation,reducedMotion==='reduce'?'none':'madar-check-pop');
            if(width===1440&&reducedMotion==='no-preference'){
              const screenshotDir=path.join(root,'.qa-madar-header-checkbox');
              fs.mkdirSync(screenshotDir,{recursive:true});
              await page.screenshot({path:path.join(screenshotDir,'centered-'+theme+'.png'),
                animations:'disabled'});
            }
            if(width===1440&&theme==='light'&&reducedMotion==='no-preference'){
              await drawer.locator('.drawer-top button[aria-label="بستن"]').click();
              const checklist=page.locator('.kanban .inline-checklist').first();
              await checklist.waitFor({state:'visible'});
              await checklist.locator('.checklist-toggle').click();
              const inlineInput=checklist.locator('.inline-check-items input[type="checkbox"]').first();
              await inlineInput.waitFor({state:'visible'});
              assert.equal(await inlineInput.isChecked(),true);
              await inlineInput.uncheck();
              assert.equal(await inlineInput.isChecked(),false);
              await inlineInput.check();
              assert.equal(await inlineInput.isChecked(),true);
              assert.equal(await inlineInput.evaluate(el=>getComputedStyle(el).animationName),
                'madar-check-pop');

              const cardToggle=page.locator('.kanban .task-complete-toggle').first();
              await cardToggle.waitFor({state:'visible'});
              assert.equal(await cardToggle.getAttribute('aria-pressed'),'false');
              await cardToggle.click();
              assert.equal(await cardToggle.getAttribute('aria-pressed'),'true');
              assert.equal(await cardToggle.evaluate(el=>getComputedStyle(el).animationName),
                'madar-check-pop');
              await page.waitForTimeout(400);
              const delta=await cardToggle.evaluate(el=>{
                const box=el.getBoundingClientRect();
                const mark=el.querySelector('svg').getBoundingClientRect();
                return Math.hypot((box.left+box.width/2)-(mark.left+mark.width/2),
                  (box.top+box.height/2)-(mark.top+mark.height/2));
              });
              assert.ok(delta<=1,'card completion SVG must stay centered: '+delta);
              await cardToggle.click();
              assert.equal(await cardToggle.getAttribute('aria-pressed'),'false');
              assert.equal(await cardToggle.evaluate(el=>getComputedStyle(el).animationName),'none',
                'unchecking must not replay check animation');
            }
            assert.deepEqual(errors,[],JSON.stringify(errors));
            evidence.push({width,theme,reducedMotion,account:accountDims,custom,native});
          }finally{await context.close();}
        }
      }
    }
    assert.equal(evidence.length,8);
    console.log('Madar account/checkmark CSS geometry: 8 responsive/theme/motion combinations checked');
  }finally{
    await browser?.close();
    await server.close();
  }
});

test('LAN directory hides the technical local handle, retains network IDs and roles', {
  skip:!runnable,timeout:30000,
},async()=>{
  const {chromium}=require(playwrightHome);
  const esbuild=require('esbuild');
  const harness=`
    import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {LanPanel,LAN_BUILTIN_DISPLAY_ROLES} from './src/features.jsx';
    const status={mode:'server',port:48370,transport:'https',
      user:{username:'owner',role:'admin'}};
    const api={
      lanUsers:async()=>[
        {username:'local',displayName:'',role:'admin',projects:null},
        {username:'staff-qa',displayName:'کارمند تست',role:'editor',projects:null}],
      lanDisplayRoles:async()=>LAN_BUILTIN_DISPLAY_ROLES
    };
    createRoot(document.getElementById('root')).render(
      React.createElement(LanPanel,{
        api,status,projects:[],initialView:'users',
        onClose:()=>{},onConnected:async()=>{},onRefresh:async()=>{}
      }));
  `;
  const script=esbuild.buildSync({
    stdin:{contents:harness,resolveDir:root,sourcefile:'lan_handle_fixture.jsx',loader:'jsx'},
    bundle:true,write:false,platform:'browser',format:'iife',loader:{'.css':'empty'}
  }).outputFiles[0].text;
  const browser=await chromium.launch({headless:true,executablePath:chrome});
  try{
    const page=await browser.newPage({viewport:{width:1000,height:800},locale:'fa-IR'});
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.setContent('<html lang="fa" dir="rtl"><body><div id="root"></div></body></html>');
    await page.addScriptTag({content:script});
    const rows=page.locator('.lan-density__directory .user-row');
    await rows.nth(1).waitFor();
    const local=rows.filter({hasText:'کاربر محلی'}).first();
    assert.equal(await local.count(),1);
    assert.doesNotMatch(await local.innerText(),/@local|^local/);
    assert.match(await local.innerText(),/مجوز فنی:.*مدیر/s);
    const staff=rows.filter({hasText:'کارمند تست'}).first();
    assert.match(await staff.innerText(),/@staff-qa/);
    assert.match(await staff.innerText(),/ویرایشگر/);
    await local.getByRole('button',{name:'ویرایش'}).click();
    assert.equal(await page.getByLabel('نام کاربری انگلیسی').inputValue(),'local',
      'the account identifier must still be available for authorized editing');
    assert.deepEqual(errors,[]);
  }finally{await browser.close();}
});
