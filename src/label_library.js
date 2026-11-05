// One shared catalogue, independent selection per card. Legacy task strings and
// per-board definitions remain readable without forcing labels onto other cards.
import {labelColor} from './boardplus.jsx';

const HEX=/^#[0-9a-f]{6}$/i;
const validColor=value=>typeof value==='string'&&HEX.test(value)?value.toLowerCase():null;
const labelName=value=>typeof value==='string'?value.trim():typeof value?.name==='string'?value.name.trim():'';
const cleanName=value=>labelName(value).slice(0,100);

export function sharedLabelLibrary(state){
  const entries=[],names=new Set(),ids=new Set();
  const add=(raw,color,id)=>{
    const name=cleanName(raw);
    if(!name||names.has(name)||entries.length>=200)return;
    names.add(name);
    let identifier=typeof id==='string'&&id.trim()&&!ids.has(id)?id:'legacy-label-'+entries.length;
    while(ids.has(identifier))identifier='legacy-label-'+(entries.length+ids.size);
    ids.add(identifier);
    entries.push({id:identifier,
      name,color:validColor(color)||labelColor(name)});
  };
  for(const item of state?.settings?.labelLibrary||[])add(item.name,item.color,item.id);
  for(const board of state?.boards||[])
    for(const item of board.labelDefinitions||[])add(item.name,item.color,item.id);
  for(const task of state?.tasks||[])
    for(const item of task.labels||[]) {
      const name=labelName(item);
      add(name,task.labelColors?.[name]||(typeof item==='object'?item.color:null));
    }
  return entries;
}

export function sharedLabelColor(library,name,legacyColors={}){
  const existing=library.find(item=>item.name===name);
  return validColor(existing?.color)||validColor(legacyColors?.[name])||labelColor(name);
}

// Pure atomic state operation, safe to call inside React's functional updater.
// Global catalogue edits never add selections to unrelated cards.
export function editSharedLabelState(state,command,idFactory=()=> 'label-'+Math.random().toString(36).slice(2)+Date.now().toString(36)){
  const library=sharedLabelLibrary(state);
  const name=cleanName(command?.name);
  const existing=library.find(item=>item.id===command?.id);
  const action=command?.action;
  if(action==='create'){
    if(!name||name.length>100||library.some(item=>item.name===name)||library.length>=200)
      throw Error('نام برچسب خالی، تکراری یا کتابخانه پر است.');
    const color=validColor(command.color);
    if(!color)throw Error('رنگ برچسب معتبر نیست.');
    const id=idFactory();
    if(typeof id!=='string'||!id.trim()||library.some(item=>item.id===id))
      throw Error('شناسه برچسب معتبر نیست.');
    return {...state,settings:{...state.settings,labelLibrary:[...library,{id,name,color}]}};
  }
  if(!existing)throw Error('برچسب موردنظر در کتابخانه وجود ندارد.');
  if(action==='toggle'){
    const task=state.tasks.find(item=>item.id===command.taskId&&item.deleted!==true);
    if(!task)throw Error('کارت موردنظر پیدا نشد.');
    const selected=Array.isArray(task.labels)?task.labels.map(labelName).filter(Boolean):[];
    const active=selected.includes(existing.name);
    if(active===Boolean(command.selected))return state;
    const labels=active?selected.filter(value=>value!==existing.name):[...selected,existing.name];
    if(labels.length>200)throw Error('تعداد برچسب‌های کارت بیش از حد مجاز است.');
    const board=state.boards?.find(item=>item.id===task.boardId);
    const boardDefinition=board?.labelDefinitions?.find(item=>item.name===existing.name);
    const ids=Array.isArray(task.labelIds)?task.labelIds:[];
    const labelIds=boardDefinition?(active?ids.filter(id=>id!==boardDefinition.id):[...new Set([...ids,boardDefinition.id])]):ids;
    return {...state,tasks:state.tasks.map(item=>item.id===task.id?
      {...item,labels,labelIds,updatedAt:command.at||item.updatedAt}:item)};
  }
  if(action==='rename'||action==='color'||action==='edit'){
    const nextName=action==='rename'||action==='edit'?name:existing.name;
    const nextColor=action==='color'||action==='edit'?validColor(command.color):existing.color;
    if(!nextName||library.some(item=>item.id!==existing.id&&item.name===nextName)||!nextColor)
      throw Error('نام یا رنگ جدید معتبر نیست.');
    return {...state,
      settings:{...state.settings,labelLibrary:library.map(item=>item.id===existing.id?
        {...item,name:nextName,color:nextColor}:item)},
      boards:(state.boards||[]).map(board=>({
        ...board,labelDefinitions:(board.labelDefinitions||[]).map(item=>item.name===existing.name?
          {...item,name:nextName,color:nextColor}:item)
      })),
      tasks:state.tasks.map(task=>{
        const selected=Array.isArray(task.labels)?task.labels.map(labelName):[];
        if(!selected.includes(existing.name))return task;
        const colors={...(task.labelColors||{})};
        if(nextName!==existing.name)delete colors[existing.name];
        colors[nextName]=nextColor;
        return {...task,labels:selected.map(value=>value===existing.name?nextName:value),labelColors:colors};
      })};
  }
  throw Error('عملیات برچسب پشتیبانی نمی‌شود.');
}
