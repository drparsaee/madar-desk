'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const root=path.resolve(__dirname,'..');
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const available=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);

async function freePort(){
  const server=net.createServer();
  await new Promise((resolve,reject)=>server.once('error',reject).listen(0,'127.0.0.1',resolve));
  const port=server.address().port;
  await new Promise(resolve=>server.close(resolve));
  return port;
}
function assertInsideViewport(bounds,viewport,label){
  assert.ok(bounds.left>=7,`${label}: left ${bounds.left}`);
  assert.ok(bounds.top>=7,`${label}: top ${bounds.top}`);
  assert.ok(bounds.right<=viewport.width-7,`${label}: right ${bounds.right}`);
  assert.ok(bounds.bottom<=viewport.height-7,`${label}: bottom ${bounds.bottom}`);
}

test('calendar floats above a narrow drawer, tracks scrolling and scaled card coordinates',
  {skip:!available,timeout:90000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',server:{host:'127.0.0.1',
      port:await freePort(),strictPort:true,hmr:false,watch:{ignored:['**/research/**']},
      fs:{allow:[root,fs.realpathSync(path.join(root,'node_modules'))]}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:320,height:420},deviceScaleFactor:2,locale:'fa-IR'});
      await context.addInitScript(()=>{
        const stamp='2026-10-20T10:00:00.000Z';
        localStorage.setItem('madar-preview',JSON.stringify({version:1,
          projects:[{id:'p',name:'پروژه تست',color:'#6889bb'}],
          boards:[{id:'b',projectId:'p',workspaceId:'w',name:'برد تست',archived:false,
            stages:[{id:'todo',label:'انجام‌دادنی',color:'#5e82b1'}]}],
          workspaces:[{id:'w',name:'فضای تست',archived:false}],
          stages:[{id:'todo',label:'انجام‌دادنی',color:'#5e82b1'}],
          tasks:[{id:'calendar-edge',projectId:'p',boardId:'b',listId:'todo',status:'todo',
            title:'کارت آزمایش تقویم',description:'',checklist:[],reports:[],assignees:[],labels:[],
            priority:'medium',createdAt:stamp,updatedAt:stamp}],settings:{theme:'light',costDefault:false}}));
        localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      });
      const page=await context.newPage();page.setDefaultTimeout(12000);
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.locator('.task-card .task-title').first().click();
      const drawer=page.getByRole('dialog',{name:'جزئیات کار'});
      await drawer.waitFor();
      const deadline=drawer.getByRole('textbox',{name:'موعد انجام'});
      // The compact app's fixed quick dock can cover the input at 320px.
      // Trigger its native click so this test isolates calendar placement.
      await deadline.evaluate(node=>node.click());
      const calendar=page.getByRole('group',{name:'تقویم انتخاب تاریخ'});
      await calendar.waitFor();
      assert.equal(await calendar.locator('.madar-mini-calendar__days button').count(),42);
      assert.equal(await calendar.evaluate(node=>node.parentNode===document.body),true,
        'popup must escape drawer clipping');
      const bounds=()=>calendar.boundingBox().then(box=>({left:box.x,top:box.y,
        right:box.x+box.width,bottom:box.y+box.height}));
      assertInsideViewport(await bounds(),{width:320,height:420},'initial');
      await drawer.locator('.drawer-scroll').evaluate(node=>{node.scrollTop+=130;node.dispatchEvent(new Event('scroll'));});
      await page.waitForTimeout(100);
      assertInsideViewport(await bounds(),{width:320,height:420},'drawer scrolling');
      await drawer.evaluate(node=>{node.style.transform='scale(0.87)';node.style.transformOrigin='left top';});
      await page.evaluate(()=>window.dispatchEvent(new Event('resize')));
      await page.waitForTimeout(100);
      assertInsideViewport(await bounds(),{width:320,height:420},'scaled drawer');
      await page.setViewportSize({width:240,height:300});
      await page.waitForTimeout(100);
      assertInsideViewport(await bounds(),{width:240,height:300},'smaller resized viewport');
      assert.equal(await calendar.evaluate(node=>node.scrollHeight>node.clientHeight),true,
        'short viewport should scroll inside the calendar instead of clipping');
      await page.setViewportSize({width:320,height:420});
      await calendar.getByRole('button',{name:'انتخاب 2026-11-05'}).click();
      await calendar.waitFor({state:'hidden'});
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview'))
        .tasks[0].dueDate==='2026-11-05');
      await drawer.locator('.calendar-field__open').first().focus();
      await page.keyboard.press('Enter');
      await calendar.waitFor();
      assert.equal(await calendar.locator('button:focus').count(),1,
        'keyboard opening moves focus into the date grid');
      await page.keyboard.press('Escape');
      await calendar.waitFor({state:'hidden'});
      assert.equal(await drawer.locator('.calendar-field__open').first().evaluate(node=>node===document.activeElement),true,
        'Escape returns focus to trigger');
      assert.deepEqual(errors,[]);
    }finally{if(browser)await browser.close();await server.close();}
  });
