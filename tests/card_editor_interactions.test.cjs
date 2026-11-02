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
const stamp='2026-10-20T10:00:00.000Z';
const stages=[{id:'todo',label:'انجام‌دادنی',color:'#5e82b1'}];
const tasks=['کارت اول آزمایشی','کارت دوم آزمایشی'].map((title,index)=>({
  id:'card-'+index,projectId:'p',boardId:'b',listId:'todo',status:'todo',title,description:'',
  checklist:[],reports:[],assignees:[],labels:[],priority:'medium',
  createdAt:stamp,updatedAt:stamp,cardOrder:index,cover:index===1?{type:'color',size:'full',color:'#AA1177'}:null,
}));
const fixture={version:1,projects:[{id:'p',name:'پروژه تست',color:'#6889bb'}],
  boards:[{id:'b',projectId:'p',workspaceId:'w',name:'برد تست',archived:false,stages}],
  workspaces:[{id:'w',name:'فضای تست',archived:false}],stages,tasks,
  settings:{theme:'light',costDefault:false}};
async function safePort(){
  for(let i=0;i<30;i++){
    const candidate=22000+Math.floor(Math.random()*16000);
    try{
      await new Promise((resolve,reject)=>{
        const server=net.createServer();server.once('error',reject);
        server.listen(candidate,'127.0.0.1',()=>server.close(error=>error?reject(error):resolve()));
      });return candidate;
    }catch(error){if(error.code!=='EADDRINUSE')throw error;}
  }
  throw new Error('No browser safe port');
}
test('full App reuses disclosure preference, offers Jalali popup, keeps full-cover text readable and archives',
  {skip:!available,timeout:90000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',server:{host:'127.0.0.1',
      port:await safePort(),strictPort:true,hmr:false,watch:{ignored:['**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      const context=await browser.newContext({viewport:{width:1280,height:850},locale:'fa-IR'});
      await context.addInitScript(state=>{
        localStorage.setItem('madar-preview',JSON.stringify(state));
        localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },fixture);
      const page=await context.newPage();page.setDefaultTimeout(12000);
      const errors=[];page.on('pageerror',error=>errors.push(error.message));
      await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
      await page.locator('.task-card .task-title').first().click();
      let drawer=page.getByRole('dialog',{name:'جزئیات کار'});
      await drawer.waitFor();
      const orderedIds=['metadata','description','assignees','attachments','checklist','tags',
        'cover','time','dependencies','reports','accounting','settings'];
      const actualSections=await drawer.locator('.task-shared-disclosure[id^="task-section-"]')
        .evaluateAll(items=>items.map(item=>item.id.replace('task-section-','')));
      assert.deepEqual(actualSections,orderedIds,'actual DOM must match requested section order');
      const navSections=await drawer.locator('.task-quick-actions button[aria-controls]')
        .evaluateAll(items=>items.map(item=>item.getAttribute('aria-controls').replace('task-section-','')));
      assert.deepEqual(navSections,orderedIds.slice(0,10),'toolbar exactly matches ten requested sections');
      assert.notEqual(await drawer.locator('#task-section-metadata').getAttribute('open'),null,
        'metadata opens by default so deadline remains accessible');
      const assignees=drawer.locator('#task-section-assignees');
      assert.equal(await assignees.getAttribute('open'),null);
      await assignees.locator('summary').click();
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-card-sections-v1:local')||'{}').assignees===true);
      await drawer.locator('#task-section-cover > summary').click();
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-card-sections-v1:local')||'{}').cover===true);
      await drawer.locator('.drawer-top button[aria-label="بستن"]').click();
      await page.locator('.task-card .task-title').nth(1).click();
      drawer=page.getByRole('dialog',{name:'جزئیات کار'});
      await drawer.waitFor();
      assert.notEqual(await drawer.locator('#task-section-assignees').getAttribute('open'),null,
        'second card inherits the first card disclosure preference');
      assert.notEqual(await drawer.locator('#task-section-cover').getAttribute('open'),null,
        'cover disclosure also persists per user across cards');
      // Clicking the compact deadline box itself opens the small picker.
      await drawer.getByRole('textbox',{name:'موعد انجام'}).click();
      const calendar=page.getByRole('group',{name:'تقویم انتخاب تاریخ'});
      await calendar.waitFor();
      assert.equal(await calendar.locator('.madar-mini-calendar__days button').count(),42);
      await calendar.getByRole('button',{name:'انتخاب 2026-11-05'}).click();
      await calendar.waitFor({state:'hidden'});
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[1].dueDate==='2026-11-05');
      await drawer.locator('.drawer-top button[aria-label="بستن"]').click();
      const coverCard=page.locator('.task-card').filter({hasText:'کارت دوم آزمایشی'});
      const bounds=await coverCard.evaluate(card=>{
        const title=card.querySelector('.task-title').getBoundingClientRect();
        const background=getComputedStyle(card).backgroundColor;
        return {background,textVisible:title.height>0,hasStripe:!!card.querySelector('.task-card-cover')};
      });
      assert.equal(bounds.background,'rgb(170, 17, 119)');
      assert.equal(bounds.textVisible,true);
      assert.equal(bounds.hasStripe,false);
      await coverCard.locator('.task-title').click();
      drawer=page.getByRole('dialog',{name:'جزئیات کار'});
      await drawer.getByRole('button',{name:'آرشیو',exact:true}).click();
      await drawer.getByText('کارت بایگانی شود؟',{exact:false}).waitFor();
      await drawer.getByRole('button',{name:'تأیید آرشیو'}).click();
      await drawer.waitFor({state:'hidden'});
      await page.getByRole('searchbox',{name:'جست‌وجوی پیشرفته کارها'}).fill('کارت دوم');
      const result=page.getByRole('region',{name:'نتایج جست‌وجوی همه کارت‌ها'});
      await result.getByText('بایگانی',{exact:true}).first().waitFor();
      assert.equal(await result.getByRole('button',{name:'بازیابی کارت'}).count(),1);
      assert.deepEqual(errors,[]);
    } finally {if(browser)await browser.close();await server.close();}
  });
