/**
 * Import one Notion table CSV into a NEW Madar project/board.
 * Independent implementation. No Focalboard source code or dependencies.
 * No file system, network, account, ledger or existing-record mutations.
 */
const MAX_BYTES=3*1024*1024;
const MAX_ROWS=2000;
const MAX_COLUMNS=50;
const clean=(s,max=180)=>String(s??'').replace(/[\u0000-\u001f\u007f]/g,' ').trim().slice(0,max);
const id=prefix=>prefix+Math.random().toString(36).slice(2,12)+Date.now().toString(36);
const palette=['#6286bd','#47a390','#ce9d52','#976eba','#bd7272','#688c9f'];
const NAME_KEYS=['name','title','نام','عنوان'];
const STAGE_KEYS=['status','group','state','وضعیت','مرحله','ستون'];
const DESC_KEYS=['description','details','توضیحات','شرح'];
const TAG_KEYS=['tags','tag','labels','برچسب','برچسب‌ها'];
const DATE_KEYS=['due','due date','date','deadline','موعد','تاریخ'];

function parseCsv(input){
  if(typeof input!=='string'||new TextEncoder().encode(input).length>MAX_BYTES)
    throw Error('فایل CSV نامعتبر یا بزرگ‌تر از سه مگابایت است.');
  const raw=input.replace(/^\uFEFF/,'');
  const rows=[];
  let row=[],field='',quotes=false,afterQuote=false;
  for(let i=0;i<raw.length;i++){
    const ch=raw[i];
    if(quotes){
      if(ch==='"'&&raw[i+1]==='"'){field+='"';i++;continue;}
      if(ch==='"'){quotes=false;afterQuote=true;continue;}
      field+=ch;
    }else if(ch===','||ch==='\r'||ch==='\n'){
      row.push(field);field='';afterQuote=false;
      if(ch!==','){
        if(ch==='\r'&&raw[i+1]==='\n')i++;
        rows.push(row);row=[];
        if(rows.length>MAX_ROWS+1)throw Error('تعداد ردیف‌های CSV بیش از حد مجاز است.');
      }
    }else if(ch==='"'&&!field&&!afterQuote){
      quotes=true;
    }else{
      if(afterQuote)throw Error('ساختار نقل‌قول‌های CSV نامعتبر است.');
      field+=ch;
    }
    if(field.length>12000)throw Error('یکی از خانه‌های CSV بیش از حد بلند است.');
  }
  if(quotes)throw Error('علامت نقل‌قول CSV بسته نشده است.');
  if(field||row.length){row.push(field);rows.push(row);}
  if(rows.length<2)throw Error('CSV باید عنوان ستون و حداقل یک کارت داشته باشد.');
  const header=rows.shift().map(s=>clean(s,100));
  if(header.length>MAX_COLUMNS||!header.length||header.some(x=>!x)||
    new Set(header.map(x=>x.toLocaleLowerCase())).size!==header.length)
    throw Error('عنوان ستون‌های CSV خالی، تکراری یا بیش از حد مجاز است.');
  if(rows.some(r=>r.length!==header.length))
    throw Error('تعداد ستون‌ها در یکی از ردیف‌های CSV یکسان نیست.');
  return {header,rows:rows.filter(r=>r.some(x=>x.trim()))};
}
function findField(header,keys){
  const index=header.findIndex(s=>keys.includes(s.toLocaleLowerCase()));
  return index;
}
const isoDate=value=>{
  const text=clean(value,80);
  if(!text)return '';
  const found=/\b(\d{4})-(\d{2})-(\d{2})\b/.exec(text);
  if(!found)return '';
  const str=found[0];
  const date=new Date(str+'T12:00:00Z');
  return Number.isNaN(date.getTime())||date.toISOString().slice(0,10)!==str?'':str;
};
function validateNotionCsv(raw){
  const {header,rows}=parseCsv(raw);
  const titleIndex=findField(header,NAME_KEYS);
  if(titleIndex<0)throw Error('ستون Name یا Title در خروجی Notion پیدا نشد.');
  if(rows.length>MAX_ROWS||!rows.length)throw Error('فایل CSV خالی یا بیش از حد مجاز است.');
  const statusIndex=findField(header,STAGE_KEYS);
  const descriptionIndex=findField(header,DESC_KEYS);
  const tagIndex=findField(header,TAG_KEYS);
  const dateIndex=findField(header,DATE_KEYS);
  const extras=header.map((name,index)=>({name,index}))
    .filter(x=>![titleIndex,statusIndex,descriptionIndex,tagIndex,dateIndex].includes(x.index))
    .slice(0,40);
  const stages=[...new Set(rows.map(row=>clean(statusIndex>=0?row[statusIndex]:'',100)||'بدون وضعیت'))];
  if(stages.length>40)throw Error('این فایل بیش از ۴۰ وضعیت متفاوت دارد.');
  for(const row of rows){
    if(!clean(row[titleIndex],300))throw Error('عنوان یک کارت در CSV خالی است.');
  }
  return {header,rows,titleIndex,statusIndex,descriptionIndex,tagIndex,dateIndex,extras,stages};
}
export function inspectNotionCsv(raw){
  const result=validateNotionCsv(raw);
  return {name:'Notion CSV',lists:result.stages.length,cards:result.rows.length,
    openCards:result.rows.length,properties:result.extras.length};
}
export function importNotionCsvBoard(state,raw){
  const x=validateNotionCsv(raw);
  if(!state||!Array.isArray(state.projects)||!Array.isArray(state.tasks))
    throw Error('وضعیت فعلی مدار برای واردکردن اطلاعات معتبر نیست.');
  const projectId=id('notion-project-'),boardId=id('notion-board-');
  const workspaceId=state.workspaces?.[0]?.id||'workspace-legacy';
  const status=state.stages?.[0]?.id||'inbox';
  const stages=x.stages.map((label,index)=>({
    id:id('notion-stage-'),label,subtitle:'',color:palette[index%palette.length]}));
  const stageMap=new Map(x.stages.map((label,index)=>[label,stages[index].id]));
  const customFields=x.extras.map(({name,index})=>({id:id('notion-field-'),name,type:'text',
    options:[],index}));
  const now=new Date().toISOString();
  const tasks=x.rows.map(row=>{
    const group=clean(x.statusIndex>=0?row[x.statusIndex]:'',100)||'بدون وضعیت';
    const labels=x.tagIndex<0?[]:clean(row[x.tagIndex],3000).split(/[,;]/)
      .map(text=>clean(text,100)).filter(Boolean).slice(0,100);
    const values={};
    for(const field of customFields){
      const value=clean(row[field.index],5000);
      if(value)values[field.id]=value;
    }
    return {id:id('notion-card-'),projectId,boardId,listId:stageMap.get(group),
      status,title:clean(row[x.titleIndex],300),
      description:x.descriptionIndex>=0?clean(row[x.descriptionIndex],5000):'',
      dueDate:x.dateIndex>=0?isoDate(row[x.dateIndex]):'',
      labels,customFieldValues:values,priority:'medium',
      checklist:[],reports:[],assignees:[],fileLinks:[],cost:0,costEnabled:false,
      createdAt:now,updatedAt:now};
  });
  const name='ورود اطلاعات Notion';
  const project={id:projectId,name,color:'#6286bd',costEnabled:false,price:0,fileLinks:[]};
  const board={id:boardId,projectId,workspaceId,name,color:project.color,
    archived:false,stages,labelDefinitions:[],
    customFields:customFields.map(({index,...field})=>field)};
  return {...state,projects:[...state.projects,project],
    boards:[...(state.boards||[]),board],tasks:[...tasks,...state.tasks]};
}
