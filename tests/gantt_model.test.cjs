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
const {dayNumber,dayString,ganttAxis,validPlan,validPlanningPatch,shiftPlan,barPosition,buildGanttRows,
  inspectGanttDependencies,analyzeCriticalPaths}=mod.exports;

test('partial card planning-date edits fail before autosave without breaking unrelated changes',()=>{
  const task={plannedStart:'2026-11-08',plannedEnd:'2026-11-12'};
  assert.equal(validPlanningPatch(task,{plannedStart:'2026-11-13'}),false);
  assert.equal(validPlanningPatch(task,{plannedEnd:'2026-11-07'}),false);
  assert.equal(validPlanningPatch(task,{plannedEnd:'2026-02-30'}),false);
  assert.equal(validPlanningPatch(task,{plannedStart:'2026-11-13',plannedEnd:'2026-11-15'}),true);
  assert.equal(validPlanningPatch(task,{plannedStart:''}),true);
  assert.equal(validPlanningPatch(task,{plannedEnd:''}),true);
  assert.equal(validPlanningPatch(task,{title:'Allowed title update'}),true);
  assert.equal(validPlanningPatch(task,{plannedStart:null}),false);
  assert.equal(validPlanningPatch(task,{plannedEnd:undefined}),false);
});

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

test('P2 Gantt identifies finish-to-start overlaps and suggests one-card safe date shift',()=>{
  const tasks=[
    {id:'a',title:'پیش‌نیاز',projectId:'p',plannedStart:'2026-11-07',plannedEnd:'2026-11-10'},
    {id:'b',title:'مرحله دو',projectId:'p',plannedStart:'2026-11-10',plannedEnd:'2026-11-12',dependencies:['a']},
    {id:'c',title:'مرحله سه',projectId:'p',plannedStart:'2026-11-13',plannedEnd:'2026-11-15',dependencies:['a']}
  ];
  const before=structuredClone(tasks);
  const result=inspectGanttDependencies(tasks);
  assert.equal(result.overlaps,1);
  assert.equal(result.conflictingCards,1);
  assert.equal(result.outsideView,0);
  assert.deepEqual(result.byTask.get('b').suggestion,
    {plannedStart:'2026-11-11',plannedEnd:'2026-11-13'});
  assert.equal(result.byTask.get('c').suggestion,null);
  assert.equal(result.byTask.get('b').conflicts[0].title,'پیش‌نیاز');
  assert.deepEqual(tasks,before);
});

test('P2 Gantt does not offer a misleading repair when predecessors are hidden or undated',()=>{
  const known={id:'a',title:'Safe',projectId:'p',plannedStart:'2026-11-05',plannedEnd:'2026-11-11'};
  const target={id:'b',title:'Target',projectId:'p',plannedStart:'2026-11-10',
    plannedEnd:'2026-11-12',dependencies:['a','hidden-id']};
  const partly=inspectGanttDependencies([known,target]);
  assert.equal(partly.overlaps,1);
  assert.equal(partly.outsideView,1);
  assert.equal(partly.byTask.get('b').hidden,1);
  assert.equal(partly.byTask.get('b').suggestion,null);
  const unknown=inspectGanttDependencies([{...known,plannedEnd:''},{...target,dependencies:['a']}]);
  assert.equal(unknown.unknownDates,1);
  assert.equal(unknown.overlaps,0);
  assert.equal(unknown.byTask.get('b').suggestion,null);
  const otherProject=inspectGanttDependencies([{...known,projectId:'else'},{...target,dependencies:['a']}]);
  assert.equal(otherProject.outsideView,1);
  assert.equal(otherProject.byTask.get('b').suggestion,null);
});

test('P2 Gantt disregards archived cards and duplicate legacy edges without mutating source',()=>{
  const prior={id:'a',projectId:'p',title:'Older',plannedStart:'0001-01-01',plannedEnd:'0001-01-02'};
  const target={id:'b',projectId:'p',title:'Next',plannedStart:'0001-01-02',
    plannedEnd:'0001-01-03',dependencies:['a','a']};
  const result=inspectGanttDependencies([prior,target,{...prior,id:'archived',archived:true}]);
  assert.equal(result.overlaps,1);
  assert.deepEqual(result.byTask.get('b').suggestion,
    {plannedStart:'0001-01-03',plannedEnd:'0001-01-04'});
  assert.equal(result.byTask.has('archived'),false);
  assert.deepEqual(target.dependencies,['a','a']);
});

test('P2 CPM identifies a longest dependency chain and the float on parallel work',()=>{
  const items=[
    {id:'a',projectId:'p',plannedStart:'2026-11-01',plannedEnd:'2026-11-03'},
    {id:'b',projectId:'p',plannedStart:'2026-11-04',plannedEnd:'2026-11-08',dependencies:['a']},
    {id:'c',projectId:'p',plannedStart:'2026-11-04',plannedEnd:'2026-11-05',dependencies:['a']},
    {id:'d',projectId:'p',plannedStart:'2026-11-09',plannedEnd:'2026-11-10',dependencies:['b','c']},
    {id:'e',projectId:'p',plannedStart:'2026-11-01',plannedEnd:'2026-11-02'}
  ];
  const snapshot=structuredClone(items);
  const result=analyzeCriticalPaths(items);
  assert.equal(result.complete,true);
  const project=result.projects[0];
  assert.equal(project.status,'ready');
  assert.equal(project.durationDays,10);
  assert.deepEqual(project.pathIds,['a','b','d']);
  assert.deepEqual(project.criticalIds,['a','b','d']);
  assert.equal(project.slackDays.get('c'),3);
  assert.equal(project.slackDays.get('e'),8);
  assert.deepEqual(items,snapshot);
});

test('P2 CPM is per project and never estimates through missing, hidden or invalid tasks',()=>{
  const card=(id,projectId,start='2026-11-01',end='2026-11-03',dependencies=[])=>({
    id,projectId,plannedStart:start,plannedEnd:end,dependencies});
  const analysis=analyzeCriticalPaths([
    card('a','public'),card('b','public','2026-11-04','2026-11-05',['a']),
    card('x','limited','2026-11-04','2026-11-05',['private-card']),
    card('y','undated','','',['x']),
    card('z','cycle','2026-11-01','2026-11-01',['zz']),
    card('zz','cycle','2026-11-01','2026-11-01',['z'])
  ]);
  assert.equal(analysis.complete,false);
  const per=new Map(analysis.projects.map(p=>[p.projectId,p]));
  assert.deepEqual(per.get('public').pathIds,['a','b']);
  assert.equal(per.get('limited').status,'partial');
  assert.equal(per.get('limited').reason,'outside_authorized_view');
  assert.equal(per.get('limited').pathIds.length,0);
  assert.equal(per.get('undated').status,'partial');
  assert.equal(per.get('cycle').status,'cycle');
  assert.deepEqual(per.get('cycle').criticalIds,[]);
  const hidden=analyzeCriticalPaths([card('b','public','2026-11-04','2026-11-05',['a'])]);
  assert.equal(hidden.projects[0].status,'partial');
  assert.equal(hidden.projects[0].durationDays,null);
});

test('P2 CPM handles early years, multiple equal paths and corrupted repeated edges',()=>{
  const t=(id,start,end,deps=[])=>({id,projectId:'p',
    plannedStart:start,plannedEnd:end,dependencies:deps});
  const tasks=[t('a','0001-01-01','0001-01-02'),
    t('b','0001-01-01','0001-01-02'),
    t('c','0001-01-03','0001-01-04',['a','b'])];
  const cp=analyzeCriticalPaths(tasks).projects[0];
  assert.equal(cp.durationDays,4);
  assert.deepEqual(cp.criticalIds,['a','b','c']);
  assert.deepEqual(cp.pathIds,['a','c']);
  assert.equal(cp.slackDays.get('a'),0);
  const invalid=analyzeCriticalPaths([...tasks.slice(0,2),{...tasks[2],dependencies:['a','a']}]);
  assert.equal(invalid.projects[0].status,'partial');
  assert.equal(invalid.projects[0].reason,'invalid_dependencies');
});

test('P2 CPM processes a long DAG iteratively and bounds unsupported cardinality',()=>{
  const tasks=Array.from({length:1200},(_,i)=>({id:'n'+i,projectId:'p',
    plannedStart:'2026-11-01',plannedEnd:'2026-11-01',
    dependencies:i?['n'+(i-1)]:[]}));
  const analysis=analyzeCriticalPaths(tasks);
  assert.equal(analysis.projects[0].status,'ready');
  assert.equal(analysis.projects[0].durationDays,1200);
  assert.equal(analysis.projects[0].pathIds.length,1200);
  assert.equal(analyzeCriticalPaths(tasks,200).projects[0].reason,'too_many');
});
