const {test}=require('node:test'),a=require('node:assert/strict'),esbuild=require('esbuild');
const path=require('node:path');
const output=esbuild.buildSync({entryPoints:[path.join(__dirname,'../src/card_dependencies.js')],platform:'node',format:'cjs',bundle:true,write:false}).outputFiles[0].text;
const m={exports:{}};new Function('module','exports',output)(m,m.exports);
const {dependencyGraph,addCardDependency,removeCardDependency,cardBlockingStatus,criticalDependencyPath}=m.exports;
const fixture=()=>({tasks:[{id:'a',projectId:'p',status:'done',estimatedMinutes:20,cost:90},{id:'b',projectId:'p',status:'active',estimatedMinutes:30},{id:'c',projectId:'p',status:'active',estimatedMinutes:5}],finance:{invoice:'INV',ledger:[1,2]},attachments:[1]});
test('immutable predecessor creation, no finance, task cost or unrelated state mutations',()=>{
  const original=fixture(),next=addCardDependency(original,'b','a',{canManage:true});
  a.deepEqual(original.tasks[1].dependencies,undefined);a.deepEqual(next.tasks[1].dependencies,['a']);
  a.strictEqual(original.finance,next.finance);a.strictEqual(original.attachments,next.attachments);a.strictEqual(original.tasks[0],next.tasks[0]);
});
test('duplicate dependency idempotent',()=>{
  const original=fixture(),once=addCardDependency(original,'b','a',{canManage:true});
  a.strictEqual(addCardDependency(once,'b','a',{canManage:true}),once);
});
test('cycle denied without touching previous state',()=>{
  const first=addCardDependency(fixture(),'b','a',{canManage:true});
  a.throws(()=>addCardDependency(first,'a','b',{canManage:true}),/cycle/i);
  a.equal(first.tasks[0].dependencies,undefined);
});
test('self edge, missing ref and cross project forbidden',()=>{
  a.throws(()=>addCardDependency(fixture(),'a','a',{canManage:true}));
  a.throws(()=>addCardDependency(fixture(),'a','other',{canManage:true}));
  const s=fixture();s.tasks[2].projectId='other';
  a.throws(()=>addCardDependency(s,'a','c',{canManage:true}));
});
test('editor grant strictly scoped; viewer denied',()=>{
  a.throws(()=>addCardDependency(fixture(),'b','a',{canEdit:true}));
  a.throws(()=>addCardDependency(fixture(),'b','a',{canEdit:true,grantedProjectIds:['else']}));
  a.doesNotThrow(()=>addCardDependency(fixture(),'b','a',{canEdit:true,grantedProjectIds:['p']}));
});
test('deleted and archived card cannot be used in a new dependency',()=>{
  const s=fixture();s.tasks[0].deleted=true;
  a.throws(()=>addCardDependency(s,'b','a',{canManage:true}));
  s.tasks[0].deleted=false;s.tasks[0].archived=true;
  a.throws(()=>addCardDependency(s,'b','a',{canManage:true}));
});
test('blocked status tracks incomplete predecessors, never makes financial changes',()=>{
  const s=addCardDependency(fixture(),'b','a',{canManage:true});
  a.deepEqual(cardBlockingStatus(s.tasks,'b'),{blocked:false,blockingIds:[]});
  s.tasks[0].status='active';
  a.deepEqual(cardBlockingStatus(s.tasks,'b'),{blocked:true,blockingIds:['a']});
});
test('longest critical path uses estimatedMinutes without guessing',()=>{
  let s=fixture();
  s=addCardDependency(s,'b','a',{canManage:true});
  s=addCardDependency(s,'c','b',{canManage:true});
  a.deepEqual(criticalDependencyPath(s.tasks),{minutes:55,cardIds:['a','b','c']});
  s=removeCardDependency(s,'c','b',{canManage:true});
  a.deepEqual(s.tasks[2].dependencies,[]);
});
test('existing cycles and duplicate refs fail closed',()=>{
  const s=fixture();s.tasks[0].dependencies=['b'];s.tasks[1].dependencies=['a'];
  a.throws(()=>dependencyGraph(s.tasks),/cycle/);
  s.tasks[0].dependencies=['b','b'];a.throws(()=>dependencyGraph(s.tasks),/repeated/);
});
test('legacy tasks with no dependencies are valid; empty graph is safe',()=>{
  a.deepEqual(dependencyGraph([]).order,[]);
  a.deepEqual(criticalDependencyPath([]),{minutes:0,cardIds:[]});
  a.equal(dependencyGraph(fixture().tasks).edges,0);
});
