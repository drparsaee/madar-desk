const test=require('node:test');
const assert=require('node:assert/strict');
const esbuild=require('esbuild');
const Module=require('node:module');
const path=require('node:path');
const file=path.resolve(__dirname,'../src/managed_display.js');
const source=esbuild.buildSync({entryPoints:[file],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const result=new Module(file,module);result.filename=file;result.paths=Module._nodeModulePaths(path.dirname(file));result._compile(source,file);
const {resolvedDisplayScope,isManagedFeatureVisible}=result.exports;
test('first private owner opens full manager display, unknown never does',()=>{
  assert.equal(resolvedDisplayScope({mode:'solo',user:{role:'admin'}}).label,'مدیرکل');
  assert.equal(resolvedDisplayScope({mode:'solo',user:{role:'admin'}}).mode,'finance');
  assert.equal(resolvedDisplayScope({mode:'client',user:null}).mode,'basic');
});
test('custom role cannot become technical administrator via presentation flags',()=>{
  const scope=resolvedDisplayScope({mode:'client',user:{role:'editor',displayRole:'senior',displayRoleLabel:'مدیر ارشد',displayMode:'finance',displayFeatures:['reporting','projectFinance','__proto__']}});
  assert.equal(scope.label,'مدیر ارشد');
  assert.deepEqual(scope.features,['reporting','projectFinance']);
  assert.equal(isManagedFeatureVisible(scope,'reporting',{canManage:false,canEdit:true}),true);
  assert.equal(isManagedFeatureVisible(scope,'projectFinance',{canManage:false,canEdit:true}),false);
  assert.equal(isManagedFeatureVisible(scope,'planner',{canManage:false,canEdit:true}),false);
  assert.equal(isManagedFeatureVisible(scope,'backupRestore',{canManage:false,canEdit:true}),true);
});
