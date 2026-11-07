'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {prepareGanttShift}=require('../server/gantt_shift_guard.cjs');
const revision='server-rev-1';
const task=(id,start,end,dependencies=[],projectId='p')=>({
  id,projectId,plannedStart:start,plannedEnd:end,dependencies});
const state=()=>({version:1,tasks:[
  task('a','2026-11-01','2026-11-03'),
  task('b','2026-11-05','2026-11-06',['a']),
  task('c','2026-11-04','2026-11-08',['a']),
  task('d','2026-11-09','2026-11-10',['b','c']),
  task('e','2026-11-19','2026-11-20',['a']),
  task('other','2026-11-01','2026-11-02',[],'q')
]});
const req=(days,taskId='a')=>({taskId,days,expectedRevision:revision});
const auth={role:'editor',projects:['p'],actualRevision:revision};
const failure=(s,r,a,code)=>assert.throws(()=>prepareGanttShift(s,r,a),
  error=>error.code===code);

test('host preflight recalculates all successors from full snapshot with no mutation',()=>{
  const before=state(),copy=structuredClone(before);
  const result=prepareGanttShift(before,req(2),auth);
  assert.equal(result.scope,'full_host');
  assert.equal(result.changedCount,4);
  assert.deepEqual(result.updates,[
    {id:'a',plannedStart:'2026-11-03',plannedEnd:'2026-11-05'},
    {id:'b',plannedStart:'2026-11-06',plannedEnd:'2026-11-07'},
    {id:'c',plannedStart:'2026-11-06',plannedEnd:'2026-11-10'},
    {id:'d',plannedStart:'2026-11-11',plannedEnd:'2026-11-12'}
  ]);
  assert.deepEqual(before,copy);
  assert.deepEqual(result.nextState.tasks[5],before.tasks[5]);
  assert.equal(prepareGanttShift(before,req(-1),auth).changedCount,1);
});
test('host gate refuses stale revision, viewer and revoked grant',()=>{
  const s=state();
  failure(s,req(1),{...auth,actualRevision:'new'},'stale_revision');
  failure(s,req(1),{...auth,role:'viewer'},'forbidden');
  failure(s,req(1),{...auth,projects:['q']},'forbidden');
  failure(s,{...req(1),taskId:'other'},auth,'forbidden');
  failure(s,{...req(1),extra:true},auth,'invalid_request');
  failure(s,req(0),auth,'invalid_request');
  failure(s,req(3661),auth,'invalid_request');
});
test('host refuses hidden, archived, corrupt, conflicted or cross-project effects',()=>{
  const s=state();
  s.tasks.push(task('out-of-scope','2026-11-10','2026-11-12',['a'],'q'));
  failure(s,req(2),auth,'outside_project');
  const deleted=state();
  deleted.tasks[1].archived=true;
  failure(deleted,req(2),auth,'outside_project');
  const missing=state();
  missing.tasks[1].dependencies=['hidden-card'];
  failure(missing,req(2),auth,'outside_project');
  const conflict=state();
  conflict.tasks[1].plannedStart='2026-11-02';
  failure(conflict,req(2),auth,'existing_conflict');
  const cycle=state();
  cycle.tasks[0].dependencies=['d'];
  failure(cycle,req(2),auth,'dependency_cycle');
  const noDate=state();
  noDate.tasks[1].plannedEnd='';
  failure(noDate,req(2),auth,'missing_plan');
  const reordered=state();
  reordered.tasks[0].plannedEnd='broken';
  reordered.tasks=[reordered.tasks[1],...reordered.tasks.filter(t=>t.id!=='b')];
  failure(reordered,req(2),auth,'missing_plan');
  const corruptOther=state();
  corruptOther.tasks[5].dependencies='bad value';
  failure(corruptOther,req(2),auth,'invalid_dependency');
  failure(state(),req(-3,'b'),auth,'earlier_than_predecessor');
});
test('host rejects dates outside supported calendar and handles years 0001 to 0099',()=>{
  const s={tasks:[task('early','0001-01-01','0001-01-02')]};
  const result=prepareGanttShift(s,req(1,'early'),auth);
  assert.equal(result.updates[0].plannedStart,'0001-01-02');
  failure(s,req(-1,'early'),auth,'date_range');
  const upper={tasks:[task('late','9999-12-30','9999-12-31')]};
  failure(upper,req(1,'late'),auth,'date_range');
});
