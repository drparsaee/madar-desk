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
const jsx=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
const features=fs.readFileSync(path.join(root,'src/features.jsx'),'utf8');
const bundle=esbuild.buildSync({entryPoints:[path.join(root,'src/features.jsx')],bundle:true,
  format:'cjs',platform:'node',write:false,jsx:'automatic',loader:{'.css':'empty'},
  external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const loaded=new Module(path.join(root,'src','lan-entry-contract.cjs'),module);
loaded.filename=path.join(root,'src','lan-entry-contract.cjs');
loaded.paths=Module._nodeModulePaths(root);
loaded._compile(bundle,loaded.filename);
const {LanPanel}=loaded.exports;
const render=(mode,role,initialView='users')=>renderToStaticMarkup(React.createElement(LanPanel,{
  api:{},projects:[],onClose:()=>{},onRefresh:async()=>{},onConnected:async()=>{},
  initialView,status:{mode,user:{role,username:'admin'},transport:'https',port:48370},
}));

test('dock network status and users icon do not open the same view',()=>{
  assert.match(jsx,/showDetails=\{openNetwork\}/);
  assert.match(jsx,/canManage&&lanStatus\.mode!=='solo'&&<button[^>]+onClick=\{openUserManagement\}/);
  assert.match(jsx,/setLanInitialView\('users'\);setLanOpen\(true\)/);
  assert.match(jsx,/setLanInitialView\('connection'\);setLanOpen\(true\)/);
  assert.match(jsx,/initialView=\{lanInitialView\}/);
  assert.doesNotMatch(jsx,/aria-label="شبکه محلی"/);
});
test('authenticated LAN admin opens real account creation with permission controls',()=>{
  const html=render('server','admin');
  assert.match(html,/تعریف کاربر و تعیین سطح دسترسی/);
  assert.match(html,/ساخت حساب جدید/);
  assert.match(html,/ایجاد حساب کاربر/);
  assert.match(html,/مجوز فنی \(مستقل از قالب نمایش\)/);
  assert.match(features,/if\(initialView==='users'&&canManage\)loadUsers\(\)/);
  assert.match(features,/await api\.lanSaveUser\(/);
});
test('solo and viewer users cannot enter privileged user management',()=>{
  const solo=render('solo','admin');
  assert.match(solo,/تعریف کاربران و تعیین دسترسی پس از راه‌اندازی میزبان/);
  assert.doesNotMatch(solo,/ساخت حساب جدید/);
  assert.doesNotMatch(render('server','viewer'),/ساخت حساب جدید/);
});
