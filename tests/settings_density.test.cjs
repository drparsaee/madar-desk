const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const css=fs.readFileSync(path.join(root,'src/settings_density.css'),'utf8');
const source=fs.readFileSync(path.join(root,'src/features.jsx'),'utf8');
const bundle=esbuild.buildSync({entryPoints:[path.join(root,'src/features.jsx')],
  bundle:true,platform:'node',format:'cjs',write:false,jsx:'automatic',
  loader:{'.css':'empty'},external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const loaded=new Module(path.join(root,'src','settings-density-test.cjs'),module);
loaded.filename=path.join(root,'src','settings-density-test.cjs');
loaded.paths=Module._nodeModulePaths(root);
loaded._compile(bundle,loaded.filename);
const {SettingsPanel,LanPanel}=loaded.exports;

function renderSettings(canManage=true){
  return renderToStaticMarkup(React.createElement(SettingsPanel,{
    data:{settings:{theme:'light'},stages:[{id:'inbox',label:'صندوق ورودی',subtitle:'جدید',color:'#aabbcc'}],tasks:[],projects:[]},
    canManage,onChange:()=>{},onClose:()=>{},onCalendarChange:()=>{},
    widgetSettings:{mode:'both'},onWidgetSettingsChange:()=>{},
  }));
}

// The LAN users view normally opens after clicking "تعریف کاربر". Force only that
// initial UI state for a static markup check, without calling the host/network.
function renderLanManager(){
  const previous=React.useState;
  React.useState=function(initial){
    if(initial==='connection')return ['users',()=>{}];
    return previous(initial);
  };
  try{
    return renderToStaticMarkup(React.createElement(LanPanel,{
      api:{},projects:[{id:'p1',name:'پروژه نمونه'}],onClose:()=>{},
      onRefresh:async()=>{},onConnected:async()=>{},
      status:{mode:'server',port:48370,transport:'https',user:{role:'admin',username:'owner'}},
    }));
  }finally{React.useState=previous;}
}

test('settings show compact quick choices and widget controls with explicit advanced disclosures',()=>{
  const html=renderSettings();
  assert.match(source,/import '\.\/settings_density\.css';/);
  assert.match(html,/class="dialog settings-modal settings-density" dir="rtl"/);
  assert.match(html,/class="settings-density__quick-grid"/);
  assert.match(html,/ظاهر برنامه/);
  assert.match(html,/تقویم و نمایش تاریخ/);
  assert.match(html,/مدیریت هزینه‌ها/);
  assert.match(html,/شخصی‌سازی ساعت و تاریخ/);
  assert.match(html,/<details class="settings-density__disclosure"><summary>/);
  assert.match(html,/تنظیم اولویت‌های کارت/);
  assert.match(html,/مدیریت ستون‌ها و مراحل برد/);
  assert.match(html,/افزودن ستون/);
  assert.match(html,/تعریف اولویت/);
});

test('non-admin can still personalize calendar and widget without gaining global editing',()=>{
  const html=renderSettings(false);
  assert(html.includes('شخصی‌سازی ساعت و تاریخ'));
  assert(html.includes('انتخاب تقویم'));
  assert(html.includes('disabled=""'));
  assert(!html.includes('افزودن ستون'));
  assert(!html.includes('تعریف اولویت</button>'));
});

test('LAN manager keeps user CRUD, technical ACL, profile templates and save actions in grouped areas',()=>{
  const html=renderLanManager();
  assert.match(html,/class="dialog lan-modal lan-density" dir="rtl"/);
  assert.match(html,/class="lan-density__workspace"/);
  assert.match(html,/<aside class="lan-density__directory" aria-label="حساب‌ها و قالب‌های موجود">/);
  assert.match(html,/<section class="lan-density__editor" aria-label="فرم مدیریت حساب" tabindex="-1">/);
  assert.match(html,/قالب‌های نقش و سطح نمایش/);
  assert.match(html,/مشخصات حساب/);
  assert.match(html,/نقش و دسترسی/);
  assert.match(html,/مجوز فنی \(مستقل از قالب نمایش\)/);
  assert.match(html,/شخصی‌سازی امکانات این کاربر/);
  assert.match(html,/آواتار و نماد کاربر/);
  assert.match(html,/ایجاد حساب کاربر/);
  assert.match(html,/class="lan-actions lan-density__actions"/);
  assert.match(html,/مشاهده‌گر: فقط خواندن/);
  assert.match(html,/مدیر میزبان: مدیریت همه بخش‌ها و کاربران/);
  assert.match(html,/راهنمای اتصال امن و اثر انگشت گواهی/);
  assert.match(source,/editorRef\.current\?\.focus\(\)/);
  assert.match(source,/scrollIntoView\?\.\(\{block:'nearest'\}\)/);
});

test('dedicated styles give desktop density, RTL, dark mode, keyboard focus and mobile stacking',()=>{
  assert.match(css,/\.settings-modal\.settings-density\{width:min\(980px/);
  assert.match(css,/\.lan-modal\.lan-density\{width:min\(1080px/);
  assert.match(css,/\.settings-density__quick-grid\{display:grid;grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
  assert.match(css,/\.lan-density__workspace\{display:grid;grid-template-columns:/);
  assert.match(css,/@media\(max-width:780px\)/);
  assert.match(css,/@media\(max-width:600px\)/);
  assert.match(css,/\.lan-density__workspace\{grid-template-columns:minmax\(0,1fr\)\}/);
  assert.match(css,/\.lan-density__editor \.setting-grid\{grid-template-columns:1fr\}/);
  assert.match(css,/summary:focus-visible/);
  assert.match(css,/:root\[data-theme="dark"\]/);
  assert.match(css,/scrollbar|overflow:auto/);
  assert.match(css,/\[open\]>summary/);
  assert(!/display:none!important/.test(css));
});
