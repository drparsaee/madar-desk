const {test}=require('node:test');
const assert=require('node:assert/strict');
const esbuild=require('esbuild');
const source=require('node:fs').readFileSync('src/parsian_local_backup_preflight.js','utf8');
const bundled=esbuild.transformSync(source,{loader:'js',format:'cjs',target:'es2020'}).code;
const moduleShim={exports:{}};
new Function('module','exports',bundled)(moduleShim,moduleShim.exports);
const {classifyLocalParsianBackup,inspectBackupFileLocally}=moduleShim.exports;

test('TAPE is media-only and never an import authorization',()=>{
  const header=Uint8Array.from([84,65,80,69,0,0,3,0,140,0,14,1,0,0,0,0]);
  const v=classifyLocalParsianBackup({name:'offline-copy.BAK',size:7555584,header});
  assert.equal(v.status,'sqlserver-media');
  assert.equal(v.signature,'TAPE');
  assert.match(v.message,/انتقال غیرفعال/);
  assert.equal(v.canImport,undefined);
});
test('unknown and truncated media fail closed',()=>{
  assert.equal(classifyLocalParsianBackup({name:'x.bak',size:1024,header:new Uint8Array(16)}).status,'unknown');
  assert.equal(classifyLocalParsianBackup({name:'x.bak',size:1024,header:new Uint8Array(15)}).status,'invalid');
});
test('suffix and size are validated before byte read',async()=>{
  let accessed=false;
  const file={name:'business.txt',size:4096,slice(){accessed=true;throw Error('unexpected read')}};
  const result=await inspectBackupFileLocally(file);
  assert.equal(result.status,'invalid');
  assert.equal(accessed,false);
  assert.equal(classifyLocalParsianBackup({name:'x.bak',size:50*1024**3+1,header:new Uint8Array(16)}).status,'invalid');
});
test('preflight reads exactly first 16 bytes and no upload/network',async()=>{
  const bytes=Uint8Array.from([84,65,80,69,...Array(12).fill(0)]);
  let count=0;
  const file={name:'fake.bak',size:2048,slice(start,end){
    count++;
    assert.equal(start,0);assert.equal(end,16);
    return {async arrayBuffer(){return bytes.buffer}};
  }};
  const result=await inspectBackupFileLocally(file);
  assert.equal(result.status,'sqlserver-media');
  assert.equal(count,1);
});
