'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const dir=path.resolve(__dirname,'../src');
const source=fs.readFileSync(path.join(dir,'features.jsx'),'utf8');
const css=fs.readFileSync(path.join(dir,'settings_density.css'),'utf8');
const labels=fs.readFileSync(path.join(dir,'labels.jsx'),'utf8');
const moduleCode=esbuild.buildSync({entryPoints:[path.join(dir,'features.jsx')],bundle:true,
  platform:'node',format:'cjs',write:false,jsx:'automatic',loader:{'.css':'empty'},
  external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const mod=new Module(path.join(dir,'qa-settings.cjs'),module);
mod.filename=path.join(dir,'qa-settings.cjs');mod.paths=Module._nodeModulePaths(dir);
mod._compile(moduleCode,mod.filename);
const {SettingsPanel}=mod.exports;
const html=renderToStaticMarkup(React.createElement(SettingsPanel,{
  data:{settings:{theme:'dark'},stages:[{id:'a',label:'تست',color:'#112233'}],tasks:[],projects:[]},
  canManage:true,theme:'dark',themeMode:'system',tarazStatus:{supported:true,pending:2,postingEnabled:false,message:'صندوق محلی'},
  generalUi:{font:'vazirmatn',density:'compact',textWidth:'wide',motion:'reduce'},
  onChange:()=>{},onClose:()=>{},onThemeChange:()=>{},onGeneralUiChange:()=>{},onTarazEnabledChange:()=>{},
}));

test('five independent settings views, minimalist general rows and functioning selectors',()=>{
  for(const tab of ['عمومی','اتصال تراز','حساب و ثبت‌نام','خرید اشتراک','پیشرفته'])
    assert(html.includes(tab),tab);
  for(const control of ['madar-setting-font','madar-setting-density','madar-setting-width','madar-setting-motion'])
    assert(html.includes('id="'+control+'"'),control);
  assert.match(html,/aria-pressed="true"[^>]*>.*سیستم/);
  assert.match(html,/class="settings-general-row"/);
  assert.match(css,/settings-general-row\{display:flex;justify-content:space-between/);
  assert.match(css,/settings-page-nav button\.active/);
  assert.match(css,/settings-special-page\[hidden\]/);
});

test('account creation routes to existing LAN admin, subscription checkout explicitly disabled',()=>{
  assert.match(source,/onOpenLanSignup/);
  assert.match(source,/onOpenUserManagement/);
  assert.match(html,/ساخت حساب شبکه|راه‌اندازی حساب شبکه|فرم ایجاد حساب شبکه/);
  assert.match(html,/ثبت‌نام عمومی با ایمیل/);
  assert.match(html,/سرور صدور اشتراک، طرح‌ها، قیمت‌های تأییدشده/);
  assert.match(html,/ادامه خرید \(غیرفعال\)/);
  assert.match(html,/disabled=""[^>]*title="درگاه پرداخت و طرح‌های تأییدشده موجود نیست"/);
  assert.doesNotMatch(html,/پرداخت موفقیت‌آمیز بود|اشتراک شما فعال شد/);
});

test('Taraz tab describes opt-in proposals and never invents remote peer online status',()=>{
  assert.match(html,/اجازهٔ ارسال دستی پیشنهاد از کارت به تراز/);
  assert.match(html,/پیش‌فرض خاموش است/);
  assert.match(html,/صندوق محلی مدار آماده است؛ این به معنی اجرا یا نصب‌بودن تراز نیست/);
  assert.doesNotMatch(html,/تراز آنلاین است|حسابداری متصل و فعال/);
});

test('label editor has sticky top delete trigger and in-place confirmation before palette',()=>{
  assert(labels.indexOf('label-editor-delete--header')<labels.indexOf('label-editor-palette'));
  assert(labels.indexOf('id="label-editor-delete-confirm"')<labels.indexOf('label-editor-palette'));
  assert.match(labels,/aria-expanded=\{confirmDelete\}/);
  assert.match(labels,/screen==='edit'&&canManage&&onDelete/);
  const stylesheet=fs.readFileSync(path.join(dir,'labels.css'),'utf8');
  assert.match(stylesheet,/\.label-editor-header\{position:sticky;top:0/);
  assert.match(stylesheet,/\.label-editor > \.label-editor-confirm\{position:sticky/);
});
