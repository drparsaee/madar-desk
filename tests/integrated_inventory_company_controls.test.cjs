'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const entry=path.join(root,'src/accounting_operational_panels.jsx');
const bundle=esbuild.buildSync({entryPoints:[entry],bundle:true,format:'cjs',platform:'node',
  write:false,jsx:'automatic',loader:{'.css':'empty'},
  external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const mod=new Module(entry,module);mod.filename=entry;
mod.paths=Module._nodeModulePaths(path.dirname(entry));mod._compile(bundle,entry);
const {fixedCompanyPostingOffset,CompanyProfile,LiveInventory}=mod.exports;

test('company posting UTC offset is explicit signed integral minutes, not browser local guess',()=>{
  assert.equal(fixedCompanyPostingOffset('+۲۱۰'),210);
  assert.equal(fixedCompanyPostingOffset('-720'),-720);
  assert.equal(fixedCompanyPostingOffset('٨٤٠'),840);
  assert.equal(fixedCompanyPostingOffset(''),null);
  for(const bad of ['+841','-721','+3.5','Infinity','NaN','03:30','abc','--2']){
    assert.throws(()=>fixedCompanyPostingOffset(bad),Error,bad);
  }
});

test('company profile explains DST and renders source-backed offset setting only to managers',()=>{
  const view={companyProfile:{legalName:'شرکت تست',history:[],postingUtcOffsetMinutes:210}};
  const html=renderToStaticMarkup(React.createElement(CompanyProfile,{
    view,canManage:true,disabled:false,execute:async()=>{},
  }));
  assert.match(html,/UTC \+210 دقیقه/);
  assert.match(html,/اختلاف ثابت ساعت دفتر با UTC/);
  assert.match(html,/تغییر ساعت تابستانی را خودکار دنبال نمی‌کند/);
  const viewer=renderToStaticMarkup(React.createElement(CompanyProfile,{
    view,canManage:false,disabled:false,execute:async()=>{},
  }));
  assert.doesNotMatch(viewer,/<form/);
});

test('inventory receipt requires explicitly documented tax/discount allocation at source',()=>{
  const source=fs.readFileSync(entry,'utf8');
  assert.match(source,/taxTreatment='expense'/);
  assert.match(source,/discountAllocation='single-line-uniform'/);
  assert.match(source,/فقط خرید تک‌ردیفی/);
  assert.match(source,/تخفیف چندردیفی یا تقسیم غیرصحیح/);
  assert.match(source,/ثبت مالیات خرید به هزینه حساب ۵۲۰۰/);
  const view={warehouses:{},items:{},stock:{},stockMovements:{},bills:{},invoices:{}};
  const html=renderToStaticMarkup(React.createElement(LiveInventory,{
    view,canManage:true,canAdmin:true,today:'2026-11-03',unit:'ریال',execute:async()=>{},
  }));
  assert.match(html,/رسید خرید دارای فاکتور/);
  assert.match(html,/فاکتور خرید قطعی/);
});

test('incomplete COGS never appears as final accounting profit in finance UI',()=>{
  const source=fs.readFileSync(path.join(root,'src/standalone_accounting_workspace.jsx'),'utf8');
  assert.match(source,/profitLossComplete===false/);
  assert.match(source,/سود \/ زیان موقت \(بهای تمام‌شده ناقص\)/);
  assert.match(source,/بررسی حواله‌های انبار/);
});
