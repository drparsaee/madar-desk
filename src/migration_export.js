/**
 * Madar M-09: portable operational subset. No I/O, auth, ledger or blob access.
 * Caller owns authenticated snapshot, consent, file download and host storage.
 */
export const PORTABLE_FORMAT = 'madar-operational-portable';
export const PORTABLE_SCHEMA_VERSION = 1;
export const MAX_PORTABLE_BYTES = 12_000_000;

const DEFAULT_PRIORITIES = [
  {id:'low',label:'کم',color:'#94a3b8',effect:'none'},
  {id:'medium',label:'متوسط',color:'#628dde',effect:'none'},
  {id:'high',label:'بالا',color:'#eb6976',effect:'none'}
];
const LIMITS = {workspaces:100,projects:2000,boards:2000,tasks:20000,stages:40,
  labelDefinitions:200,checklist:300,checklists:30,items:300,labels:200,priorities:30,attachments:5000};
const isObject=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
const own=(x,k)=>Object.prototype.hasOwnProperty.call(x,k);
function fail(path,reason){throw new Error('M09 '+path+': '+reason);}
function object(x,path,strict,keys){
  if(!isObject(x))fail(path,'expected object');
  if(strict)for(const key of Object.keys(x))if(!keys.includes(key))fail(path,'unsupported field');
  return x;
}
function array(x,path,max){
  if(!Array.isArray(x)||x.length>max)fail(path,'invalid or oversized array');
  return x;
}
function string(x,path,max=300,allowEmpty=false){
  if(typeof x!=='string'||x.length>max||(!allowEmpty&&!x.trim())||/[\u0000-\u001f\u007f]/.test(x))
    fail(path,'invalid string');
  return x;
}
function multiLine(x,path,max=10000){
  if(typeof x!=='string'||x.length>max||/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(x))
    fail(path,'invalid text');
  return x;
}
function flag(x,path){if(typeof x!=='boolean')fail(path,'expected boolean');return x;}
function integer(x,path,min,max){
  if(!Number.isSafeInteger(x)||x<min||x>max)fail(path,'invalid integer');
  return x;
}
function optional(obj,key,path,fn,fallback){
  return own(obj,key)?fn(obj[key],path+'.'+key):fallback;
}
function records(items,path,max,project,strict){
  return array(items,path,max).map((item,i)=>project(item,path+'['+i+']',strict));
}
function unique(items,path){
  const found=new Set();
  for(const [index,item] of items.entries()){
    if(found.has(item.id))fail(path+'['+index+'].id','duplicate identifier');
    found.add(item.id);
  }
}
function sorted(records){return records.slice().sort((a,b)=>a.id<b.id?-1:a.id>b.id?1:0);}
function projectWorkspace(raw,path,strict){
  const x=object(raw,path,strict,['id','name','archived']);
  return {id:string(x.id,path+'.id',100),name:string(x.name,path+'.name',180),
    archived:optional(x,'archived',path,flag,false)};
}
function projectProject(raw,path,strict){
  const x=object(raw,path,strict,['id','name','color']);
  return {id:string(x.id,path+'.id',100),name:string(x.name,path+'.name',180,true),
    color:optional(x,'color',path,v=>string(v,path+'.color',80),'#64748b')};
}
function projectStage(raw,path,strict){
  const x=object(raw,path,strict,['id','label','subtitle','color','archived']);
  return {id:string(x.id,path+'.id',100),label:string(x.label,path+'.label',100),
    subtitle:optional(x,'subtitle',path,v=>string(v,path+'.subtitle',10000,true),''),
    color:optional(x,'color',path,v=>string(v,path+'.color',80,true),''),
    archived:optional(x,'archived',path,flag,false)};
}
function projectLabel(raw,path,strict){
  const x=object(raw,path,strict,['id','name','color']);
  return {id:string(x.id,path+'.id',100),name:string(x.name,path+'.name',100),
    color:optional(x,'color',path,v=>string(v,path+'.color',80),'#64748b')};
}
function projectBoard(raw,path,strict){
  const x=object(raw,path,strict,['id','workspaceId','projectId','name','color','archived','stages','labelDefinitions']);
  const result={id:string(x.id,path+'.id',100),
    workspaceId:string(x.workspaceId,path+'.workspaceId',100),
    projectId:x.projectId==null?null:string(x.projectId,path+'.projectId',100),
    name:string(x.name,path+'.name',180),
    color:optional(x,'color',path,v=>string(v,path+'.color',80,true),'#64748b'),
    archived:optional(x,'archived',path,flag,false),
    stages:records(x.stages,path+'.stages',LIMITS.stages,projectStage,strict),
    labelDefinitions:records(x.labelDefinitions??[],path+'.labelDefinitions',LIMITS.labelDefinitions,projectLabel,strict)};
  unique(result.stages,path+'.stages');unique(result.labelDefinitions,path+'.labelDefinitions');
  if(new Set(result.labelDefinitions.map(x=>x.name)).size!==result.labelDefinitions.length)
    fail(path+'.labelDefinitions','duplicate label names');
  if(!result.stages.length||result.stages.every(s=>s.archived))fail(path+'.stages','no active list');
  return result;
}
function projectCheckItem(raw,path,strict){
  const x=object(raw,path,strict,['id','text','done']);
  return {id:string(x.id,path+'.id',100),text:multiLine(x.text,path+'.text'),
    done:flag(x.done,path+'.done')};
}
function projectChecklist(raw,path,strict){
  const x=object(raw,path,strict,['id','name','items']);
  const items=records(x.items,path+'.items',LIMITS.items,projectCheckItem,strict);
  unique(items,path+'.items');
  return {id:string(x.id,path+'.id',100),name:string(x.name,path+'.name',180),items};
}
function projectPriority(raw,path,strict){
  const x=object(raw,path,strict,['id','label','color','effect']);
  const id=string(x.id,path+'.id',100),color=string(x.color,path+'.color',7);
  const effect=string(x.effect,path+'.effect',20);
  if(!/^(low|medium|high|p-[a-z0-9]{3,32})$/.test(id)||
    !/^#[a-fA-F0-9]{6}$/.test(color)||
    !['none','neon','shimmer','pulse','glow','solid'].includes(effect))
    fail(path,'invalid priority definition');
  return {id,label:string(x.label,path+'.label',60),color,effect};
}
function projectTask(raw,path,strict){
  const x=object(raw,path,strict,['id','projectId','boardId','listId','status','title','description',
    'priority','dueDate','labels','labelIds','checklist','checklists','archived','deleted',
    'cardOrder','estimatedMinutes','actualMinutes','createdAt','updatedAt',
    'dependencies','plannedStart','plannedEnd']);
  const list=records(x.checklist??[],path+'.checklist',LIMITS.checklist,projectCheckItem,strict);
  const groups=records(x.checklists??[],path+'.checklists',LIMITS.checklists,projectChecklist,strict);
  const labels=array(x.labels??[],path+'.labels',LIMITS.labels).map((v,i)=>string(v,path+'.labels['+i+']',100));
  const labelIds=array(x.labelIds??[],path+'.labelIds',LIMITS.labels).map((v,i)=>string(v,path+'.labelIds['+i+']',100));
  unique(groups,path+'.checklists');
  if(new Set(labelIds).size!==labelIds.length)fail(path+'.labelIds','duplicate label');
  return {id:string(x.id,path+'.id',100),projectId:string(x.projectId,path+'.projectId',100),
    boardId:string(x.boardId,path+'.boardId',100),listId:string(x.listId,path+'.listId',100),
    status:string(x.status,path+'.status',100),title:string(x.title,path+'.title',300,true),
    description:optional(x,'description',path,v=>multiLine(v,path+'.description'),''),
    priority:string(x.priority,path+'.priority',100),
    dueDate:optional(x,'dueDate',path,v=>string(v,path+'.dueDate',40,true),''),
    labels,labelIds,checklist:list,checklists:groups,
    archived:optional(x,'archived',path,flag,false),
    deleted:optional(x,'deleted',path,flag,false),
    cardOrder:optional(x,'cardOrder',path,v=>integer(v,path+'.cardOrder',0,1000000),0),
    estimatedMinutes:optional(x,'estimatedMinutes',path,v=>integer(v,path+'.estimatedMinutes',0,5256000),0),
    actualMinutes:optional(x,'actualMinutes',path,v=>integer(v,path+'.actualMinutes',0,5256000),0),
    createdAt:optional(x,'createdAt',path,v=>string(v,path+'.createdAt',100,true),''),
    updatedAt:optional(x,'updatedAt',path,v=>string(v,path+'.updatedAt',100,true),''),
    ...(own(x,'dependencies')?{dependencies:array(x.dependencies,path+'.dependencies',128)
      .map((value,i)=>string(value,path+'.dependencies['+i+']',100))}:{}),
    ...(own(x,'plannedStart')?{plannedStart:planDate(x.plannedStart,path+'.plannedStart')}:{}),
    ...(own(x,'plannedEnd')?{plannedEnd:planDate(x.plannedEnd,path+'.plannedEnd')}:{}),
  };
}
function planDate(value,path){
  if(value==='')return '';
  const text=string(value,path,10);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(text))fail(path,'expected ISO date');
  const [year,month,day]=text.split('-').map(Number);
  const stamp=new Date(Date.UTC(year,month-1,day));
  if(stamp.getUTCFullYear()!==year||stamp.getUTCMonth()!==month-1||
    stamp.getUTCDate()!==day)fail(path,'invalid calendar date');
  return text;
}
function projectAttachment(raw,path,strict){
  const x=object(raw,path,strict,['id','cardId','projectId','filename','mime','size','sha256']);
  // Content is not accepted even if the caller mislabeled a binary as metadata.
  for(const name of ['content','contentBase64','base64','data','bytes','blob','path'])
    if(own(x,name))fail(path,'attachment bytes or filesystem path are forbidden');
  const sha=string(x.sha256,path+'.sha256',64);
  if(!/^[a-f0-9]{64}$/.test(sha))fail(path+'.sha256','expected SHA-256');
  return {id:string(x.id,path+'.id',100),cardId:string(x.cardId,path+'.cardId',100),
    projectId:string(x.projectId,path+'.projectId',100),
    filename:string(x.filename,path+'.filename',180),
    mime:string(x.mime,path+'.mime',100),
    size:integer(x.size,path+'.size',1,4*1024*1024),sha256:sha};
}
function sourceData(state){
  object(state,'state',false,[]);
  byteLength(state);
  if(state.version!==1)fail('state.version','expected Madar state version 1');
  const data={
    stages:records(state.stages,'state.stages',LIMITS.stages,projectStage,false),
    priorityDefinitions:records(state.settings?.priorityDefinitions??DEFAULT_PRIORITIES,
      'state.settings.priorityDefinitions',LIMITS.priorities,projectPriority,false),
    workspaces:sorted(records(state.workspaces,'state.workspaces',LIMITS.workspaces,projectWorkspace,false)),
    projects:sorted(records(state.projects,'state.projects',LIMITS.projects,projectProject,false)),
    boards:sorted(records(state.boards,'state.boards',LIMITS.boards,projectBoard,false)),
    tasks:sorted(records(state.tasks,'state.tasks',LIMITS.tasks,projectTask,false))
  };
  checkReferences(data);
  return data;
}
function checkReferences(data){
  unique(data.stages,'data.stages');unique(data.priorityDefinitions,'data.priorityDefinitions');
  for(const key of ['workspaces','projects','boards','tasks'])unique(data[key],'data.'+key);
  if(!data.stages.length||data.stages.every(s=>s.archived))fail('data.stages','no active global stage');
  if(!data.workspaces.length||data.workspaces.every(w=>w.archived))fail('data.workspaces','no active workspace');
  const stageIds=new Set(data.stages.map(s=>s.id)),priorityIds=new Set(data.priorityDefinitions.map(p=>p.id));
  const workspaces=new Set(data.workspaces.map(w=>w.id)),projects=new Set(data.projects.map(p=>p.id));
  const boards=new Map(data.boards.map(b=>[b.id,b]));
  const taskById=new Map(data.tasks.map(t=>[t.id,t]));
  if(!['low','medium','high'].every(id=>priorityIds.has(id)))fail('data.priorityDefinitions','required default priorities missing');
  for(const board of data.boards){
    if(!workspaces.has(board.workspaceId)||board.projectId!==null&&!projects.has(board.projectId))
      fail('data.boards','orphan workspace or project');
  }
  for(const task of data.tasks){
    const board=boards.get(task.boardId);
    if(!board||!projects.has(task.projectId)||board.projectId!==null&&board.projectId!==task.projectId||
       !board.stages.some(s=>s.id===task.listId)||!stageIds.has(task.status)||
       !priorityIds.has(task.priority)||task.labelIds.some(id=>!board.labelDefinitions.some(l=>l.id===id)))
      fail('data.tasks','orphan project, board, list, global stage, priority or label');
    if(task.plannedStart&&task.plannedEnd&&task.plannedStart>task.plannedEnd)
      fail('data.tasks','start date is after end date');
    for(const dep of task.dependencies||[]){
      const predecessor=taskById.get(dep);
      if(dep===task.id||!predecessor||predecessor.projectId!==task.projectId||
        predecessor.deleted||task.deleted)
        fail('data.tasks.dependencies','invalid dependency reference');
    }
  }
  const visiting=new Set(),visited=new Set();
  for(const task of data.tasks){
    if(visited.has(task.id))continue;
    const stack=[[task.id,false]];
    while(stack.length){
      const [id,exit]=stack.pop();
      if(exit){visiting.delete(id);visited.add(id);continue;}
      if(visited.has(id))continue;
      if(visiting.has(id))fail('data.tasks.dependencies','dependency cycle');
      visiting.add(id);stack.push([id,true]);
      for(const dep of taskById.get(id).dependencies||[])stack.push([dep,false]);
    }
  }
}
function byteLength(value){
  let json;
  try{json=JSON.stringify(value);}catch{fail('payload','not JSON serializable');}
  if(typeof json!=='string')fail('payload','not JSON');
  const bytes=new TextEncoder().encode(json).byteLength;
  if(bytes>MAX_PORTABLE_BYTES)fail('payload','exceeds 12 MB bound');
  return bytes;
}
function nonZero(v){return v!==null&&v!==false&&v!==0&&v!==''&&(!Array.isArray(v)||v.length>0);}
const financialKey=/^(?:finance|financial|cost|costEnabled|price|budget|amount|balance|revenue|profit|ledger|invoice|invoices|accounting|contracts|expenses|payments|tax|sale|billing|cardCosts|outbox)$/i;
function hasFinancialData(source){
  // Inspect data shape, not free-form description text. This gate does not
  // claim that users cannot type confidential data into a title/description.
  const stack=[source],seen=new Set();let visited=0;
  while(stack.length){
    const item=stack.pop();
    if(!item||typeof item!=='object'||seen.has(item))continue;
    seen.add(item);
    if(++visited>150000)fail('state','too many nested records');
    for(const [key,value] of Object.entries(item)){
      if(financialKey.test(key)&&nonZero(value))return true;
      if(value&&typeof value==='object')stack.push(value);
    }
  }
  return false;
}
function omittedCount(source,clean){
  let count=0;
  if(Array.isArray(source)&&Array.isArray(clean)){
    const identified=source.every(x=>isObject(x)&&typeof x.id==='string')&&
      clean.every(x=>isObject(x)&&typeof x.id==='string');
    const byId=identified?new Map(clean.map(item=>[item.id,item])):null;
    for(let i=0;i<source.length;i++)
      count+=omittedCount(source[i],identified?byId.get(source[i].id):clean[i]);
  }else if(isObject(source)&&isObject(clean)){
    for(const key of Object.keys(source))count+=!own(clean,key)?1:omittedCount(source[key],clean[key]);
  }
  return count;
}
function lossReport(state,data,attachmentCount){
  const financePresent=hasFinancialData(state);
  const allowedRoot={version:1,projects:data.projects,boards:data.boards,
    workspaces:data.workspaces,tasks:data.tasks,stages:data.stages,
    settings:{priorityDefinitions:data.priorityDefinitions}};
  return {
    included:['global stages','priority definitions','workspaces','projects (non-financial)',
      'boards/lists/labels','tasks (non-financial)','checklists (without costs)','attachment reference manifest'],
    omitted:[
      {scope:'financial ledgers, amounts, costs, pricing, invoices and approvals',
        presence:financePresent?'present':'not-detected'},
      {scope:'users, roles, credentials, connection settings and authentication',
        presence:'not-inspected'},
      {scope:'attachment file bytes and Windows shared file links',
        presence:'not-inspected'},
      {scope:'reports, comments, activity, custom fields, templates, automations and extensions',
        presence:'not-inspected'}
    ],
    excludedPropertyOccurrences:omittedCount(state,allowedRoot),
    attachmentsListed:attachmentCount,
    sourceCounts:{workspaces:data.workspaces.length,projects:data.projects.length,
      boards:data.boards.length,tasks:data.tasks.length},
    financialDataPresent:financePresent,
    separateFinanceBackupRequired:financePresent,
    separateAttachmentBackupRequired:true,
    textFieldsMayContainPrivateContent:true
  };
}
function attachmentManifest(items,data){
  const source=records(items,'attachmentManifest',LIMITS.attachments,projectAttachment,false);
  unique(source,'attachmentManifest');
  const cards=new Map(data.tasks.map(t=>[t.id,t]));
  for(const entry of source){
    if(!cards.has(entry.cardId)||cards.get(entry.cardId).projectId!==entry.projectId)
      fail('attachmentManifest','attachment points outside exported cards');
  }
  return sorted(source);
}
/** Inspect exclusion consequences without making a downloadable payload. */
export function previewPortableExport(state,{attachmentManifest:items=[]}={}){
  const data=sourceData(state);
  const manifest=attachmentManifest(items,data);
  return lossReport(state,data,manifest.length);
}
/** Explicit acknowledgment is required when financial state would be omitted. */
export function createPortableExport(state,{attachmentManifest:items=[],acknowledgeFinancialExclusion=false}={}){
  const data=sourceData(state),manifest=attachmentManifest(items,data);
  const loss=lossReport(state,data,manifest.length);
  if(loss.financialDataPresent&&acknowledgeFinancialExclusion!==true)
    fail('finance','financial data exists; explicit acknowledgement of exclusion and separate backup are required');
  const result={
    format:PORTABLE_FORMAT,schemaVersion:PORTABLE_SCHEMA_VERSION,sourceModelVersion:1,
    scope:'operational-subset',data,
    attachments:{containsBinaries:false,metadataCoverage:manifest.length?'caller-provided':'not-collected',
      manifest},
    lossReport:loss
  };
  byteLength(result);
  return result;
}
/** Defensive parser: refuses unknown fields, invalid references and changed schema. */
export function inspectPortableExport(raw){
  if(typeof raw==='string'){
    if(new TextEncoder().encode(raw).byteLength>MAX_PORTABLE_BYTES)fail('payload','exceeds 12 MB bound');
    try{raw=JSON.parse(raw);}catch{fail('payload','invalid JSON');}
  }
  byteLength(raw);
  const x=object(raw,'payload',true,['format','schemaVersion','sourceModelVersion','scope','data','attachments','lossReport']);
  if(x.format!==PORTABLE_FORMAT||x.schemaVersion!==1||x.sourceModelVersion!==1||
     x.scope!=='operational-subset')fail('payload','unsupported portable version or scope');
  const input=object(x.data,'data',true,['stages','priorityDefinitions','workspaces','projects','boards','tasks']);
  const data={
    stages:records(input.stages,'data.stages',LIMITS.stages,projectStage,true),
    priorityDefinitions:records(input.priorityDefinitions,'data.priorityDefinitions',LIMITS.priorities,projectPriority,true),
    workspaces:records(input.workspaces,'data.workspaces',LIMITS.workspaces,projectWorkspace,true),
    projects:records(input.projects,'data.projects',LIMITS.projects,projectProject,true),
    boards:records(input.boards,'data.boards',LIMITS.boards,projectBoard,true),
    tasks:records(input.tasks,'data.tasks',LIMITS.tasks,projectTask,true)
  };
  checkReferences(data);
  const attachments=object(x.attachments,'attachments',true,['containsBinaries','metadataCoverage','manifest']);
  if(attachments.containsBinaries!==false||!['not-collected','caller-provided'].includes(attachments.metadataCoverage))
    fail('attachments','binaries or unknown coverage mode');
  const manifest=attachmentManifest(attachments.manifest,data);
  if(!manifest.length&&attachments.metadataCoverage!=='not-collected'||
     manifest.length&&attachments.metadataCoverage!=='caller-provided')
    fail('attachments','coverage inconsistent with manifest');
  const loss=object(x.lossReport,'lossReport',true,
    ['included','omitted','excludedPropertyOccurrences','attachmentsListed','sourceCounts',
      'financialDataPresent','separateFinanceBackupRequired','separateAttachmentBackupRequired',
      'textFieldsMayContainPrivateContent']);
  const expectedIncluded=['global stages','priority definitions','workspaces',
    'projects (non-financial)','boards/lists/labels','tasks (non-financial)',
    'checklists (without costs)','attachment reference manifest'];
  if(!Array.isArray(loss.included)||loss.included.length!==expectedIncluded.length||
     loss.included.some((part,i)=>part!==expectedIncluded[i])||
     !Array.isArray(loss.omitted)||loss.omitted.length!==4||
     loss.attachmentsListed!==manifest.length||loss.textFieldsMayContainPrivateContent!==true||
     loss.separateAttachmentBackupRequired!==true||
     typeof loss.financialDataPresent!=='boolean'||
     loss.separateFinanceBackupRequired!==loss.financialDataPresent)
    fail('lossReport','required omission disclosure missing or inconsistent');
  const expectedScopes=[
    'financial ledgers, amounts, costs, pricing, invoices and approvals',
    'users, roles, credentials, connection settings and authentication',
    'attachment file bytes and Windows shared file links',
    'reports, comments, activity, custom fields, templates, automations and extensions'
  ];
  loss.omitted.forEach((entry,i)=>{
    object(entry,'lossReport.omitted['+i+']',true,['scope','presence']);
    if(entry.scope!==expectedScopes[i]||
       entry.presence!==(i===0?(loss.financialDataPresent?'present':'not-detected'):'not-inspected'))
      fail('lossReport','unsupported omission disclosure');
  });
  const counts=object(loss.sourceCounts,'lossReport.sourceCounts',true,
    ['workspaces','projects','boards','tasks']);
  for(const key of Object.keys(counts))if(counts[key]!==data[key].length)fail('lossReport','source count mismatch');
  integer(loss.excludedPropertyOccurrences,'lossReport.excludedPropertyOccurrences',0,1000000);
  return {data,manifest,lossReport:loss,sourceCounts:counts};
}
/** Construct an isolated new version-1 state; NEVER overwrite a live state. */
export function importPortableSubset(raw){
  const {data}=inspectPortableExport(raw);
  return {version:1,
    stages:data.stages,workspaces:data.workspaces,
    projects:data.projects.map(p=>({...p,costEnabled:false,price:0,fileLinks:[]})),
    boards:data.boards.map(b=>({...b,customFields:[]})),
    tasks:data.tasks.map(t=>({...t,cost:0,costEnabled:false,assignees:[],
      fileLinks:[],reports:[],customFieldValues:{},
      checklist:t.checklist.map(item=>({...item,cost:0})),
      checklists:t.checklists.map(g=>({...g,items:g.items.map(item=>({...item,cost:0}))}))})),
    templates:[],settings:{theme:'light',costDefault:false,priorityDefinitions:data.priorityDefinitions}};
}
export function portableJson(bundle){
  inspectPortableExport(bundle);
  return JSON.stringify(bundle,null,2)+'\n';
}
function csvCell(value){
  let text=String(value??'');
  if(/^[\s\uFEFF]*[=+@-]/.test(text))text="'"+text;
  return '"'+text.replace(/"/g,'""')+'"';
}
/** CSV is a convenience view of tasks, NOT a lossless restore format. */
export function portableTasksCsv(bundle){
  const {data}=inspectPortableExport(bundle);
  const columns=['id','projectId','boardId','listId','status','title','description',
    'priority','dueDate','archived','deleted','cardOrder','labels'];
  return '\uFEFF'+columns.map(csvCell).join(',')+'\r\n'+data.tasks.map(task=>
    columns.map(key=>csvCell(key==='labels'?task.labels.join(' | '):task[key])).join(',')
  ).join('\r\n')+(data.tasks.length?'\r\n':'');
}
