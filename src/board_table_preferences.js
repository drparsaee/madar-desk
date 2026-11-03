/**
 * Presentation-only preferences, isolated per authenticated user and board.
 * These never enter the shared task state or accounting ledger.
 */
const MODES = new Set(['board', 'list', 'table']);
const DEFAULTS = [
  {id:'title',label:'عنوان کارت',width:260},
  {id:'stage',label:'لیست',width:150},
  {id:'priority',label:'اولویت',width:125},
  {id:'due',label:'موعد',width:145},
  {id:'project',label:'پروژه',width:155},
  {id:'completed',label:'وضعیت انجام',width:130},
];
const safePart=value=>encodeURIComponent(String(value||'local').slice(0,180));
const prefKey=(identity,scopeId)=>'madar-board-view-v1:'+safePart(identity)+':'+safePart(scopeId);
export const MIN_TABLE_WIDTH=88;
export const MAX_TABLE_WIDTH=480;

export function boardTableColumns(board){
  const used=new Set(DEFAULTS.map(column=>column.id));
  const columns=DEFAULTS.map(column=>({...column}));
  for(const field of board?.customFields||[]){
    if(typeof field?.id!=='string'||!field.id||!['text','number','date','checkbox','select'].includes(field.type))continue;
    const id='custom:'+field.id;
    if(used.has(id))continue;
    used.add(id);
    columns.push({id,label:String(field.name||'فیلد سفارشی').slice(0,100),width:160,
      numeric:field.type==='number',field});
  }
  return columns;
}

export function normalizeBoardViewPreferences(value,columns){
  const existing=Array.isArray(value?.columns)?value.columns:[];
  const allowed=new Map(columns.map(column=>[column.id,column]));
  const ordered=[];
  for(const saved of existing){
    if(!saved||typeof saved.id!=='string'||!allowed.has(saved.id)||ordered.some(x=>x.id===saved.id))continue;
    const width=Number.isInteger(saved.width)&&saved.width>=MIN_TABLE_WIDTH&&saved.width<=MAX_TABLE_WIDTH
      ?saved.width:allowed.get(saved.id).width;
    ordered.push({id:saved.id,width,visible:saved.id==='title'||saved.visible!==false});
  }
  for(const column of columns)if(!ordered.some(entry=>entry.id===column.id)){
    ordered.push({id:column.id,width:column.width,visible:true});
  }
  // Keep the primary accessible card opener available even for corrupt storage.
  const title=ordered.find(entry=>entry.id==='title');
  if(title)title.visible=true;
  return {mode:MODES.has(value?.mode)?value.mode:'board',columns:ordered};
}

export function readBoardViewPreferences(storage,identity,scopeId,columns=boardTableColumns(null)){
  try{
    const raw=storage?.getItem(prefKey(identity,scopeId));
    return normalizeBoardViewPreferences(raw?JSON.parse(raw):null,columns);
  }catch{return normalizeBoardViewPreferences(null,columns);}
}

export function saveBoardViewPreferences(storage,identity,scopeId,patch,columns=boardTableColumns(null)){
  const previous=readBoardViewPreferences(storage,identity,scopeId,columns);
  const next=normalizeBoardViewPreferences({...previous,...patch},columns);
  try{storage?.setItem(prefKey(identity,scopeId),JSON.stringify(next));}catch{}
  return next;
}

/** Sum only custom numeric data with exact decimal representation (up to six places).
 * The source of truth stays on the card; built-in money fields are deliberately
 * excluded because legacy units and task visibility differ from the ledger.
 */
export function safeNumericAggregate(tasks,fieldId){
  let count=0, precision=0;
  const entries=[];
  for(const task of tasks){
    const value=task?.customFieldValues?.[fieldId];
    if(value===null||value===undefined||value==='')continue;
    if(typeof value!=='number'||!Number.isFinite(value))return {status:'unsafe',count:0};
    const literal=String(value);
    if(!/^-?(?:0|[1-9]\d*)(?:\.\d{1,6})?$/.test(literal))return {status:'unsafe',count:0};
    const decimals=literal.split('.')[1]?.length||0;
    precision=Math.max(precision,decimals);
    entries.push(literal);
    count++;
  }
  if(!count)return {status:'empty',count:0};
  let sum=0n;
  const max=BigInt(Number.MAX_SAFE_INTEGER);
  for(const literal of entries){
    const negative=literal.startsWith('-');
    const normalized=negative?literal.slice(1):literal;
    const [integer,decimal='']=normalized.split('.');
    const scaled=BigInt(integer+decimal.padEnd(precision,'0'))*(negative?-1n:1n);
    if(scaled>max||scaled< -max)return {status:'unsafe',count:0};
    sum+=scaled;
    if(sum>max||sum< -max)return {status:'unsafe',count:0};
  }
  const negative=sum<0n;
  const absolute=(negative?-sum:sum).toString().padStart(precision+1,'0');
  const integer=absolute.slice(0,absolute.length-precision||undefined);
  const decimal=precision?absolute.slice(-precision).replace(/0+$/,''):'';
  const format=new Intl.NumberFormat('fa-IR',{useGrouping:true,maximumFractionDigits:0});
  return {status:'ok',count,value:(negative?'-':'')+format.format(Number(integer))+
    (decimal?'٫'+decimal.replace(/\d/g,d=>'۰۱۲۳۴۵۶۷۸۹'[Number(d)]):'')};
}
