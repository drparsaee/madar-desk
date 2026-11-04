'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');
const Module=require('node:module');
const root=path.resolve(__dirname,'..');
const file=path.join(root,'src','advanced_filter_scope.js');
const output=esbuild.buildSync({entryPoints:[file],bundle:true,platform:'node',
  format:'cjs',write:false}).outputFiles[0].text;
const moduleShim=new Module(file,module);
moduleShim.filename=file;moduleShim.paths=Module._nodeModulePaths(root);
moduleShim._compile(output,file);
const {EMPTY_ADVANCED_FILTER,readScopedAdvancedFilter,updateScopedAdvancedFilter}=
  moduleShim.exports;
test('active filters are scoped to identity and board before rendering, not only via an effect',()=>{
  const scopeA='[solo,alice]|board-a',scopeB='[solo,bob]|board-a';
  let state={scope:'',value:EMPTY_ADVANCED_FILTER};
  state=updateScopedAdvancedFilter(state,scopeA,
    prior=>({...prior,member:'alice',status:'doing'}));
  assert.equal(readScopedAdvancedFilter(state,scopeA).member,'alice');
  assert.equal(readScopedAdvancedFilter(state,scopeB).member,'all');
  assert.equal(readScopedAdvancedFilter(state,'[solo,alice]|board-b').status,'all');
  state=updateScopedAdvancedFilter(state,scopeB,
    prior=>({...prior,priority:'high'}));
  assert.equal(readScopedAdvancedFilter(state,scopeB).member,'all');
  assert.equal(readScopedAdvancedFilter(state,scopeB).priority,'high');
  assert.equal(readScopedAdvancedFilter(state,scopeA).priority,'all');
});
test('task UI passes host identity and board scope to both saved and active filters',()=>{
  const source=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
  assert.match(source,/const advancedScope=String\(plannerIdentity\(lanStatus\)\)\+'\|'\+boardViewScope/);
  assert.match(source,/const advanced=readScopedAdvancedFilter\(advancedState,advancedScope\)/);
  assert.match(source,/updateScopedAdvancedFilter\(previous,advancedScope,update\)/);
  assert.match(source,/identity=\{plannerIdentity\(lanStatus\)\} scopeId=\{boardViewScope\}/);
});
