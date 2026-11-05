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
test('full App compact card keeps drafts, Jalali date, cover readability and archive search',
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
      const cardBox=await drawer.boundingBox();
      assert.ok(cardBox&&Math.abs(cardBox.x+cardBox.width/2-640)<3,
        'on desktop the card should be centered like a Trello detail dialog');
      assert.match(await drawer.locator('.task-editor-location').innerText(),/پروژه تست/);
      assert.equal(await drawer.locator('.task-quick-actions > button:visible').count(),6,
        'five common actions and one More control are visible at first');
      assert.equal(await drawer.locator('#task-section-description').count(),1);
      assert.equal(await drawer.locator('#task-section-checklist').count(),1);
      assert.equal(await drawer.locator('#task-section-attachments').count(),1);
      assert.equal(await drawer.locator('.task-activity-panel#task-section-reports').count(),1);
      assert.equal(await drawer.locator('#task-section-cover').count(),0,
        'cover editor belongs to the board right-click menu, never inside the drawer');
      assert.equal(await drawer.locator('#task-section-dependencies').count(),0);
      await drawer.getByRole('button',{name:'بیشتر'}).click();
      assert.equal(await drawer.locator('.task-more-menu').count(),1);
      assert.equal(await drawer.locator('.task-more-menu').getByText('ثبت گزارش').count(),0,
        'report composer stays in the activity column');
      assert.equal(await drawer.locator('.task-more-menu').getByText('کاور').count(),0);
      await drawer.getByRole('button',{name:'چک‌لیست',exact:true}).click();
      const newStep=drawer.getByRole('textbox',{name:'مرحله جدید چک‌لیست'});
      await newStep.waitFor();
      await newStep.fill('مرحله سریع آزمایشی');
      await newStep.press('Enter');
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].checklist.length===1);
      assert.equal(await drawer.locator('#task-section-checklist .step-list').getByText('مرحله سریع آزمایشی').count(),1);
      await drawer.getByRole('button',{name:'چک‌لیست',exact:true}).click();
      const description=drawer.locator('#task-section-description .rich-description textarea');
      await description.fill('توضیح آزمایشی سریع');
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview')).tasks[0].description==='توضیح آزمایشی سریع');
      assert.equal(await drawer.getByRole('textbox',{name:'عنوان کار'}).getAttribute('maxlength'),'300');
      await drawer.getByRole('button',{name:'چک‌لیست',exact:true}).click();
      await newStep.fill('مرحله نیمه‌کاره');
      page.once('dialog',dialog=>dialog.dismiss());
      await drawer.locator('.drawer-top button[aria-label="بستن"]').click();
      assert.equal(await drawer.isVisible(),true,'draft must survive dismissal of close confirmation');
      await drawer.getByRole('button',{name:'چک‌لیست',exact:true}).click();
      assert.equal(await newStep.inputValue(),'مرحله نیمه‌کاره');
      page.once('dialog',dialog=>dialog.accept());
      await drawer.locator('.drawer-top button[aria-label="بستن"]').click();
      await page.locator('.task-card .task-title').nth(1).click();
      drawer=page.getByRole('dialog',{name:'جزئیات کار'});
      await drawer.waitFor();
      await drawer.getByRole('button',{name:'تاریخ',exact:true}).click();
      await drawer.getByRole('textbox',{name:'موعد انجام'}).click();
      const calendar=page.getByRole('group',{name:'تقویم انتخاب تاریخ'});
      await calendar.waitFor();
      assert.equal(await calendar.locator('.madar-mini-calendar__days button').count(),42);
      await calendar.getByRole('button',{name:'انتخاب 2026-11-05'}).click();
      await calendar.waitFor({state:'hidden'});
      await page.waitForFunction(()=>JSON.parse(localStorage.getItem('madar-preview'))
        .tasks.some(task=>task.id==='card-1'&&task.dueDate==='2026-11-05'));
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
      await drawer.getByRole('button',{name:'بیشتر'}).click();
      await drawer.getByRole('button',{name:'بایگانی یا حذف'}).click();
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
