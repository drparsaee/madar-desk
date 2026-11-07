'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const root=path.resolve(__dirname,'..');
const chrome=[process.env.MADAR_CHROME_PATH,
  path.join(process.env.PROGRAMFILES||'C:\\Program Files','Google','Chrome','Application','chrome.exe'),
  path.join(process.env.LOCALAPPDATA||'','Google','Chrome','Application','chrome.exe')
].find(value=>value&&fs.existsSync(value));
let playwright=null;
for(const candidate of ['playwright',path.join(process.env.APPDATA||'','npm','node_modules','playwright')]){
  try{playwright=require(candidate);break;}catch{}
}
const freePort=()=>new Promise((resolve,reject)=>{
  const server=net.createServer();server.once('error',reject);
  server.listen(0,'127.0.0.1',()=>{
    const port=server.address().port;
    server.close(error=>error?reject(error):resolve(port));
  });
});

test('real Chromium: RTL Gantt drag does not open a card; calendar scale, viewer and chat permissions work',
  {skip:!chrome||!playwright,timeout:45000},async()=>{
    const {createServer}=await import('vite');
    const port=await freePort();let vite=null,browser=null;
    try{
      vite=await createServer({root,mode:'web',logLevel:'error',server:{
        host:'127.0.0.1',port,strictPort:true,hmr:false}});
      await vite.listen();
      browser=await playwright.chromium.launch({headless:true,executablePath:chrome});
      const page=await browser.newPage({viewport:{width:1400,height:900}});
      page.on('dialog',dialog=>dialog.accept());
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.goto('http://127.0.0.1:'+port+'/tests/fixtures/madar-gantt-chat.html');
      await page.waitForFunction(()=>typeof window.mountGantt==='function');
      await page.evaluate(()=>window.mountGantt());
      const bar=page.getByRole('button',{name:'نوار فعالیت اول'});
      await bar.waitFor();
      assert.equal(await page.locator('.gantt-arrows path').count()>0,true);
      const alignment=await page.evaluate(()=>{
        const track=document.querySelector('.gantt-track').getBoundingClientRect();
        const arrows=document.querySelector('.gantt-arrows').getBoundingClientRect();
        return {deltaX:Math.abs(track.left-arrows.left),deltaWidth:Math.abs(track.width-arrows.width)};
      });
      assert.ok(alignment.deltaX<2&&alignment.deltaWidth<2,
        'dependency SVG must use the same horizontal coordinates as the RTL timeline');
      await bar.scrollIntoViewIfNeeded();
      const bounds=await bar.boundingBox();
      assert.ok(bounds&&bounds.x>=0&&bounds.x+bounds.width<=1400,
        'Gantt bar should be scrolled into the visible Chromium viewport');
      await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2);
      await page.mouse.down();
      await page.mouse.move(bounds.x+bounds.width/2+44,bounds.y+bounds.height/2,{steps:5});
      await page.mouse.up();
      const afterDrag=await page.evaluate(()=>window.testActions);
      assert.equal(afterDrag.updated.length,1);
      assert.deepEqual(afterDrag.updated[0],{id:'one',patch:{
        plannedStart:'2026-11-08',plannedEnd:'2026-11-10'}});
      assert.deepEqual(afterDrag.opened,[],'pointer drag must not open editor');
      await bar.click();
      assert.deepEqual((await page.evaluate(()=>window.testActions.opened)),['one']);
      await page.getByLabel('مقیاس گانت').selectOption('week');
      assert.equal(await page.locator('.gantt-axis-cell').count(),24);
      await page.getByLabel('مقیاس گانت').selectOption('month');
      assert.equal(await page.locator('.gantt-axis-cell').count(),18);
      await page.evaluate(()=>window.mountGantt(false));
      assert.equal(await page.getByLabel('شروع فعالیت اول').isDisabled(),true);
      await page.evaluate(()=>window.mountChat('viewer',false,false));
      await page.getByText('پیام علی').waitFor();
      assert.equal(await page.getByRole('button',{name:'ارسال پیام'}).count(),0);
      assert.equal(await page.getByTitle('حذف نظر').count(),0);
      await page.evaluate(()=>window.mountChat('admin',true,true));
      await page.getByTitle('حذف نظر').first().waitFor();
      assert.equal(await page.getByTitle('حذف نظر').count(),2);
      assert.equal(await page.getByTitle('ویرایش نظر').count(),0,
        'admin may delete but must not edit another author message');
      await page.evaluate(()=>window.mountChat('ali',true,false));
      assert.equal(await page.getByTitle('ویرایش نظر').count(),1);
      assert.equal(await page.getByTitle('حذف نظر').count(),1);
      const compose=page.getByPlaceholder('پیام بنویس؛ با @username به کاربر اشاره کن.');
      await compose.fill('ارسال از رابط کاربری');
      await page.getByRole('button',{name:'ارسال پیام'}).click();
      await page.getByText('ارسال از رابط کاربری').waitFor();
      await page.getByTitle('پاسخ').first().click();
      await compose.fill('پاسخ از رابط کاربری');
      await page.getByRole('button',{name:'ارسال پیام'}).click();
      await page.getByText('پاسخ از رابط کاربری').waitFor();
      const commands=await page.evaluate(()=>window.testActions.commands);
      assert.equal(commands.at(-1).type,'comment.reply');
      assert.equal(commands.at(-1).replyToId,'a');
      await page.getByTitle('ویرایش نظر').first().click();
      await page.locator('.comment-thread textarea').fill('متن اصلاح‌شده');
      await page.getByRole('button',{name:'ذخیره'}).click();
      await page.getByText('متن اصلاح‌شده').waitFor();
      await page.getByTitle('حذف نظر').first().click();
      await page.getByText('پیام حذف شده است.').waitFor();
      assert.deepEqual(errors,[]);
    }finally{
      if(browser)await browser.close();
      if(vite)await vite.close();
    }
  });
