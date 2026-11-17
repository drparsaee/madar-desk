'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const file=path.resolve(__dirname,'../src/general_ui_preferences.js');
const bundle=esbuild.buildSync({entryPoints:[file],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const compiled=new Module(file+'.test.cjs',module);
compiled.filename=file+'.test.cjs';compiled.paths=Module._nodeModulePaths(path.dirname(file));
compiled._compile(bundle,compiled.filename);
const {readGeneralUi,writeGeneralUi,normalizeGeneralUi,readThemeMode,writeThemeMode,
  resolveTheme,readTarazQueueConsent,writeTarazQueueConsent}=compiled.exports;
const storage=()=>{
  const records=new Map();return {records,getItem:key=>records.get(key)??null,
    setItem:(key,value)=>records.set(key,value)};
};

test('only validated device-local UI fields persist, isolated for each account',()=>{
  const store=storage();
  assert.deepEqual(readGeneralUi(store,'solo:alice'),{
    font:'estedad',density:'comfortable',textWidth:'standard',motion:'system'});
  const result=writeGeneralUi(store,'solo:alice',{
    font:'vazirmatn',density:'compact',textWidth:'wide',motion:'reduce',financialSecret:'never'});
  assert.equal(result.font,'vazirmatn');
  assert.equal(readGeneralUi(store,'solo:alice').density,'compact');
  assert.equal(readGeneralUi(store,'solo:bob').density,'comfortable');
  assert(!store.records.get('madar-general-ui:solo:alice').includes('financialSecret'));
  assert.equal(normalizeGeneralUi({font:'script',motion:'flash'}).font,'estedad');
  assert.equal(normalizeGeneralUi({font:'script',motion:'flash'}).motion,'system');
});

test('system theme follows OS and explicit theme overrides OS, including persisted mode',()=>{
  const store=storage();
  assert.equal(readThemeMode(store,'solo:a','dark'),'dark');
  writeThemeMode(store,'solo:a','system');
  assert.equal(readThemeMode(store,'solo:a'),'system');
  assert.equal(resolveTheme('system',true),'dark');
  assert.equal(resolveTheme('system',false),'light');
  assert.equal(resolveTheme('light',true),'light');
  assert.throws(()=>writeThemeMode(store,'solo:a','hacked'),TypeError);
});

test('Taraz metadata queue requires explicit opt-in per device/account and has no implicit default',()=>{
  const store=storage();
  assert.equal(readTarazQueueConsent(store,'solo:a'),false);
  writeTarazQueueConsent(store,'solo:a',true);
  assert.equal(readTarazQueueConsent(store,'solo:a'),true);
  assert.equal(readTarazQueueConsent(store,'solo:b'),false);
  writeTarazQueueConsent(store,'solo:a',false);
  assert.equal(readTarazQueueConsent(store,'solo:a'),false);
  assert.throws(()=>writeTarazQueueConsent(store,'solo:a','true'),TypeError);
  assert.equal(readTarazQueueConsent({getItem(){throw Error('blocked');}},'solo:a'),false);
});

test('Madar caller checks permission plus actual opt-in before reaching native queue',()=>{
  const app=fs.readFileSync(path.resolve(__dirname,'../src/App.jsx'),'utf8');
  assert.match(app,/if\(!tarazEnabled\)\{setToast\('/);
  assert.match(app,/if\(!tarazStatus\?\.supported\|\|tarazStatus\?\.postingEnabled!==false\)/);
  assert.match(app,/tarazQueueAvailable=\{tarazEnabled&&tarazStatus\?\.supported===true/);
  assert.match(app,/await api\.tarazIntegrationPrepare\(taskId\)/);
  assert.match(app,/await api\.tarazIntegrationQueue\(taskId,null,targetId\)/);
  assert.match(app,/result\?\.postingPerformed!==false/);
});
