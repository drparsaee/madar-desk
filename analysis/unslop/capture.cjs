'use strict';
const path=require('node:path'),fs=require('node:fs'),net=require('node:net');
const {chromium}=require('C:/Users/Parsa/AppData/Roaming/npm/node_modules/playwright');
const {preview}=require('vite');
const root=path.resolve(__dirname,'../..');
const target=path.resolve(__dirname,process.argv[2]||'current');
function task(i,projectId,stage){const day=String(1+i%27).padStart(2,'0');
  const month=String(4+i%7).padStart(2,'0');
  return {id:'synthetic-'+i,projectId,boardId:'board-'+projectId,
    title:'پیگیری سفارش نمونه '+i,description:'بررسی فایل و زمان‌بندی تولید',
    status:stage,listId:stage,createdAt:'2026-'+month+'-'+day+'T11:00:00.000Z',
    updatedAt:'2026-10-'+day+'T12:00:00.000Z',dueDate:'',
    labels:[],checklist:[],reports:[],priority:'medium'};}
const stages=[{id:'planned',label:'برای انجام',color:'#729ee9'},
 {id:'active',label:'در حال انجام',color:'#e9aa56'},
 {id:'review',label:'بازبینی',color:'#b38bd5'},
 {id:'done',label:'تکمیل‌شده',color:'#5fbd95'}];
const projects=Array.from({length:6},(_,i)=>({id:'project-'+i,
 name:['برنامه‌ریزی تولید','سفارش‌های چاپ دیجیتال','کنترل کیفیت','طراحی بسته‌بندی','ارتباط با مشتریان','تحویل پروژه'][i],color:'#729ee9',costEnabled:false,price:0}));
const tasks=Array.from({length:32},(_,i)=>task(i+1,projects[i%6].id,stages[i%4].id));
const state={version:1,projects,workspaces:[{id:'workspace-qa',name:'فضای آزمون',archived:false}],
 boards:projects.map(p=>({id:'board-'+p.id,workspaceId:'workspace-qa',projectId:p.id,name:p.name,stages,archived:false})),
 tasks,stages,settings:{theme:'dark',costDefault:false}};
async function port(){return await new Promise((ok,bad)=>{const s=net.createServer();
 s.once('error',bad);s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>ok(p));});});}
(async()=>{fs.mkdirSync(target,{recursive:true});
 const server=await preview({preview:{host:'127.0.0.1',port:await port(),strictPort:true},root,logLevel:'error'});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 try{
  for(const [label,width,height,theme] of [['dark',1440,900,'dark'],['light',1440,900,'light'],['mobile',390,844,'dark']]){
   const context=await browser.newContext({viewport:{width,height},locale:'fa-IR',colorScheme:theme});
   const page=await context.newPage();
   const errors=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(([data,selection])=>{
     localStorage.setItem('madar-preview',JSON.stringify({...data,settings:{...data.settings,theme:selection}}));
     localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
   },[state,theme]);
   const url=new URL('index.html',server.resolvedUrls.local[0]).href;
   await page.goto(url,{waitUntil:'domcontentloaded',timeout:20000});
   await page.getByRole('button',{name:'نمای کلی',exact:true}).click();
   await page.locator('.vitrea-overview-project').first().waitFor({state:'visible',timeout:7000});
   const metrics=await page.evaluate(()=>{
     const root=document.querySelector('.vitrea-overview');
     const font=(sel)=>{const el=document.querySelector(sel);return el?getComputedStyle(el).fontSize:null;};
     return {bodyScrollWidth:document.body.scrollWidth,viewport:innerWidth,
       heading:font('.vitrea-overview-panel__heading small'),
       taskLabel:font('.vitrea-overview-task__content small'),
       monthLabel:font('.vitrea-overview-month-chart__month small'),
       kpiLabel:font('.vitrea-overview-kpi small'),
       cards:root?.querySelectorAll('.vitrea-overview-project').length,
       taskButtons:root?.querySelectorAll('.vitrea-overview-task').length,
       projectBackground:getComputedStyle(root.querySelector('.vitrea-overview-project')).backgroundColor,
       dir:root?.getAttribute('dir'),
       panelBounds:[...root.querySelectorAll('.vitrea-overview-panel')].map(el=>{const b=el.getBoundingClientRect();return [Math.round(b.x),Math.round(b.width)];})};
   });
   console.log(label,JSON.stringify({metrics,errors}));
   await page.screenshot({path:path.join(target,label+'.png'),fullPage:true,animations:'disabled'});
   await context.close();
  }
 }finally{await browser.close();await new Promise(ok=>server.httpServer.close(ok));}
})().catch(err=>{console.error(err);process.exitCode=1;});
