'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const python=fs.readFileSync(path.resolve(__dirname,'../native_app.py'),'utf8');
function bridge(name,timers){
  const match=new RegExp('^'+name+' = """([\\s\\S]*?)"""','m').exec(python);
  assert.ok(match,name+' native bridge declaration not found');
  const javascript=match[1].replace(/^\s*<script>\s*/,'').replace(/\s*<\/script>\s*$/,'');
  const window={pywebview:{api:{}}};
  const pending=[];
  const sandbox={window,Promise,Object,Error,setTimeout:timers?
    (callback)=>{pending.push(callback);return pending.length;}:
    setTimeout};
  vm.runInNewContext(javascript,sandbox,{filename:name+'.js',timeout:1000});
  return {window,pending};
}

test('accounting methods wait for a real WebView2 export after route navigation',async()=>{
  const {window,pending}=bridge('ACCOUNTING_JS_BRIDGE',true);
  const request=window.madar.standaloneAccountingRead();
  assert.equal(pending.length,1,'missing native method schedules a bounded retry');
  window.pywebview.api.standaloneAccountingRead=async()=>({revision:7,currency:'RIAL'});
  pending.shift()();
  assert.equal((await request).revision,7);
});

test('missing native bridge rejects rather than TypeError or infinite loading',async()=>{
  const {window,pending}=bridge('ACCOUNTING_JS_BRIDGE',true);
  const request=window.madar.standaloneAccountingRead();
  let count=0;
  while(pending.length){
    const tick=pending.shift();tick();count++;
    assert.ok(count<=80,'retry must be bounded');
  }
  await assert.rejects(request,/Native bridge method unavailable: standaloneAccountingRead/);
  assert.equal(count,75);
});

test('available accounting writer executes exactly once; host remains authoritative',async()=>{
  const {window,pending}=bridge('ACCOUNTING_JS_BRIDGE',true);
  const observed=[];
  window.pywebview.api.standaloneAccountingCommand=async request=>{
    observed.push(request);
    return {accepted:true};
  };
  const payload={command:{type:'synthetic'},expectedRevision:0};
  const result=await window.madar.standaloneAccountingCommand(payload);
  assert.equal(result.accepted,true);
  assert.equal(observed.length,1);
  assert.equal(observed[0],payload);
  assert.equal(pending.length,0);
});

test('task desktop bridge also waits for exported methods before invoking',async()=>{
  const {window,pending}=bridge('JS_BRIDGE',true);
  const request=window.madar.getState();
  window.pywebview.api.getState=async()=>({version:1});
  pending.shift()();
  assert.equal((await request).version,1);
});
