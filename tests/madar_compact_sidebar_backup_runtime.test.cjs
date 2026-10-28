'use strict';

const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');

const root=path.resolve(__dirname,'..');
const chrome='C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const playwrightHome='C:\\Users\\Parsa\\AppData\\Roaming\\npm\\node_modules\\playwright';
const runnable=fs.existsSync(chrome)&&fs.existsSync(playwrightHome);
const stages=[{id:'todo',label:'در انتظار',color:'#64748b',subtitle:''}];
const fixture={
  version:1,
  projects:[{id:'project-qa',name:'پروژه کنترل رابط',color:'#6989bd',costEnabled:false,price:0}],
  workspaces:[{id:'workspace-qa',name:'فضای ایزوله',archived:false}],
  boards:[{id:'board-qa',workspaceId:'workspace-qa',projectId:'project-qa',
    name:'برد کنترل رابط',color:'#6989bd',archived:false,stages}],
  stages,tasks:[],settings:{theme:'light',costDefault:false},
};

async function freePort(){
  return new Promise((resolve,reject)=>{
    const socket=net.createServer();
    socket.once('error',reject);
    socket.listen(0,'127.0.0.1',()=>{
      const port=socket.address().port;
      socket.close(error=>error?reject(error):resolve(port));
    });
  });
}

// The full App renders through Vite; only its preview/mock bridge is replaced
// in memory. All writes and the LAN host are synthetic, never native storage.
function isolatedHostPlugin(){
  const target='const api=window.madar||mockBridge;';
  const syntheticApi=`
    mockBridge.lanStatus=async()=>window.__qaMode==='server'
      ?{mode:'server',transport:'https',port:48370,user:{username:'admin',role:'admin',projects:null}}
      :{mode:'solo',user:{username:'local',role:'admin',projects:null}};
    mockBridge.lanUsers=async()=>{window.__qaCalls.push('lanUsers');return [...window.__qaUsers];};
    mockBridge.lanDisplayRoles=async()=>[
      {id:'employee',label:'کارمند',displayMode:'basic',isBuiltin:true},
      {id:'general_manager',label:'مدیرکل',displayMode:'complete',isBuiltin:true},
    ];
    mockBridge.lanSaveUser=async user=>{window.__qaCalls.push({method:'lanSaveUser',user});
      window.__qaUsers.push({...user,password:undefined});return {ok:true};};
    mockBridge.createLocalBackup=async()=>{window.__qaCalls.push('createLocalBackup');
      const backup={name:'madar-qa-local-01.sqlite',createdAt:'2026-10-28T08:00:00Z'};
      window.__qaBackups=[backup];return backup;};
    mockBridge.listLocalBackups=async()=>[...window.__qaBackups];
    mockBridge.chooseDriveFolder=async()=>{window.__qaCalls.push('chooseDriveFolder');
      window.__qaFolder={configured:true,available:true,folder:'C:/QA/Drive/Madar'};
      return {canceled:false};};
    mockBridge.driveFolderStatus=async()=>({...window.__qaFolder});
    mockBridge.driveFolderList=async()=>[...window.__qaFolderBackups];
    mockBridge.driveFolderBackup=async()=>{window.__qaCalls.push('driveFolderBackup');
      const backup={name:'madar-qa-folder-01.json'};
      window.__qaFolderBackups=[backup];return backup;};
  `;
  return {name:'madar-compact-sidebar-isolated-host',enforce:'pre',transform(code,id){
    if(!/[\\/]src[\\/]App\.jsx(?:\?|$)/.test(id))return;
    assert.ok(code.includes(target),'full App mock bridge injection target moved');
    return code.replace(target,syntheticApi+'\n'+target);
  }};
}

async function openSidebar(page){
  await page.getByRole('button',{name:'نمایش منوی کامل مدار'}).click();
  const sidebar=page.locator('#madar-sidebar');
  await sidebar.waitFor({state:'visible'});
  assert.equal(await sidebar.getAttribute('role'),'dialog');
  return sidebar;
}

async function checkSidebar(page,width){
  const sidebar=await openSidebar(page);
  assert.equal(await sidebar.evaluate(el=>getComputedStyle(el).direction),'rtl');
  const groups=[
    ['ابزارهای برنامه','گزارش‌ها و ابزارها','گزارش و تحلیل'],
    ['بخش حسابداری','حسابداری','ورود به نرم‌افزار حسابداری'],
    ['ابزارهای مدیریتی','مدیریت','کاربران و دسترسی‌ها'],
  ];
  assert.equal(await sidebar.locator('.sidebar-group').count(),3,
    'secondary navigation must have three compact groups');
  for(const [label,title,item] of groups){
    const group=sidebar.locator('details.sidebar-group[aria-label="'+label+'"]');
    await group.waitFor({state:'attached'});
    assert.equal(await group.getAttribute('open'),null,title+' starts collapsed');
    assert.match(await group.locator(':scope > summary').innerText(),new RegExp(title));
    assert.equal(await group.getByRole('button',{name:item}).count(),0,
      'closed group should hide its children from navigation');
    await group.locator(':scope > summary').click();
    assert.notEqual(await group.getAttribute('open'),null,title+' expands on click');
    assert.equal(await group.getByRole('button',{name:item}).isVisible(),true);
    await group.locator(':scope > summary').click();
    assert.equal(await group.getAttribute('open'),null,title+' collapses on second click');
  }
  const rootLinks=await sidebar.locator(':scope > nav.sidebar-nav > button').allInnerTexts();
  assert.equal(rootLinks.length,2,'secondary tools should no longer crowd the top-level navigation');
  assert.match(rootLinks[0],/^همه کارها\s+[0۰٠]$/);
  assert.equal(rootLinks[1].trim(),'کارهای مهم');
  assert.equal(await sidebar.getByText('تنظیمات و مراحل برد').count(),0);
  assert.equal(await sidebar.getByText('مدیریت مالی',{exact:true}).count(),0,
    'accounting belongs in the dedicated accounting group');
  const settings=sidebar.locator('.sidebar-bottom > button.sidebar-settings').filter({hasText:'تنظیمات'});
  assert.equal(await settings.count(),1);
  const alignment=await settings.evaluate(button=>{
    const style=getComputedStyle(button),icon=button.querySelector('svg');
    const buttonBounds=button.getBoundingClientRect(),iconBounds=icon.getBoundingClientRect();
    return {direction:style.direction,textAlign:style.textAlign,buttonRight:buttonBounds.right,
      iconRight:iconBounds.right};
  });
  assert.equal(alignment.direction,'rtl');
  assert.equal(alignment.textAlign,'right');
  assert.ok(alignment.buttonRight-alignment.iconRight<30,
    'settings icon should begin on the right edge of its RTL button: '+JSON.stringify(alignment));
  await settings.click();
  const modal=page.getByRole('dialog',{name:'تنظیمات مدار'});
  await modal.waitFor({state:'visible'});
  assert.equal(await modal.getByText('تنظیمات و مراحل برد').count(),0);
  await modal.getByRole('button',{name:'بستن'}).click();
  assert.equal(await page.locator('#madar-sidebar').getAttribute('role'),null,
    'sidebar should close after entering Settings');
  assert.equal(await page.locator('html').getAttribute('dir'),'rtl');
  assert.ok((await page.locator('.app-shell').evaluate(el=>getComputedStyle(el).direction))==='rtl');
  const geometry=await page.locator('.vitrea-quickdock').boundingBox();
  assert.ok(geometry && geometry.x>=-2 && geometry.x+geometry.width<=width+2);
}

async function checkUserShortcut(page,mode){
  const shortcut=page.locator('.vitrea-quickdock').getByRole('button',{name:'تعریف کاربران'});
  await shortcut.click();
  const modal=page.getByRole('dialog',{name:'شبکه محلی و کاربران'});
  await modal.waitFor({state:'visible'});
  assert.equal(await modal.evaluate(el=>getComputedStyle(el).direction),'rtl');
  if(mode==='solo'){
    await modal.getByText('تعریف کاربران و تعیین دسترسی پس از راه‌اندازی میزبان شبکه فعال می‌شود',{exact:false})
      .waitFor({state:'visible'});
    await modal.getByRole('button',{name:'جست‌وجوی میزبان در شبکه'}).waitFor({state:'visible'});
    const advanced=modal.locator('details.lan-advanced');
    assert.equal(await advanced.getAttribute('open'),null,
      'easy LAN discovery is shown first and manual server settings start collapsed');
    await advanced.locator(':scope > summary').click();
    await modal.getByText('فعال‌کردن سرور محلی').waitFor({state:'visible'});
    await modal.getByText('اتصال به سرور دیگر').waitFor({state:'visible'});
    assert.equal(await modal.getByText('ساخت حساب جدید').count(),0);
    assert.equal(await page.evaluate(()=>window.__qaCalls.includes('lanUsers')),false,
      'solo mode must not fetch network accounts');
  }else{
    await modal.getByText('تعریف کاربر و تعیین سطح دسترسی',{exact:true}).first().waitFor({state:'visible'});
    await modal.getByText('ساخت حساب جدید').waitFor({state:'visible'});
    assert.equal(await page.evaluate(()=>window.__qaCalls.includes('lanUsers')),true,
      'server mode must load actual host users API');
    const form=modal.locator('.lan-density__editor');
    await form.getByRole('textbox',{name:'نام کاربری انگلیسی'}).fill('qauser');
    await form.locator('input[type=password]').fill('synthetic123');
    const create=form.getByRole('button',{name:'ایجاد حساب کاربر'});
    assert.equal(await create.isEnabled(),true);
    await create.click();
    await modal.getByText('حساب، قالب نمایش و مجوز فنی ذخیره شد.').waitFor({state:'visible'});
    const calls=await page.evaluate(()=>window.__qaCalls);
    const created=calls.find(call=>call?.method==='lanSaveUser');
    assert.equal(created.user.username,'qauser');
    assert.equal(created.user.role,'viewer');
  }
  await modal.locator('.dialog-head .icon-btn').click();
  await modal.waitFor({state:'hidden'});
}

async function checkBackup(page,width){
  await page.locator('.vitrea-quickdock').getByRole('button',{name:'Google Drive'}).click();
  const panel=page.getByRole('dialog',{name:'پشتیبان‌گیری'});
  await panel.waitFor({state:'visible'});
  assert.equal(await panel.evaluate(el=>getComputedStyle(el).direction),'rtl');
  const box=await panel.boundingBox();
  assert.ok(box && box.x>=-2 && box.x+box.width<=width+2,
    'backup dialog must fit '+width+'px: '+JSON.stringify(box));
  const quick=panel.getByRole('region',{name:'پشتیبان‌گیری سریع'});
  assert.equal(await quick.getByRole('button',{name:'ایجاد پشتیبان',exact:true}).isEnabled(),true);
  assert.equal(await quick.getByRole('button',{name:'انتخاب پوشه',exact:true}).isEnabled(),true);
  const more=panel.locator('details.backup-easy-more');
  assert.equal(await more.getAttribute('open'),null,'advanced backup settings start folded');
  assert.equal(await panel.getByRole('textbox',{name:'Google OAuth Desktop Client ID'}).count(),0);

  await quick.getByRole('button',{name:'ایجاد پشتیبان',exact:true}).click();
  await panel.getByText('نسخه پشتیبان محلی ایجاد شد: madar-qa-local-01.sqlite',{exact:false})
    .waitFor({state:'visible'});
  await panel.getByText('آخرین نسخه‌های محلی').waitFor({state:'visible'});
  await quick.getByRole('button',{name:'انتخاب پوشه',exact:true}).click();
  await panel.getByRole('status').filter({hasText:'C:/QA/Drive/Madar'}).waitFor({state:'visible'});
  await quick.getByRole('button',{name:'ذخیره در پوشه'}).click();
  await panel.getByText('نسخه اطلاعات داخل پوشه همگام‌شده ثبت شد: madar-qa-folder-01.json')
    .waitFor({state:'visible'});
  const calls=await page.evaluate(()=>window.__qaCalls);
  for(const name of ['createLocalBackup','chooseDriveFolder','driveFolderBackup'])
    assert.equal(calls.filter(call=>call===name).length,1,'one-click operation '+name);
  assert.equal(calls.some(call=>/OAuth|driveConnect|driveUpload/.test(String(call))),false,
    'normal backup never requires Google API authorization');

  await more.locator(':scope > summary').click();
  assert.notEqual(await more.getAttribute('open'),null);
  const google=more.locator('details.drive-advanced');
  assert.equal(await google.getAttribute('open'),null,'Google API is a second optional disclosure');
  await google.locator(':scope > summary').click();
  assert.notEqual(await google.getAttribute('open'),null);
  await google.getByText('Google OAuth Desktop Client ID').waitFor({state:'visible'});
  assert.equal(await google.getByRole('button',{name:'اتصال API Google'}).isDisabled(),true);
  await panel.locator('.dialog-head .icon-btn').click();
  await panel.waitFor({state:'hidden'});
}

test('Full App compact sidebar, LAN user routing and one-click backup at 1440/480 RTL',
  {skip:!runnable,timeout:150000},async()=>{
    const {createServer}=await import('vite');
    const {chromium}=require(playwrightHome);
    const server=await createServer({root,logLevel:'error',plugins:[isolatedHostPlugin()],
      server:{host:'127.0.0.1',port:await freePort(),strictPort:true,hmr:false,
        watch:{ignored:['**/.qa-*','**/.qa-*/**','**/WebView2/**','**/research/**']}}});
    let browser;
    try{
      await server.listen();
      browser=await chromium.launch({headless:true,executablePath:chrome});
      for(const width of [1440,480])for(const mode of ['solo','server']){
        const context=await browser.newContext({viewport:{width,height:900},locale:'fa-IR'});
        await context.addInitScript(({state,mode})=>{
          localStorage.setItem('madar-preview',JSON.stringify(state));
          localStorage.setItem('madar-preferences',JSON.stringify({calendar:'jalali',clockWidget:'hidden'}));
          window.__qaMode=mode;window.__qaCalls=[];window.__qaUsers=[{username:'admin',role:'admin',displayRole:'general_manager',projects:null}];
          window.__qaBackups=[];window.__qaFolderBackups=[];
          window.__qaFolder={configured:false,available:false,folder:''};
        },{state:fixture,mode});
        const page=await context.newPage();
        page.setDefaultTimeout(12000);
        const errors=[];page.on('pageerror',e=>errors.push(e.message));
        try{
          await page.goto(server.resolvedUrls.local[0],{waitUntil:'domcontentloaded'});
          await page.locator('.vitrea-overview').waitFor({state:'visible'});
          await checkSidebar(page,width);
          await checkUserShortcut(page,mode);
          await checkBackup(page,width);
          assert.deepEqual(errors,[],`${width}px ${mode} emitted JS page errors`);
          console.log(`Compact sidebar/backup full App: ${width}px, ${mode}, RTL, no pageerror`);
        }finally{await context.close();}
      }
    }finally{await browser?.close();await server.close();}
  });
