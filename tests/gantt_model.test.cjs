const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const output=esbuild.buildSync({entryPoints:[path.join(root,'src/gantt_model.js')],
  platform:'node',format:'cjs',bundle:true,write:false}).outputFiles[0].text;
const mod=new Module(path.join(root,'gantt-model-test.cjs'),module);
mod.filename=path.join(root,'gantt-model-test.cjs');
mod.paths=Module._nodeModulePaths(root);
mod._compile(output,mod.filename);
const {dayNumber,dayString,ganttAxis,validPlan,shiftPlan,barPosition,buildGanttRows}=mod.exports;

test('ISO planning dates validate leap years and preserve chronological ranges',()=>{
  assert.equal(dayNumber('2024-02-29')!==null,true);
  assert.equal(dayNumber('2026-02-29'),null);
  assert.equal(dayNumber('2026-13-01'),null);
  assert.equal(dayString(dayNumber('0001-01-01')),'0001-01-01');
  assert.equal(dayNumber('0099-12-31')!==null,true);
  assert.equal(dayNumber('0000-01-01'),null);
  assert.equal(validPlan('invalid',''),false);
  assert.equal(validPlan('2026-11-08','2026-11-07'),false);
  assert.equal(validPlan('2026-11-08','2026-11-08'),true);
  assert.equal(validPlan('',''),true);
  assert.equal(validPlan('2026-11-08',''),true);
  assert.deepEqual(shiftPlan({plannedStart:'2026-11-08',plannedEnd:'2026-11-10'},4),
    {plannedStart:'2026-11-12',plannedEnd:'2026-11-14'});
  assert.equal(dayString(dayNumber('2026-11-07')+1),'2026-11-08');
});
test('day/week/month axes use UTC stable calendar boundaries and locate bars',()=>{
  for(const scale of ['day','week','month']){
    const axis=ganttAxis('2026-11-07',scale);
    assert.ok(axis.length>=18);
    for(let i=1;i<axis.length;i++)assert.equal(axis[i-1].end,axis[i].start);
    assert.ok(axis.every(c=>c.end>c.start));
    const bar=barPosition({plannedStart:'2026-11-07',plannedEnd:'2026-11-09'},axis);
    assert.ok(bar&&bar.width>0);
  }
  assert.equal(barPosition({plannedStart:'',plannedEnd:''},ganttAxis('2026-11-07')),null);
});
test('large task list caps rendered rows and filters deleted/archived tasks',()=>{
  const items=Array.from({length:1000},(_,i)=>({id:'t'+i,title:'Task '+i,
    plannedStart:'2026-11-07',plannedEnd:'2026-11-08'}));
  items[0].deleted=true;items[1].archived=true;
  const outcome=buildGanttRows(items);
  assert.equal(outcome.total,998);
  assert.equal(outcome.rows.length,350);
  assert.equal(outcome.truncated,true);
});
