const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');
const ROOT=path.resolve(__dirname,'..');
const src=fs.readFileSync(path.join(ROOT,'src/sync_health.js'),'utf8');
const compiled=esbuild.transformSync(src,{loader:'js',format:'cjs'}).code;
const mod={exports:{}};
new Function('module','exports',compiled)(mod,mod.exports);
const {syncHealth}=mod.exports;

test('explicit conflict wins over connected or pending, never reports synced',()=>{
  const result=syncHealth({mode:'client',connected:true,pending:false},{conflict:true});
  assert.equal(result.kind,'conflict');
  assert.equal(result.pending,true);
});
test('LAN pending while reachable is not yet synced',()=>{
  assert.equal(syncHealth({mode:'client',connected:true,pending:true}).kind,'pending');
});
test('offline pending reports local queue and never claims transfer',()=>{
  const h=syncHealth({mode:'client',connected:false,pending:true});
  assert.equal(h.kind,'pending');assert.match(h.label,/سرور قطع/);
});
test('client disconnected without draft is not a successful sync',()=>{
  assert.equal(syncHealth({mode:'client',connected:false,pending:false}).kind,'offline');
});
test('in-flight local save cannot be called synced',()=>{
  assert.equal(syncHealth({mode:'client',connected:true,pending:false},{saving:true}).kind,'saving');
});
test('only explicitly connected no-pending client is synced',()=>{
  assert.equal(syncHealth({mode:'client',connected:true,pending:false}).kind,'synced');
  assert.equal(syncHealth({mode:'client',pending:false}).kind,'offline');
});
test('solo remains local and is not branded remote synced',()=>{
  assert.equal(syncHealth({mode:'solo',connected:true,pending:false}).kind,'local');
});
test('App must wire conflict/pending to indicator and retain recovery action',()=>{
  const app=fs.readFileSync(path.join(ROOT,'src/App.jsx'),'utf8');
  assert.match(app,/syncHealth\(status/);
  assert.match(app,/conflict=\{pendingRecovery/);
  assert.match(app,/madar-unsaved-recovery/);
  assert.match(app,/blocked\.current=true/);
});
