'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const Module=require('node:module');
const esbuild=require('esbuild');
const entry=path.resolve(__dirname,'../src/host_backup_health.js');
const output=esbuild.buildSync({entryPoints:[entry],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const loaded=new Module(entry,module);loaded.filename=entry;loaded.paths=Module._nodeModulePaths(path.dirname(entry));
loaded._compile(output,entry);
const {hostBackupHealth}=loaded.exports;
test('host failures are explicit and do not appear as healthy backup',()=>{
  assert.equal(hostBackupHealth({running:true,lastError:'synthetic disk full'}).kind,'error');
  assert.match(hostBackupHealth({running:true,lastError:'synthetic disk full'}).description,/synthetic disk full/);
  assert.equal(hostBackupHealth({running:false}).kind,'stopped');
  assert.equal(hostBackupHealth({running:true,lastSuccess:'2026-11-02T00:00:00+00:00'}).kind,'ok');
  assert.equal(hostBackupHealth(null).kind,'unknown');
  assert.equal(hostBackupHealth({running:false},true).kind,'client');
});
test('host backup UI refreshes health and refuses local backup on clients',()=>{
  const app=fs.readFileSync(path.join(__dirname,'../src/App.jsx'),'utf8');
  assert.match(app,/hostBackupHealth\(automaticBackup,isClient\)/);
  assert.match(app,/setInterval\(readBackupHealth,30000\)/);
  assert.match(app,/disabled=\{!!busy\|\|isClient\} onClick=\{\(\)=>operation\('local'/);
});
