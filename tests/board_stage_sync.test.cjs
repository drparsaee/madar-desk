'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {transformSync}=require('esbuild');
const code=fs.readFileSync(path.join(__dirname,'../src/board_stage_sync.js'),'utf8');
const transformed=transformSync(code,{format:'cjs',loader:'js'}).code;
const moduleObject={exports:{}};
new Function('module','exports',transformed)(moduleObject,moduleObject.exports);
const {propagateAddedWorkspaceStages,boardForColumn}=moduleObject.exports;
const stage=id=>({id,label:id,color:'#64748b'});
const makeState=()=>({stages:[stage('original')],boards:[
  {id:'a',projectId:'pa',workspaceId:'w',stages:[stage('original')]},
  {id:'b',projectId:'pb',workspaceId:'w',stages:[stage('original')]},
  {id:'other',projectId:'pc',workspaceId:'other',stages:[stage('original')]},
  {id:'archived',projectId:'pd',workspaceId:'w',archived:true,stages:[stage('original')]},
],tasks:[{id:'card',boardId:'a',listId:'original',status:'original',cost:12345}]});

test('new stage added in workspace settings appears as selectable board stage without card or financial mutation',()=>{
  const before=makeState(), added=stage('custom-new');
  const after=propagateAddedWorkspaceStages(before,{...before,stages:[...before.stages,added]},'w');
  assert.deepEqual(after.boards.map(b=>b.stages.map(s=>s.id)),[
    ['original','custom-new'],['original','custom-new'],['original'],['original']]);
  assert.strictEqual(after.tasks,before.tasks);
  assert.equal(after.tasks[0].cost,12345);
  assert.equal(boardForColumn(after.boards,'pa','custom-new','a')?.id,'a');
});
test('board-specific display properties are preserved and duplicate list IDs are never created',()=>{
  const before=makeState(),added=stage('custom-new');
  before.boards[0].stages.push({...added,label:'نام مخصوص برد',color:'#112233'});
  const after=propagateAddedWorkspaceStages(before,{...before,stages:[...before.stages,added]},'w');
  assert.equal(after.boards[0].stages.length,2);
  assert.equal(after.boards[0].stages[1].label,'نام مخصوص برد');
  assert.equal(after.boards[1].stages[1].label,'custom-new');
});
test('global stage rename updates inherited labels but never overwrites a board-specific override',()=>{
  const before=makeState();
  before.boards[1].stages[0].label='نام سفارشی برد';
  const revised={...before,stages:[{...before.stages[0],label:'نام عمومی جدید'}]};
  const after=propagateAddedWorkspaceStages(before,revised,'w');
  assert.equal(after.boards[0].stages[0].label,'نام عمومی جدید');
  assert.equal(after.boards[1].stages[0].label,'نام سفارشی برد');
  assert.strictEqual(after.tasks,before.tasks);
});
test('workspace stage addition fails closed if any active board is already full',()=>{
  const before=makeState();
  before.boards[1].stages=Array.from({length:40},(_,i)=>stage('b'+i));
  assert.strictEqual(propagateAddedWorkspaceStages(before,{...before,stages:[...before.stages,stage('new')]},'w'),before);
});
test('new card target chooses a board that actually contains the clicked list',()=>{
  const boardA={id:'a',projectId:'p',stages:[stage('inbox')]};
  const boardB={id:'b',projectId:'p',stages:[stage('inbox'),stage('new')]};
  assert.equal(boardForColumn([boardA,boardB],'p','new','a')?.id,'b');
  assert.equal(boardForColumn([boardA,boardB],'p','inbox','a')?.id,'a');
});
