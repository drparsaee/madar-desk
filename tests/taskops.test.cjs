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
test('duplicate does not silently carry over stale assignees and due dates on individual steps',()=>{
 const src={id:'old',title:'Synthetic',projectId:'p',boardId:'b',
   assignees:['old-owner'],dueDate:'2026-12-31',
   checklist:[{id:'one',text:'Check',done:true,assignees:['old-owner'],dueDate:'2026-12-30',cost:0}],
   checklists:[{id:'named',name:'QA',items:[{id:'two',text:'Review',done:true,
     assignees:['old-owner'],dueDate:'2026-12-29',expenseItems:[]}]}]};
 let n=0;const created=duplicateCard(src,'fresh','2026-11-05',()=>String(++n));
 for(const step of [...created.checklist,...created.checklists.flatMap(g=>g.items)]){
   assert.equal(step.assignees.length,0);
   assert.equal(step.dueDate,'');
   assert.equal(step.done,false);
 }
 assert.deepEqual(src.checklists[0].items[0].assignees,['old-owner']);
 assert.equal(src.checklists[0].items[0].dueDate,'2026-12-29');
});
test('paid, completed or deleted card duplicates as an independent uncompleted template',()=>{
 const src={id:'paid',title:'Paid',projectId:'p',boardId:'b',completed:true,deleted:true,
   deletedAt:'2026-11-03',invoiceId:'invoice-old',linkedFinanceIds:['f1'],
   cost:900,costCategory:'printing',costDate:'2026-10-03',
   checklist:[{id:'step',text:'Proof',done:true,cost:250,costCategory:'paper',
     costDate:'2026-10-03',expenseItems:[{id:'line-1'}]}],
   checklists:[{id:'checklist-legacy',name:'Checklist',items:[{id:'step',text:'Proof',done:true,cost:250}]}]};
 let count=0;const copy=duplicateCard(src,'new','2026-11-05',()=>`new-${++count}`);
 assert.equal(copy.completed,false);assert.equal(copy.deleted,false);
 assert.equal(copy.deletedAt,'');assert.equal(copy.cost,0);
 assert.equal(copy.costCategory,'');assert.equal(copy.costDate,'');
 assert.equal('invoiceId' in copy,false);assert.equal('linkedFinanceIds' in copy,false);
 assert.equal(copy.checklist[0].costCategory,'');
 assert.equal(copy.checklist[0].costDate,'');
 assert.equal(copy.checklist[0].expenseItems.length,0);
 assert.equal(copy.checklists[0].items[0].id,copy.checklist[0].id);
 assert.equal(copy.checklists[0].items[0].cost,0);
 assert.equal(src.completed,true);assert.equal(src.deleted,true);
});

test('duplicate does not inherit predecessor blockers or old Gantt schedule',()=>{
 const original={id:'old',title:'Scheduled',projectId:'p',boardId:'b',
   dependencies:['predecessor'],plannedStart:'2026-11-08',plannedEnd:'2026-11-12',
   checklist:[],checklists:[]};
 const copy=duplicateCard(original,'new','2026-11-07',()=> 'fresh-id');
 assert.deepEqual(Array.from(copy.dependencies),[]);
 assert.equal(copy.plannedStart,'');
 assert.equal(copy.plannedEnd,'');
 assert.deepEqual(original.dependencies,['predecessor']);
 assert.equal(original.plannedStart,'2026-11-08');
});

test('moving cards cannot silently discard custom field values or unknown board labels',()=>{
 const sourceBoard={id:'a',labelDefinitions:[{id:'l1',name:'چاپ',color:'#ff0000'}],
   customFields:[{id:'f1',name:'ضخامت',type:'number',options:[]}]};
 const destination={id:'b',projectId:'p',archived:false,stages:[{id:'new'}],
   labelDefinitions:[{id:'l2',name:'چاپ',color:'#ff0000'}],
   customFields:[{id:'f2',name:'ضخامت',type:'number',options:[]}]};
 const src={id:'c',projectId:'p',boardId:'a',listId:'old',status:'old',title:'Keep all',
   labelIds:['l1'],labels:['چاپ'],customFieldValues:{f1:1.2},cost:150,
   expenseItems:[{id:'financial-link'}]};
 const before=JSON.stringify(src);
 const moved=moveCardToBoard(src,destination,[{id:'inbox'}],sourceBoard);
 assert.deepEqual(moved.labelIds,['l2']);
 assert.deepEqual(moved.customFieldValues,{f2:1.2});
 assert.equal(moved.cost,150);
 assert.deepEqual(moved.expenseItems,src.expenseItems);
 assert.equal(JSON.stringify(src),before);
 assert.throws(()=>moveCardToBoard(src,{...destination,customFields:[]},[{id:'inbox'}],sourceBoard),/فیلد/);
 assert.throws(()=>moveCardToBoard(src,destination,[{id:'inbox'}]),/فیلد|برچسب/);
});
test('board move preserves compatible board references and picks destination column',()=>{
 const source={id:'t1',projectId:'p',boardId:'a',listId:'old',status:'old',labelIds:['l1'],labels:['چاپ'],customFieldValues:{x:4},title:'keep'};
 const from={id:'a',labelDefinitions:[{id:'l1',name:'چاپ'}],customFields:[{id:'x',name:'عدد',type:'number'}]};
 const board={id:'b',projectId:'p',archived:false,stages:[{id:'new'}],labelDefinitions:[{id:'l2',name:'چاپ'}],customFields:[{id:'y',name:'عدد',type:'number'}]};
 const globalStages=[{id:'inbox'}];
 const moved=moveCardToBoard(source,board,globalStages,from);
 assert.equal(moved.boardId,'b');assert.equal(moved.listId,'new');assert.equal(moved.status,'inbox');
 assert.deepEqual(moved.labelIds,['l2']);assert.deepEqual(moved.customFieldValues,{y:4});
 assert.equal(moved.title,'keep');assert.equal(source.boardId,'a');
 assert.throws(()=>moveCardToBoard(source,{...board,projectId:'other'},globalStages,from));
 assert.throws(()=>moveCardToBoard(source,{...board,archived:true},globalStages,from));
});
test('ambiguous label names and select option mapping fail closed',()=>{
 const task={id:'c',projectId:'p',boardId:'a',labelIds:['l1'],labels:[],
   customFieldValues:{choice:'src-option'}};
 const from={id:'a',labelDefinitions:[{id:'l1',name:'QC'}],
   customFields:[{id:'choice',name:'Finish',type:'select',options:[{id:'src-option',label:'Glossy'}]}]};
 const to={id:'b',projectId:'p',stages:[{id:'todo'}],
   labelDefinitions:[{id:'l2',name:'QC'}],
   customFields:[{id:'target-choice',name:'Finish',type:'select',options:[{id:'dst-option',label:'Glossy'}]}]};
 const mapped=moveCardToBoard(task,to,[{id:'inbox'}],from);
 assert.equal(mapped.customFieldValues['target-choice'],'dst-option');
 assert.deepEqual(mapped.labelIds,['l2']);
 assert.throws(()=>moveCardToBoard(task,{...to,labelDefinitions:[...to.labelDefinitions,
   {id:'l3',name:' qc '}]},[{id:'inbox'}],from),/برچسب مقصد مبهم/);
 assert.throws(()=>moveCardToBoard(task,to,[{id:'inbox'}],{...from,
   labelDefinitions:[...from.labelDefinitions,{id:'l4',name:' qc '}]}),/برچسب مبدأ یکتا/);
 assert.throws(()=>moveCardToBoard(task,{...to,customFields:[{...to.customFields[0],
   options:[{id:'a',label:'Glossy'},{id:'b',label:'glossy'}]}]},[{id:'inbox'}],from),/گزینه/);
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
