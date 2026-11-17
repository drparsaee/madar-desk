const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const code=esbuild.buildSync({
  entryPoints:[path.join(root,'src/migration_export.js')],
  platform:'node',format:'cjs',bundle:true,write:false
}).outputFiles[0].text;
const mod=new Module(path.join(root,'m09_bundle.cjs'),module);
mod.filename=path.join(root,'m09_bundle.cjs');
mod.paths=Module._nodeModulePaths(root);
mod._compile(code,mod.filename);
const {createPortableExport,previewPortableExport,inspectPortableExport,
  importPortableSubset,portableJson,portableTasksCsv}=mod.exports;

function fixture(){
  return {version:1,
    stages:[{id:'inbox',label:'Inbox',color:'#ccc'},{id:'done',label:'Done',color:'#fff'}],
    settings:{theme:'dark',googleClientId:'secret-client-id',password:'SECRET-SETTINGS',
      priorityDefinitions:[{id:'low',label:'Low',color:'#94a3b8',effect:'none'},
        {id:'medium',label:'Medium',color:'#628dde',effect:'none'},
        {id:'high',label:'High',color:'#eb6976',effect:'none'}]},
    workspaces:[{id:'w-2',name:'Two'},{id:'w-1',name:'One',archived:false}],
    projects:[{id:'p2',name:'Second',color:'#abc',price:0,costEnabled:false},
      {id:'p1',name:'First',color:'#def',price:0,costEnabled:false,
        fileLinks:[{id:'f1',path:'\\\\office\\share\\SECRET-PATH'}]}],
    boards:[{id:'b2',workspaceId:'w-2',projectId:'p2',name:'Second board',
      stages:[{id:'todo2',label:'To do'}],labelDefinitions:[]},
      {id:'b1',workspaceId:'w-1',projectId:'p1',name:'First board',
        stages:[{id:'todo',label:'To do'},{id:'completed',label:'Done'}],
        labelDefinitions:[{id:'lbl',name:'Important',color:'#eeeeee'}],
        customFields:[{id:'cost',name:'Sensitive custom field',type:'number'}]}],
    tasks:[{id:'t2',projectId:'p2',boardId:'b2',listId:'todo2',status:'inbox',
      title:'Tasks',priority:'medium',checklist:[],reports:[]},
      {id:'t1',projectId:'p1',boardId:'b1',listId:'completed',status:'done',
        title:'=1+2',description:'مرور توضیحات, "متن"\nLine 2',priority:'high',labels:['Important'],
        labelIds:['lbl'],checklist:[{id:'i1',text:'Check it',done:true,cost:0}],
        checklists:[{id:'cl1',name:'Checklist',items:[{id:'step1',text:'Substep',done:true,cost:0}]}],
        actualMinutes:30,cardOrder:5,archived:true,deleted:false,
        reports:[{id:'r1',summary:'SECRET-REPORT'}],fileLinks:[{path:'SECRET-UNC'}],
        assignees:['SECRET-USER'],customFieldValues:{cost:3333}}],
    templates:[{id:'tpl1',boardId:'b1',title:'SECRET-TEMPLATE'}],
    users:[{passwordHash:'SECRET-HASH'}],
    finance:{invoices:[]},integrationSecret:'SECRET-EXTENSION'};
}

test('preview discloses omitted scopes and blocks non-empty ledger without explicit acknowledgement',()=>{
  const state=fixture(),before=structuredClone(state);
  const loss=previewPortableExport(state);
  assert.equal(loss.financialDataPresent,true);
  assert(loss.excludedPropertyOccurrences>0);
  assert.equal(loss.sourceCounts.tasks,2);
  assert.equal(loss.separateFinanceBackupRequired,true);
  assert.throws(()=>createPortableExport(state),/finance.*acknowledgement/);
  assert.deepEqual(state,before);
});

test('only allowlisted operational data leaves the portable boundary and omission report is explicit',()=>{
  const exported=createPortableExport(fixture(),{acknowledgeFinancialExclusion:true});
  const text=portableJson(exported);
  for(const privateValue of ['SECRET-SETTINGS','SECRET-REPORT','SECRET-USER',
    'SECRET-PATH','SECRET-UNC','SECRET-HASH','SECRET-TEMPLATE','SECRET-EXTENSION','3333'])
    assert(!text.includes(privateValue),privateValue);
  assert.equal(exported.attachments.containsBinaries,false);
  assert.equal(exported.attachments.metadataCoverage,'not-collected');
  assert.equal(exported.lossReport.omitted.length,4);
  assert.equal(exported.data.boards[0].id,'b1');
  assert.equal(exported.data.projects[0].id,'p1');
  assert.equal(exported.data.tasks[0].title,'=1+2');
});

test('portable JSON byte-stable over repeated runs and safe reordering of identity collections',()=>{
  const source=fixture();
  const first=portableJson(createPortableExport(source,{acknowledgeFinancialExclusion:true}));
  const second=portableJson(createPortableExport(source,{acknowledgeFinancialExclusion:true}));
  assert.equal(first,second);
  const reordered=structuredClone(source);
  for(const k of ['projects','tasks','boards','workspaces'])reordered[k].reverse();
  assert.equal(portableJson(createPortableExport(reordered,{acknowledgeFinancialExclusion:true})),first);
});

test('round trip creates new safe independent model and validates against native additive model',()=>{
  const bundle=createPortableExport(fixture(),{acknowledgeFinancialExclusion:true});
  const restored=importPortableSubset(portableJson(bundle));
  assert.equal(restored.version,1);
  assert.equal(restored.tasks.length,2);
  assert.equal(restored.tasks[0].checklists[0].items[0].cost,0);
  assert.equal(restored.projects[0].price,0);
  assert.equal(restored.tasks[0].cardOrder,5);
  assert.equal(restored.tasks[0].archived,true);
  assert.equal(restored.settings.googleClientId,undefined);
  assert.equal(restored.finance,undefined);
  assert.deepEqual(createPortableExport(restored).data,bundle.data);
  const py='import json,sys;from data_model import validate_plus;validate_plus(json.load(sys.stdin));print("VALID_M09")';
  const checked=spawnSync('py',['-3.12','-c',py],{
    cwd:root,input:JSON.stringify(restored),encoding:'utf8',timeout:18000});
  assert.equal(checked.status,0,checked.stderr||checked.stdout);
  assert.match(checked.stdout,/VALID_M09/);
});
test('portable export preserves dependency DAG and planned dates but rejects corrupted graphs',()=>{
  const state=fixture();
  const older=state.tasks.find(t=>t.id==='t2'),newer=state.tasks.find(t=>t.id==='t1');
  Object.assign(older,{projectId:'p1',boardId:'b1',listId:'todo',
    plannedStart:'2026-11-08',plannedEnd:'2026-11-09'});
  Object.assign(newer,{plannedStart:'2026-11-10',plannedEnd:'2026-11-12',dependencies:['t2']});
  const bundle=createPortableExport(state,{acknowledgeFinancialExclusion:true});
  const imported=importPortableSubset(bundle);
  assert.deepEqual(imported.tasks.find(t=>t.id==='t1').dependencies,['t2']);
  assert.equal(imported.tasks.find(t=>t.id==='t1').plannedStart,'2026-11-10');
  assert.equal(imported.tasks.find(t=>t.id==='t1').plannedEnd,'2026-11-12');
  assert.deepEqual(createPortableExport(imported).data,bundle.data);
  const cycle=structuredClone(state);
  cycle.tasks.find(t=>t.id==='t2').dependencies=['t1'];
  assert.throws(()=>createPortableExport(cycle,{acknowledgeFinancialExclusion:true}),/cycle/);
  const cross=structuredClone(state);
  cross.tasks.find(t=>t.id==='t2').projectId='p2';
  cross.tasks.find(t=>t.id==='t2').boardId='b2';
  cross.tasks.find(t=>t.id==='t2').listId='todo2';
  assert.throws(()=>createPortableExport(cross,{acknowledgeFinancialExclusion:true}),/dependency reference/);
  const invalidDate=structuredClone(state);
  invalidDate.tasks.find(t=>t.id==='t1').plannedEnd='2026-11-01';
  assert.throws(()=>createPortableExport(invalidDate,{acknowledgeFinancialExclusion:true}),/after end date/);
});

test('attachment manifest has metadata only and rejects binaries, incorrect associations, duplicates',()=>{
  const sha='a'.repeat(64),metadata={id:'att1',cardId:'t1',projectId:'p1',
    filename:'hello.pdf',mime:'application/pdf',size:42,sha256:sha,
    uploadedBy:'PRIVATE-UPLOADER',createdAt:'2026-10-21T10:00:00Z'};
  const options={acknowledgeFinancialExclusion:true,attachmentManifest:[metadata]};
  const bundle=createPortableExport(fixture(),options);
  const data=portableJson(bundle);
  assert.equal(bundle.attachments.metadataCoverage,'caller-provided');
  assert.equal(bundle.lossReport.attachmentsListed,1);
  assert(!data.includes('PRIVATE-UPLOADER'));
  assert.equal(inspectPortableExport(bundle).manifest[0].sha256,sha);
  assert.throws(()=>createPortableExport(fixture(),{...options,
    attachmentManifest:[{...metadata,contentBase64:'AQID'}]}),/forbidden/);
  assert.throws(()=>createPortableExport(fixture(),{...options,
    attachmentManifest:[{...metadata,cardId:'unknown'}]}),/outside exported/);
  assert.throws(()=>createPortableExport(fixture(),{...options,
    attachmentManifest:[metadata,metadata]}),/duplicate/);
});

test('parse fails closed on unknown versions, inserted sensitive keys, orphan references and hidden omissions',()=>{
  const initial=createPortableExport(fixture(),{acknowledgeFinancialExclusion:true});
  const malformed=[
    {...initial,schemaVersion:2},
    {...initial,unexpected:'password'},
    {...initial,data:{...initial.data,finance:{secret:'ledger'}}},
    {...initial,data:{...initial.data,tasks:[{...initial.data.tasks[0],cost:1234},initial.data.tasks[1]]}},
    {...initial,data:{...initial.data,tasks:[{...initial.data.tasks[0],listId:'unknown'},initial.data.tasks[1]]}},
    {...initial,lossReport:{...initial.lossReport,omitted:[]}},
    {...initial,lossReport:{...initial.lossReport,included:['financial ledger',...initial.lossReport.included.slice(1)]}},
    {...initial,data:{...initial.data,priorityDefinitions:[{...initial.data.priorityDefinitions[0],effect:'expression(alert(1))'},...initial.data.priorityDefinitions.slice(1)]}},
    {...initial,data:{...initial.data,boards:[{...initial.data.boards[0],
      labelDefinitions:[initial.data.boards[0].labelDefinitions[0],
        {...initial.data.boards[0].labelDefinitions[0],id:'clone-label'}]},initial.data.boards[1]]}},
    {...initial,attachments:{...initial.attachments,containsBinaries:true}},
    {...initial,attachments:{...initial.attachments,manifest:[{contentBase64:'AAAA'}]}},
  ];
  for(const bad of malformed)assert.throws(()=>inspectPortableExport(bad));
});

test('oversized names and non-serializable/circular source fail without truncation',()=>{
  const state=fixture();state.finance=undefined;state.tasks[0].description='x'.repeat(10001);
  assert.throws(()=>createPortableExport(state),/description/);
  const circular=fixture();circular.loop=circular;
  assert.throws(()=>createPortableExport(circular,{acknowledgeFinancialExclusion:true}));
});

test('CSV escapes quotes, embedded line breaks and formula leading characters',()=>{
  const bundle=createPortableExport(fixture(),{acknowledgeFinancialExclusion:true});
  const csv=portableTasksCsv(bundle);
  assert(csv.startsWith('\uFEFF'));
  assert(csv.includes('"\'=1+2"'));
  assert(csv.includes('""متن""'));
  assert(csv.includes('Line 2'));
  assert(!csv.includes('SECRET-REPORT'));
});
