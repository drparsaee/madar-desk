const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const compiled = esbuild.buildSync({entryPoints:[path.resolve(__dirname,'../src/planner_identity.js')],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const loader=new Module(path.resolve(__dirname,'../src/planner_identity.cjs'),module);
loader.filename=path.resolve(__dirname,'../src/planner_identity.cjs');loader.paths=Module._nodeModulePaths(process.cwd());loader._compile(compiled,loader.filename);
const {plannerIdentity}=loader.exports;

test('different long remote URLs remain distinct and identity is stable',()=>{
  const prefix='https://example.org/'+('long-'.repeat(20));
  const base={mode:'client',user:{username:'agent'},fingerprint:'sha256'};
  assert.notEqual(plannerIdentity({...base,url:prefix+'alpha'}),plannerIdentity({...base,url:prefix+'beta'}));
  assert.equal(plannerIdentity({...base,url:prefix+'alpha'}),plannerIdentity({...base,url:prefix+'alpha'}));
});
test('incomplete remote identity fails closed instead of sharing unknown namespace',()=>{
  assert.equal(plannerIdentity({mode:'client',user:{username:'agent'}}),null);
  assert.equal(plannerIdentity({mode:'client',url:'https://a.example',user:{}}),null);
  assert.notEqual(plannerIdentity({mode:'solo',user:{username:'a'}}),plannerIdentity({mode:'solo',user:{username:'b'}}));
});
