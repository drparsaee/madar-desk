const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('src/taskops.js','utf8').replace('export function','function');
const sandbox={module:{exports:{}},globalThis:{structuredClone}};
vm.runInNewContext(source+'\nmodule.exports={duplicateCard}',sandbox);
const {duplicateCard}=sandbox.module.exports;
const esbuild=require('esbuild');
const Module=require('node:module');
const {spawnSync}=require('node:child_process');
const boardBundle=esbuild.buildSync({entryPoints:['src/boardops.js'],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const boardLoader=new Module('src/boardops-test.cjs',module);
boardLoader.filename='src/boardops-test.cjs';boardLoader.paths=Module._nodeModulePaths(process.cwd());
boardLoader._compile(boardBundle,boardLoader.filename);
const {moveCardToBoard,boardStageUpdate,legacyStatusForStage,archiveBoardState,restoreBoardState,renameBoardState}=boardLoader.exports;
test('duplicate creates independent checklist IDs, resets money and reports',()=>{
 const src={id:'old',title:'a',projectId:'p',boardId:'b',cost:150,costEnabled:true,
  reports:[{id:'r'}],assignees:['member'],fileLinks:[{path:'UNC'}],attachments:[{id:'binary'}],
  checklist:[{id:'step',done:true,cost:100,text:'cut'}],
  checklists:[{id:'checklist-legacy',items:[{id:'step',done:true,cost:100}]},
              {id:'custom',items:[{id:'item',done:true,cost:300}]}],
  actualMinutes:90,dueDate:'2026-11-01'};
 let counter=0;
 const clone=duplicateCard(src,'fresh','2026-10-20',()=>('id-'+ ++counter));
 assert.equal(clone.cost,0);
 assert.equal(clone.costEnabled,null);
 assert.deepEqual(JSON.parse(JSON.stringify(clone.reports)),[]);
 assert.deepEqual(JSON.parse(JSON.stringify(clone.attachments)),[]);
 assert.notEqual(clone.checklist[0].id,src.checklist[0].id);
 assert.equal(clone.checklists[0].id,'checklist-legacy');
 assert.notEqual(clone.checklists[1].id,'custom');
 assert.notEqual(clone.checklists[1].items[0].id,'item');
 assert.equal(clone.checklists[1].items[0].done,false);
 assert.equal(clone.checklists[1].items[0].cost,0);
 clone.checklists[1].items[0].cost=999;
 assert.equal(src.checklists[1].items[0].cost,300);
 assert.equal(src.checklists[0].items[0].done,true);
});
test('board move resets board-scoped references and picks destination column',()=>{
 const source={id:'t1',projectId:'p',boardId:'a',listId:'old',status:'old',labelIds:['l1'],customFieldValues:{x:4},title:'keep'};
 const board={id:'b',projectId:'p',archived:false,stages:[{id:'new'}]};
 const globalStages=[{id:'inbox'}];
 const moved=moveCardToBoard(source,board,globalStages);
 assert.equal(moved.boardId,'b');assert.equal(moved.listId,'new');assert.equal(moved.status,'inbox');
 assert.deepEqual(moved.labelIds,[]);assert.deepEqual(moved.customFieldValues,{});
 assert.equal(moved.title,'keep');assert.equal(source.boardId,'a');
 assert.throws(()=>moveCardToBoard(source,{...board,projectId:'other'}));
 assert.throws(()=>moveCardToBoard(source,{...board,archived:true}));
});
test('board-local columns keep legacy status valid on two different boards and pass native validation',()=>{
 const stages=[{id:'inbox',label:'Inbox',subtitle:'',color:'#888'}];
 const makeStage=(id,label)=>({id,label,subtitle:'',color:'#888'});
 const makeBoard=(id)=>({id,name:id,workspaceId:'w',projectId:'p',archived:false,
   stages:[makeStage(id+'-custom','Custom'),...stages],labelDefinitions:[],customFields:[]});
 const boardA=makeBoard('a'),boardB=makeBoard('b');
 const state={version:1,settings:{theme:'light',costDefault:false},stages,
   projects:[{id:'p',name:'Project',costEnabled:false,price:0,fileLinks:[]}],
   workspaces:[{id:'w',name:'Workspace',archived:false}],boards:[boardA,boardB],tasks:[]};
 const original={id:'t1',projectId:'p',boardId:'a',title:'Card',listId:'a-custom',
   status:legacyStatusForStage('a-custom',stages),priority:'medium',checklist:[],reports:[],labels:[]};
 assert.equal(original.status,'inbox');
 const snapshots=[];
 const first={...state,tasks:[original]};snapshots.push(first);
 const moved=moveCardToBoard(original,boardB,stages);
 assert.equal(moved.listId,'b-custom');assert.equal(moved.status,'inbox');
 const updated=boardStageUpdate(moved,boardB,stages,'inbox');
 assert.equal(updated.listId,'inbox');assert.equal(updated.status,'inbox');
 snapshots.push({...state,tasks:[moved]});
 const renamed=renameBoardState({...state,tasks:[moved]},'b','Board Two');
 const archived=archiveBoardState(renamed,'b');
 snapshots.push(renamed,archived,restoreBoardState(archived,'b'));
 const py=[
   'import json,sys,tempfile',
   'from pathlib import Path',
   'from unittest.mock import patch',
   'import native_app',
   'from data_model import normalize_plus',
   'states=json.load(sys.stdin)',
   'with tempfile.TemporaryDirectory(prefix="madar-board-test-") as temp:',
   '  with patch.object(native_app,"datadir",return_value=Path(temp)):',
   '    bridge=native_app.Bridge()',
   '    for state in states:',
   '      native_app.is_valid(state)',
   '      normalize_plus(state)',
   '      bridge.saveState(state)',
   '      stored=bridge.getState()',
   '      native_app.is_valid(stored)',
   '      assert len(stored["boards"])==2',
   '      assert stored["tasks"][0]["listId"]==state["tasks"][0]["listId"]',
   'print(len(states))',
 ].join('\n');
 const result=spawnSync('python',['-c',py],{cwd:process.cwd(),encoding:'utf8',input:JSON.stringify(snapshots)});
 assert.equal(result.status,0,(result.stderr||result.error?.message||'native validation failed'));
 assert.equal(result.stdout.trim(),String(snapshots.length));
});
test('archiving and restoring a board preserves previously archived cards',()=>{
 const state={boards:[{id:'a',name:'Original',archived:false}],tasks:[
   {id:'t1',boardId:'a',archived:false},{id:'t2',boardId:'a',archived:true},
   {id:'t3',boardId:'b',archived:false}]};
 const archived=archiveBoardState(state,'a');
 assert.equal(archived.boards[0].archived,true);
 assert.equal(archived.tasks[0].archivedByBoard,true);
 const restored=restoreBoardState(archived,'a');
 assert.equal(restored.boards[0].archived,false);
 assert.equal(restored.tasks[0].archived,false);
 assert.equal(restored.tasks[1].archived,true);
 assert.equal(restored.tasks[2].archived,false);
 assert.equal(state.boards[0].archived,false);
 const renamed=renameBoardState(restored,'a','  Renamed  ');
 assert.equal(renamed.boards[0].name,'Renamed');
 assert.throws(()=>renameBoardState(restored,'a','  '));
});
