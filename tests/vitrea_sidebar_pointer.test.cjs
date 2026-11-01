'use strict';
/* Isolated Chromium hit-testing; preview mode never watches private SQL files. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const root=path.resolve(__dirname,'..');
const binary='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPackage='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const available=fs.existsSync(binary)&&fs.existsSync(playwrightPackage);

const stages=[
  {id:'todo',label:'در صف',subtitle:'',color:'#739ce4'},
  {id:'done',label:'انجام شده',subtitle:'',color:'#54ac90'}
];
const state={
  version:1,
  projects:[{id:'project-qa',name:'پروژه QA',color:'#739ce4',costEnabled:false,price:0}],
  workspaces:[{id:'workspace-qa',name:'فضای آزمون',archived:false}],
  boards:[{id:'board-qa',workspaceId:'workspace-qa',projectId:'project-qa',
    name:'برد آزمایشی QA',color:'#739ce4',archived:false,stages}],
  tasks:[],stages,settings:{theme:'dark',costDefault:false},
};
async function freePort(){
  return new Promise((resolve,reject)=>{
    const server=net.createServer();
    server.once('error',reject);
    server.listen(0,'127.0.0.1',()=>{
      const port=server.address().port;
      server.close(e=>e?reject(e):resolve(port));
    });
  });
}
async function hitTarget(locator){
  return locator.evaluate(el=>{
    const bounds=el.getBoundingClientRect();
    const x=bounds.left+bounds.width/2,y=bounds.top+bounds.height/2;
    const hit=document.elementFromPoint(x,y);
    const ancestors=[];
    for(let item=el;item;item=item.parentElement){
      const box=item.getBoundingClientRect(),style=getComputedStyle(item);
      ancestors.push({
        tag:item.tagName,cls:item.className,
        top:Math.round(box.top),bottom:Math.round(box.bottom),
        height:Math.round(box.height),clientHeight:item.clientHeight,scrollHeight:item.scrollHeight,
        scrollTop:item.scrollTop,overflowY:style.overflowY,flexShrink:style.flexShrink,
        pointerEvents:style.pointerEvents,inert:item.inert,
      });
      if(item.id==='madar-sidebar')break;
    }
    return {x,y,hit:hit?.tagName,hitClass:hit?.className,
      correct:hit===el||el.contains(hit),ancestors};
  });
}
test('opened desktop Vitrea sidebar project is pointer-hit-testable and clickable',
  {skip:!available,timeout:40000},async()=>{
    const {chromium}=require(playwrightPackage);
    const {preview}=await import('vite');
    const server=await preview({root,preview:{host:'127.0.0.1',port:await freePort(),strictPort:true},logLevel:'error'});
    let browser;
    try {
      browser=await chromium.launch({headless:true,executablePath:binary});
      const page=await browser.newPage({viewport:{width:1440,height:900},locale:'fa-IR'});
      await page.addInitScript(value=>localStorage.setItem('madar-preview',JSON.stringify(value)),state);
      await page.goto(new URL('index.html',server.resolvedUrls.local[0]).href,{waitUntil:'domcontentloaded'});
      await page.locator('.vitrea-primary-nav button').first().click();
      await page.locator('.vitrea-overview').waitFor({state:'visible'});
      await page.getByRole('button',{name:'نمایش منوی کامل مدار'}).click();
      const sidebar=page.locator('#madar-sidebar');
      await sidebar.waitFor({state:'visible'});
      assert.equal(await sidebar.getAttribute('inert'),null);
      const link=sidebar.locator('.projects-nav button[title="پروژه پروژه QA"]');
      await link.scrollIntoViewIfNeeded();
      const hit=await hitTarget(link);
      console.log('Vitrea project hit test',JSON.stringify(hit));
      assert.ok(hit.correct,'Project button is clipped or intercepted: '+JSON.stringify(hit));
      await link.click({timeout:5000});
      await page.waitForFunction(()=>document.querySelector('.projects-nav button[title="پروژه پروژه QA"]')?.classList.contains('active'));
      assert.ok((await link.getAttribute('class')).includes('active'));
      await page.getByRole('button',{name:'نمایش منوی کامل مدار'}).click();
      const board=sidebar.locator('.workspace-board-nav button').filter({hasText:'برد آزمایشی QA'});
      await board.scrollIntoViewIfNeeded();
      const boardHit=await hitTarget(board);
      assert.ok(boardHit.correct,'Board button is clipped or intercepted: '+JSON.stringify(boardHit));
      await board.click({timeout:5000});
      await page.getByRole('heading',{name:'برد آزمایشی QA'}).waitFor({state:'visible',timeout:5000});
      await page.close();
    } finally {
      await browser?.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });
