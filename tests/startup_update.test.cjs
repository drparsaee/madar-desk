const test=require('node:test');
const assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const path=require('node:path');

const moduleUrl=pathToFileURL(path.resolve(__dirname,'../src/startup_update.mjs')).href;

test('startup downloads a host-verified update but never triggers installation',async()=>{
  const {checkAndCacheAvailableUpdate}=await import(moduleUrl);
  const calls=[];
  const api={
    releaseCheck:async()=>{calls.push('check');return {available:true,latest:'1.0.27'};},
    releaseDownload:async()=>{calls.push('download');return {verified:true,path:'host-owned'};},
    releaseInstall:async()=>{calls.push('install');}
  };
  const result=await checkAndCacheAvailableUpdate(api,{onFound:info=>calls.push('found:'+info.latest)});
  assert.deepEqual(calls,['check','found:1.0.27','download']);
  assert.deepEqual(result,{info:{available:true,latest:'1.0.27'},downloaded:true});
});

test('no stable update means no download or install',async()=>{
  const {checkAndCacheAvailableUpdate}=await import(moduleUrl);
  let downloaded=false,found='unexpected';
  const result=await checkAndCacheAvailableUpdate({
    releaseCheck:async()=>({available:false}),
    releaseDownload:async()=>{downloaded=true;}
  },{onFound:info=>{found=info;}});
  assert.equal(found,null);
  assert.equal(downloaded,false);
  assert.deepEqual(result,{info:null,downloaded:false});
});

test('unverified download fails closed and allows caller to preserve manual retry',async()=>{
  const {checkAndCacheAvailableUpdate}=await import(moduleUrl);
  let found;
  await assert.rejects(checkAndCacheAvailableUpdate({
    releaseCheck:async()=>({available:true,latest:'1.0.27'}),
    releaseDownload:async()=>({verified:false})
  },{onFound:info=>{found=info;}}),/not verified/);
  assert.equal(found.latest,'1.0.27');
});
