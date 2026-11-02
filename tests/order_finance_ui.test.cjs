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

test('sales card has compact quantity and a single invoice action with no extraneous currency note',()=>{
  const entry=path.join(root,'src/order_finance_fields.jsx');
  const built=esbuild.buildSync({entryPoints:[entry],platform:'node',bundle:true,format:'cjs',write:false,
    loader:{'.css':'empty'},external:['react','react/jsx-runtime','react-dom','lucide-react']}).outputFiles[0].text;
  const moduleInstance=new Module(entry,module);
  moduleInstance.filename=entry;
  moduleInstance.paths=Module._nodeModulePaths(path.dirname(entry));
  moduleInstance._compile(built,entry);
  const {OrderSaleFields}=moduleInstance.exports;
  const html=renderToStaticMarkup(React.createElement(OrderSaleFields,{
    task:{saleCurrency:'RIAL',salePartyId:'p',saleQuantity:17,saleUnitPrice:500},
    api:{standaloneAccountingRead:async()=>({view:{parties:{}}})},
    canManage:true,canEdit:true,onUpdate:()=>{},onPrepare:()=>{}}));
  assert.match(html,/class="order-sale-fields__quantity"/);
  assert.match(html,/value="17"/);
  assert.match(html,/>ثبت فاکتور<\/button>/);
  assert.match(html,/صدور نهایی پس از بررسی و تأیید در حسابداری مستقل/);
  assert.doesNotMatch(html,/مشخصات تولید وارد حسابداری نمی‌شود|واحد سفارش‌های جدید ریال است|آماده‌سازی فاکتور/);
  const css=fs.readFileSync(path.join(root,'src/order_finance_fields.css'),'utf8');
  assert.match(css,/order-sale-fields__quantity input\{[^}]*max-width:96px/);
});
