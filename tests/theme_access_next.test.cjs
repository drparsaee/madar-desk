'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const entry=path.resolve(__dirname,'../src/theme_preference.js');
const output=esbuild.buildSync({entryPoints:[entry],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const loaded=new Module(entry,module);loaded.filename=entry;loaded.paths=Module._nodeModulePaths(path.dirname(entry));
loaded._compile(output,entry);
const {readTheme,writeTheme,themeScope}=loaded.exports;
const storage=()=>{const items=new Map();return {
 getItem:key=>items.has(key)?items.get(key):null,
 setItem:(key,value)=>items.set(key,value),
};};
test('theme is individually changeable by admin, editor and viewer identities',()=>{
  const store=storage();
  const admin=themeScope({mode:'client',user:{username:'admin',role:'admin'}});
  const viewer=themeScope({mode:'client',user:{username:'viewer',role:'viewer'}});
  assert.equal(readTheme(store,viewer,'dark'),'dark');
  writeTheme(store,viewer,'light');
  assert.equal(readTheme(store,viewer,'dark'),'light');
  assert.equal(readTheme(store,admin,'dark'),'dark');
  writeTheme(store,admin,'dark');
  assert.equal(readTheme(store,viewer,'dark'),'light');
  assert.equal(store.getItem('madar-ui-theme'),'dark','finance route follows latest local selection');
});
test('invalid theme or missing storage fails harmlessly without saving shared task state',()=>{
  const store=storage(), viewer=themeScope({mode:'client',user:{username:'viewer'}});
  assert.equal(readTheme(store,viewer,'surprise'),'dark');
  assert.throws(()=>writeTheme(store,viewer,'purple'),/theme/i);
  assert.equal(readTheme({getItem(){throw Error('blocked')}},viewer,'light'),'light');
  assert.doesNotThrow(()=>writeTheme({setItem(){throw Error('blocked')}},viewer,'light'));
});
test('theme toggle is not gated by manager permission or shared state save',()=>{
  const app=fs.readFileSync(require('node:path').join(__dirname,'../src/App.jsx'),'utf8');
  assert.match(app,/writeTheme\(localStorage/);
  assert.doesNotMatch(app,/\{canManage&&<button type="button" title=\{data\.settings\?\.theme/);
});
