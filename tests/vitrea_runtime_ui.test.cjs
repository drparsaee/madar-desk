'use strict';
// Browser smoke for the real Vite entrypoints. Nothing touches the desktop host:
// both entrypoints receive isolated, synthetic, in-memory data.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');

const chromiumBinary = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightPackage = 'C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable = fs.existsSync(chromiumBinary) && fs.existsSync(playwrightPackage);

const stages = [
  {id:'planned',label:'برای انجام',color:'#729ee9',subtitle:'وظایف برنامه‌ریزی‌شده'},
  {id:'active',label:'در حال انجام',color:'#f4c15a',subtitle:'در دست اقدام'},
  {id:'review',label:'بازبینی',color:'#b38bd5',subtitle:'آماده بررسی'},
  {id:'done',label:'تکمیل‌شده',color:'#5fbd95',subtitle:'پایان یافته'},
];
const qaTask = (id,title,listId) => ({
  id,title,listId,status:listId,projectId:'project-qa',boardId:'board-qa',
  description:'',priority:'medium',dueDate:'',labels:[],checklist:[],reports:[],
  createdAt:'2026-10-20T12:00:00.000Z',updatedAt:'2026-10-20T12:00:00.000Z',
});
const previewState = {
  version:1,
  projects:[{id:'project-qa',name:'پروژه QA',color:'#729ee9',costEnabled:false,price:0}],
  workspaces:[{id:'workspace-qa',name:'فضای آزمون',archived:false}],
  boards:[{id:'board-qa',workspaceId:'workspace-qa',projectId:'project-qa',
    name:'برد آزمایشی QA',color:'#729ee9',archived:false,stages}],
  tasks:[qaTask('task-1','کارت آزمایشی شماره یک','planned'),
    qaTask('task-2','کارت آزمایشی شماره دو','active')],
  stages,settings:{theme:'dark',costDefault:false},
};

const accountingEmpty = {revision:0,capabilities:{canManage:false,canDraft:false,canAdmin:false},
  view:{currency:'RIAL',companyProfile:{legalName:'شرکت آزمایشی QA'},
    accounts:{},parties:{},items:{},invoices:{},bills:{},receipts:{},payments:{},
    journals:[],cheques:{},proformas:{},returns:{},closedThrough:null}};

const screenshots = process.env.MADAR_QA_SCREENSHOT_DIR || '';
function screenshotPath(name) {
  if(!screenshots)return null;
  fs.mkdirSync(screenshots,{recursive:true});
  return path.join(screenshots, name+'.png');
}
async function screenshot(page,name){
  const destination=screenshotPath(name);
  if(destination)await page.screenshot({path:destination,fullPage:false,animations:'disabled'});
}
function captureErrors(page){
  const errors=[];
  page.on('pageerror',error=>errors.push('pageerror: '+error.message));
  page.on('response',response=>{
    if(response.status()>=400)errors.push(`HTTP ${response.status()}: ${response.url()}`);
  });
  page.on('console',msg=>{
    if(msg.type()==='error'&&!/^Failed to load resource: the server responded with a status of \d+/.test(msg.text()))
      errors.push('console: '+msg.text()+' @ '+msg.location().url);
  });
  return errors;
}
async function geometry(page,selector){
  return page.evaluate(sel=>{
    const el=document.querySelector(sel);
    const rect=el?.getBoundingClientRect();
    const styles=el&&getComputedStyle(el);
    return {width:rect&&Math.round(rect.width),height:rect&&Math.round(rect.height),
      x:rect&&Math.round(rect.x),y:rect&&Math.round(rect.y),
      background:styles?.backgroundColor,color:styles?.color,
      dir:styles?.direction,viewport:innerWidth,bodyWidth:document.documentElement.scrollWidth};
  },selector);
}
async function unusedLocalPort(){
  return new Promise((resolve,reject)=>{
    const listener=net.createServer();
    listener.once('error',reject);
    listener.listen(0,'127.0.0.1',()=>{
      const port=listener.address().port;
      listener.close(error=>error?reject(error):resolve(port));
    });
  });
}

test('Vitrea UI runtime smoke: RTL, dark, navigation and isolated accounting',
  {skip:!runnable,timeout:55000},async()=>{
    const {chromium} = require(playwrightPackage);
    const {preview}=await import('vite');
    // Preview serves the separately built dist/ with no source watcher: locked
    // private SQL files in the repository must never be touched by this QA.
    const server=await preview({preview:{host:'127.0.0.1',port:await unusedLocalPort(),strictPort:true},
      root:path.resolve(__dirname,'..'),logLevel:'error'});
    let browser;
    try {
      const base=server.resolvedUrls.local[0];
      browser=await chromium.launch({headless:true,executablePath:chromiumBinary});
      const desktop=await browser.newContext({viewport:{width:1440,height:900},
        locale:'fa-IR',colorScheme:'dark'});
      const page=await desktop.newPage();
      page.setDefaultTimeout(6000);
      const mainErrors=captureErrors(page);
      await page.addInitScript(data=>{
        localStorage.setItem('madar-preview',JSON.stringify(data));
        localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
      },previewState);
      await page.goto(new URL('index.html',base).href,{waitUntil:'domcontentloaded',timeout:18000});
      await page.locator('.vitrea-primary-nav button').first().click();
      await page.locator('.vitrea-overview').waitFor({state:'visible'});
      const overviewPolish=await page.evaluate(()=>{
        const font=selector=>parseFloat(getComputedStyle(document.querySelector(selector)).fontSize);
        const project=document.querySelector('.vitrea-overview-project');
        const root=document.querySelector('.vitrea-overview');
        return {dir:root.getAttribute('dir'),kpis:root.querySelectorAll('.vitrea-overview-kpi').length,
          projectTiles:root.querySelectorAll('.vitrea-overview-project').length,
          labelPx:font('.vitrea-overview-panel__heading small'),
          taskPx:font('.vitrea-overview-task__content small'),
          monthPx:font('.vitrea-overview-month-chart__month small'),
          projectBackgroundImage:getComputedStyle(project).backgroundImage,
          bodyScrollWidth:document.body.scrollWidth,viewport:innerWidth};
      });
      assert.equal(overviewPolish.dir,'rtl');
      assert.equal(overviewPolish.kpis,3);
      assert.equal(overviewPolish.projectTiles,1);
      assert.ok(overviewPolish.labelPx>=12&&overviewPolish.taskPx>=12&&
        overviewPolish.monthPx>=11,JSON.stringify(overviewPolish));
      assert.equal(overviewPolish.projectBackgroundImage,'none',
        'project cards should use calm surfaces rather than decorative gradients');
      assert.ok(overviewPolish.bodyScrollWidth<=overviewPolish.viewport+1,
        'overview must not cause horizontal page overflow');
      await screenshot(page,'madar-unslop-overview-dark');
      await page.evaluate(()=>{document.documentElement.dataset.theme='light';});
      await screenshot(page,'madar-unslop-overview-light');
      await page.evaluate(()=>{document.documentElement.dataset.theme='dark';});
      // Task manager uses ordinary native field labels; no fixed caption
      // portal may obscure search or the editable fields in its settings.
      assert.equal(await page.locator('.madar-fl-caption').count(),0);
      const searchInput=page.getByRole('searchbox',{name:'جست‌وجوی پیشرفته کارها'});
      await searchInput.click();
      assert.equal(await page.locator('.madar-fl-caption').count(),0);
      const menuButton=page.getByRole('button',{name:'نمایش منوی کامل مدار'});
      await menuButton.hover();
      assert.equal(await menuButton.getAttribute('title'),'منو');
      await screenshot(page,'madar-overview-dark-initial');
      const headerLayout=await page.evaluate(()=>{
        const box=selector=>{
          const node=document.querySelector(selector);
          if(!node)return null;
          const r=node.getBoundingClientRect();
          return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};
        };
        return {
          main:box('.vitrea-header-main'),
          brand:box('.vitrea-brand-capsule'),
          search:box('.vitrea-header-main .searchplus-shell'),
          account:box('.vitrea-header-main .vitrea-account-capsule'),
          time:box('.vitrea-header-clock .clock-widget__time-card'),
          date:box('.vitrea-header-clock .clock-widget__date'),
          dock:box('.vitrea-quickdock'),
          sync:box('.vitrea-quickdock > .sync-indicator--dock'),
          refresh:box('.vitrea-quickdock > .vitrea-quickdock__refresh'),
        };
      });
      assert.ok(headerLayout.main.x>=headerLayout.time.right+10,
        'Clock must remain outside and left of the unified right header');
      assert.ok(Math.abs(headerLayout.date.x-headerLayout.time.x)<=1 &&
        Math.abs(headerLayout.date.width-headerLayout.time.width)<=1 &&
        headerLayout.date.y>=headerLayout.time.bottom-1,
        'Date must align directly below time inside the unified clock capsule');
      assert.ok(headerLayout.search.y>headerLayout.brand.y &&
        headerLayout.account.y>=headerLayout.brand.y-2 &&
        headerLayout.account.bottom<=headerLayout.search.y+2 &&
        headerLayout.account.right<headerLayout.brand.x,
        'Search belongs below the top row; profile sits opposite the brand, not beside search');
      assert.ok(headerLayout.sync.y>=headerLayout.dock.y &&
        headerLayout.refresh.y>=headerLayout.sync.bottom,
        'Connection comes first and refresh immediately follows within the left rail');
      assert.ok(headerLayout.dock.y>headerLayout.date.bottom,
        'Desktop dock must not overlap the date capsule');
      assert.equal(await page.locator('.vitrea-header-clock .clock-widget__date').evaluate(
        el=>getComputedStyle(el).borderTopWidth),'0px',
        'The date must share a seamless background with the clock');
      assert.equal(await page.locator('.vitrea-quickdock button[aria-label="تعریف کاربران"]').count(),1,
        'Solo admin should have the user-management entry but must reach LAN setup, not a fake account form');
      await page.locator('.vitrea-quickdock .sync-indicator--dock').click();
      await page.getByRole('dialog',{name:'شبکه محلی و کاربران'}).waitFor({state:'visible'});
      assert.match(await page.locator('.lan-modal').innerText(),
        /تعریف کاربران و تعیین دسترسی پس از راه‌اندازی میزبان/);
      await page.locator('.lan-modal .dialog-head .icon-btn').click();
      await page.locator('.lan-modal').waitFor({state:'hidden'});
      const navigationProblems=[];
      const clickWithDiagnostic=async locator=>{
        try{await locator.click({timeout:4000});}
        catch(error){
          const detail=await locator.evaluate(el=>{
            const bounds=el.getBoundingClientRect();
            const x=bounds.left+bounds.width/2,y=bounds.top+bounds.height/2;
            const intercept=document.elementFromPoint(x,y);
            const parent=el.parentElement;
            const sidebar=el.closest('#madar-sidebar');
            const ancestorClips=[];
            for(let node=el.parentElement;node;node=node.parentElement){
              const box=node.getBoundingClientRect(),css=getComputedStyle(node);
              ancestorClips.push({node:node.className||node.tagName,
                top:Math.round(box.top),bottom:Math.round(box.bottom),
                overflowY:css.overflowY,visibility:css.visibility,
                scrollTop:node.scrollTop});
              if(node===sidebar)break;
            }
            return {target:el.getAttribute('title')||el.textContent,
              bounds:{x:bounds.x,y:bounds.y,width:bounds.width,height:bounds.height},
              intercept:intercept?.outerHTML?.slice(0,250),
              pointerEvents:getComputedStyle(el).pointerEvents,
              parentPointerEvents:parent&&getComputedStyle(parent).pointerEvents,
              sidebarPointerEvents:sidebar&&getComputedStyle(sidebar).pointerEvents,
              sidebarScroll:{top:sidebar?.scrollTop,scrollHeight:sidebar?.scrollHeight,
                clientHeight:sidebar?.clientHeight},
              ancestorClips,
            };
          });
          navigationProblems.push(detail);
          console.log('Native pointer click blocked',JSON.stringify(detail));
          await screenshot(page,'madar-sidebar-click-blocked');
          throw error;
        }
      };
      await page.getByRole('button',{name:'نمایش منوی کامل مدار'}).click();
      assert.equal(await page.locator('#madar-sidebar').getAttribute('role'),'dialog');
      await screenshot(page,'madar-sidebar-open-dark');
      await clickWithDiagnostic(page.locator('.projects-nav button[title="پروژه پروژه QA"]'));
      await page.getByRole('button',{name:'نمایش منوی کامل مدار'}).click();
      await clickWithDiagnostic(page.locator('.workspace-board-nav button').filter({hasText:'برد آزمایشی QA'}));
      await page.getByRole('heading',{name:'برد آزمایشی QA'}).waitFor();
      assert.equal(await page.locator('.task-card').count(),2);
      await page.getByRole('button',{name:'نمایش منوی کامل مدار'}).click();
      assert.equal(await page.locator('#madar-sidebar').getAttribute('role'),'dialog');
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#madar-sidebar').getAttribute('role'),null);
      assert.equal(await page.evaluate(()=>document.activeElement?.getAttribute('aria-label')),
        'نمایش منوی کامل مدار');
      const main=await geometry(page,'.app-shell');
      const aside=await geometry(page,'.sidebar');
      assert.equal(await page.locator('html').getAttribute('dir'),'rtl');
      assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
      assert.equal(aside.dir,'rtl');
      assert.ok(aside.width>=180,JSON.stringify(aside));
      assert.ok(main.bodyWidth<=1441,JSON.stringify(main));
      await screenshot(page,'madar-overview-dark-desktop');
      const darkInk=main.color;
      await page.evaluate(()=>{document.documentElement.dataset.theme='light';});
      const lightInk=(await geometry(page,'.app-shell')).color;
      assert.notEqual(lightInk,darkInk,'light and dark shell must use different text tokens');
      await screenshot(page,'madar-overview-light-desktop');
      await page.evaluate(()=>{document.documentElement.dataset.theme='dark';});
      await page.locator('.board-tabs').getByRole('button',{name:'فهرست'}).click();
      assert.ok(await page.locator('.list-mode').isVisible());
      await page.locator('.board-tabs').getByRole('button',{name:'برد کارها'}).click();
      assert.ok(await page.locator('.kanban').isVisible());
      await page.getByRole('navigation',{name:'بخش‌های اصلی مدار'}).getByRole('button',{name:'حسابداری'}).click();
      await page.waitForURL(/accounting\.html/);
      assert.ok(!mainErrors.length,JSON.stringify(mainErrors));

      const mobile=await browser.newContext({viewport:{width:390,height:844},
        isMobile:true,hasTouch:true,locale:'fa-IR',colorScheme:'dark'});
      const small=await mobile.newPage();
      small.setDefaultTimeout(6000);
      const mobileErrors=captureErrors(small);
      await small.addInitScript(data=>localStorage.setItem('madar-preview',JSON.stringify(data)),previewState);
      await small.goto(new URL('index.html',base).href,{waitUntil:'domcontentloaded',timeout:18000});
      await small.getByRole('button',{name:'نمای کلی',exact:true}).click();
      await small.locator('.vitrea-overview').waitFor({state:'visible'});
      const mobileOverview=await small.evaluate(()=>{
        const root=document.querySelector('.vitrea-overview');
        return {viewport:innerWidth,bodyScrollWidth:document.body.scrollWidth,
          kpis:root?.querySelectorAll('.vitrea-overview-kpi').length,
          monthPx:parseFloat(getComputedStyle(root.querySelector('.vitrea-overview-month-chart__month small')).fontSize)};
      });
      assert.equal(mobileOverview.kpis,3);
      assert.ok(mobileOverview.monthPx>=11,JSON.stringify(mobileOverview));
      assert.ok(mobileOverview.bodyScrollWidth<=mobileOverview.viewport+1,
        'mobile overview must not cause horizontal overflow');
      await screenshot(small,'madar-unslop-overview-mobile');
      const mobileDock=await small.getByRole('button',{name:'نمایش منوی کامل مدار'})
        .evaluate(button=>{
          const r=button.getBoundingClientRect(),hit=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
          return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:innerWidth,height:innerHeight,
            clickable:button===hit||button.contains(hit)};
        });
      assert.ok(mobileDock.x>=0 && mobileDock.y>=0 &&
        mobileDock.right<=mobileDock.width && mobileDock.bottom<=mobileDock.height &&
        mobileDock.clickable,'Mobile quickdock menu must be visible and hit-testable');
      await small.getByRole('button',{name:'نمایش منوی کامل مدار'}).click();
      assert.equal(await small.locator('#madar-sidebar').getAttribute('role'),'dialog');
      // Mobile drawer animates its visibility/transform; under parallel Node
      // test load, React state can settle before the CSS visibility transition.
      await small.locator('#madar-sidebar').waitFor({state:'visible',timeout:6000});
      await screenshot(small,'madar-sidebar-mobile-open');
      if(!await small.locator('#madar-sidebar').isVisible()){
        console.log('Mobile sidebar diagnostic',JSON.stringify({
          sidebar:await geometry(small,'#madar-sidebar'),
          css:await small.locator('#madar-sidebar').evaluate(el=>{
            const css=getComputedStyle(el);
            return {display:css.display,visibility:css.visibility,opacity:css.opacity,
              transform:css.transform,pointerEvents:css.pointerEvents,className:el.className};
          }),errors:mobileErrors,
        }));
      }
      assert.ok(await small.locator('#madar-sidebar').isVisible());
      await screenshot(small,'madar-overview-dark-mobile');
      await small.keyboard.press('Escape');
      assert.equal(await small.locator('#madar-sidebar').getAttribute('role'),null);
      await screenshot(small,'madar-overview-mobile-menu-closed');
      assert.ok(!mobileErrors.length,JSON.stringify(mobileErrors));

      const accounting=await browser.newContext({viewport:{width:1440,height:900},
        locale:'fa-IR',colorScheme:'dark'});
      const finance=await accounting.newPage();
      finance.setDefaultTimeout(6000);
      const financeErrors=captureErrors(finance);
      await finance.addInitScript(payload=>{
        window.__qaAccountingCommandCalls=0;
        window.madar={
          standaloneAccountingRead:async()=>structuredClone(payload),
          standaloneAccountingCommand:async()=>{
            window.__qaAccountingCommandCalls++;
            throw Error('read-only QA fixture');
          },
        };
        document.addEventListener('DOMContentLoaded',()=>{
          document.documentElement.dataset.theme='dark';
        },{once:true});
      },accountingEmpty);
      await finance.goto(new URL('accounting.html',base).href,{waitUntil:'domcontentloaded',timeout:18000});
      // Switch from the default task-centric novice shell to the retained expert Ribbon.
      await finance.locator('.sac-nav-mode button:nth-child(2)').click();
      await finance.locator('.sac-ribbon-tabs').waitFor({state:'visible'});
      try{await finance.locator('.sac-vtr-home').waitFor({state:'visible'});}
      catch(error){
        await screenshot(finance,'madar-accounting-diagnostic');
        console.log('Accounting QA diagnostic',JSON.stringify({
          errors:financeErrors,
          body:(await finance.locator('body').innerText()).slice(0,1400),
          rootClass:await finance.locator('.sac-root').getAttribute('class'),
        }));
        throw error;
      }
      const accounts=await geometry(finance,'.sac-root');
      const financeRibbon=await geometry(finance,'.sac-ribbon-shell');
      assert.equal(await finance.locator('.sac-root').getAttribute('dir'),'rtl');
      assert.ok(financeRibbon.width>500,JSON.stringify(financeRibbon));
      assert.ok(accounts.bodyWidth<=1441,JSON.stringify(accounts));
      assert.ok(await finance.getByText('ریال',{exact:true}).count()>0);
      assert.ok(!await finance.getByRole('alert',{name:/پاسخ میزبان/}).count());
      await screenshot(finance,'madar-payouts-dark-desktop');
      await finance.getByRole('navigation',{name:'دسته‌بندی‌های حسابداری'})
        .getByRole('button',{name:'فاکتورها و سفارش‌ها'}).click();
      await finance.getByRole('navigation',{name:'فرمان‌های گروه انتخاب‌شده'})
        .getByRole('button',{name:'فاکتورهای فروش'}).click();
      await finance.locator('.sac-workflow-nav').waitFor({state:'visible'});
      assert.ok(await finance.locator('.sac-workflow-nav').getByText('فاکتورهای فروش').isVisible());
      await finance.getByRole('navigation',{name:'دسته‌بندی‌های حسابداری'})
        .getByRole('button',{name:'عمومی'}).click();
      await finance.getByRole('navigation',{name:'فرمان‌های گروه انتخاب‌شده'})
        .getByRole('button',{name:'داشبورد'}).click();
      assert.ok(await finance.locator('.sac-vtr-home').isVisible());
      assert.equal(await finance.evaluate(()=>window.__qaAccountingCommandCalls),0,
        'smoke test must never request ledger mutations');
      assert.ok(!financeErrors.length,JSON.stringify(financeErrors));
      console.log('Vitrea UI geometry (synthetic QA fixture)',JSON.stringify({main,aside,accounts,financeRibbon,navigationProblems}));
      assert.deepEqual(navigationProblems,[],'Sidebar links must be directly clickable with pointer input');
      await desktop.close();await mobile.close();await accounting.close();
    } finally {
      if(browser)await browser.close();
      await new Promise(resolve=>server.httpServer.close(resolve));
    }
  });
