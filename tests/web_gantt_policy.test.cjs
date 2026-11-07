const test=require('node:test');
const assert=require('node:assert/strict');
const {validateSnapshot,ValidationError}=require('../server/policy.cjs');
const stage={id:'todo',label:'Todo'};
function snapshot(){
  return {version:1,
    workspaces:[{id:'w',name:'Workspace'}],
    projects:[{id:'p',name:'Project'},{id:'q',name:'Secret'}],
    boards:[{id:'b',projectId:'p',workspaceId:'w',name:'Board',stages:[stage]},
      {id:'c',projectId:'q',workspaceId:'w',name:'Secret',stages:[stage]}],
    stages:[stage],
    tasks:[{id:'one',projectId:'p',boardId:'b',listId:'todo',title:'One',
      labels:[],checklist:[],plannedStart:'2026-11-08',plannedEnd:'2026-11-11'},
      {id:'two',projectId:'p',boardId:'b',listId:'todo',title:'Two',
        labels:[],checklist:[],dependencies:['one']}],
    settings:{theme:'light'}};
}
test('Gantt dates are optional but strictly verified when set',()=>{
  const state=snapshot();assert.equal(validateSnapshot(state),state);
  state.tasks[0].plannedEnd='2026-11-07';
  assert.throws(()=>validateSnapshot(state),ValidationError);
  state.tasks[0].plannedEnd='2026-02-30';
  assert.throws(()=>validateSnapshot(state),ValidationError);
  state.tasks[0].plannedEnd='0000-01-01';
  assert.throws(()=>validateSnapshot(state),ValidationError);
  state.tasks[0].plannedEnd='';
  assert.doesNotThrow(()=>validateSnapshot(state));
});
test('Web API rejects cross-project, duplicate and cyclic task dependencies',()=>{
  const state=snapshot();
  state.tasks[0].dependencies=['two'];
  assert.throws(()=>validateSnapshot(state),/dependency cycle/);
  state.tasks[0].dependencies=[];
  state.tasks[1].dependencies=['one','one'];
  assert.throws(()=>validateSnapshot(state),/invalid dependency/);
  state.tasks[1].dependencies=['one'];
  state.tasks.push({id:'three',projectId:'q',boardId:'c',listId:'todo',
    title:'Private',labels:[],checklist:[]});
  state.tasks[1].dependencies=['three'];
  assert.throws(()=>validateSnapshot(state),/invalid dependency/);
});
