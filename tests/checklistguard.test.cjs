const {test} = require('node:test');
const assert = require('node:assert/strict');
const esbuild = require('esbuild');
const Module = require('node:module');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const bundled = esbuild.buildSync({entryPoints:[path.join(root,'src/checklistguard.js')],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const script = new Module(path.join(root,'checklistguard.bundle.cjs'),module);
script.filename = path.join(root,'checklistguard.bundle.cjs');
script.paths = Module._nodeModulePaths(root);
script._compile(bundled,script.filename);
const {removeUnpaidLegacyStep} = script.exports;

const task = () => ({checklist:[{id:'paid',cost:125,costCategory:'courier'},{id:'free',cost:0}],
  checklists:[{id:'checklist-legacy',items:[{id:'paid',cost:125},{id:'free',cost:0}]},
    {id:'extra',items:[{id:'another',cost:50}]}]});

test('paid step cannot be removed through legacy editor operation',()=>{
  const source=task();
  assert.equal(removeUnpaidLegacyStep(source,'paid'),null);
  assert.equal(source.checklist[0].cost,125);
  assert.equal(removeUnpaidLegacyStep({...source,checklist:[{id:'paid',cost:'bad'}]},'paid'),null);
});
test('free step removal also updates legacy mirror without touching other groups',()=>{
  const source=task();const before=JSON.stringify(source);
  const patch=removeUnpaidLegacyStep(source,'free');
  assert.deepEqual(patch.checklist.map(x=>x.id),['paid']);
  assert.deepEqual(patch.checklists[0].items.map(x=>x.id),['paid']);
  assert.deepEqual(patch.checklists[1],source.checklists[1]);
  assert.equal(JSON.stringify(source),before);
});
test('duplicate IDs are rejected and UI invokes guarded handler',()=>{
  assert.equal(removeUnpaidLegacyStep({checklist:[{id:'x'},{id:'x'}]},'x'),null);
  assert.equal(removeUnpaidLegacyStep({checklist:[{
    id:'vendor',cost:0,expenseItems:[{id:'cost.1',unitPrice:null}]}]},'vendor'),null);
  const app=fs.readFileSync(path.join(root,'src/checklist_task_row.jsx'),'utf8');
  assert.match(app,/const result=removeUnpaidLegacyStep\(task,step\.id\)/);
  // Roles below manager cannot remove lines even when their redacted cost is 0.
  assert.match(app,/const canDelete=canEdit&&canManage&&!paid/);
});
