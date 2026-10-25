const safe=(value,limit=180)=>typeof value==='string'?value.replace(/[\u0000-\u001f\u007f]/g,' ').trim().slice(0,limit):'';
const identifier=(prefix)=>prefix+Math.random().toString(36).slice(2,13)+Date.now().toString(36);
const defaultPalette=['#7893bb','#3f9b87','#be9850','#af77bb','#668e9d'];
export const inspectTrelloExport=raw=>{
  if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('ساختار فایل Trello معتبر نیست.');
  const lists=raw.lists,cards=raw.cards;
  if(!Array.isArray(lists)||!Array.isArray(cards)||lists.length>40||cards.length>2000){
    throw Error('فایل باید مجموعه فهرست‌ها و کارت‌های محدود Trello داشته باشد.');
  }
  if(!lists.length)throw Error('در فایل خروجی Trello هیچ ستونی پیدا نشد.');
  const ids=new Set();
  for(const list of lists){
    if(typeof list?.id!=='string'||!list.id||ids.has(list.id)||typeof list.name!=='string')throw Error('شناسه یا نام ستون معتبر نیست.');
    ids.add(list.id);
  }
  for(const card of cards){
    if(typeof card?.id!=='string'||typeof card.idList!=='string'||!ids.has(card.idList)||typeof card.name!=='string')throw Error('کارت ناشناخته یا نامعتبر در فایل وجود دارد.');
  }
  return {name:safe(raw.name)||'برد واردشده از Trello',lists:lists.length,cards:cards.length,openCards:cards.filter(c=>!c.closed).length};
};
export const importTrelloBoard=(state,raw)=>{
  const inspected=inspectTrelloExport(raw);
  const projectId=identifier('project-'),boardId=identifier('board-');
  const workspaces=Array.isArray(state.workspaces)?state.workspaces:[];
  const workspaceId=workspaces[0]?.id||'workspace-legacy';
  const listMap=new Map();
  const stages=raw.lists.filter(list=>!list.closed).map((list,index)=>{
    const stage={id:identifier('trello-list-'),label:safe(list.name,100)||`ستون ${index+1}`,subtitle:'',color:defaultPalette[index%defaultPalette.length]};
    listMap.set(list.id,stage.id);return stage;
  });
  if(!stages.length)throw Error('ستون بازی در فایل Trello وجود ندارد.');
  const fallback=stages[0].id;
  const globalStatus=state.stages?.[0]?.id||'inbox';
  const checks=new Map();
  if(Array.isArray(raw.checklists)){
    if(raw.checklists.length>2500)throw Error('تعداد چک‌لیست‌ها بیش از حد مجاز است.');
    for(const check of raw.checklists){
      if(!Array.isArray(check.checkItems))continue;
      checks.set(check.id,check);
    }
  }
  const labels=new Map((Array.isArray(raw.labels)?raw.labels.slice(0,300):[])
    .filter(x=>x&&typeof x.id==='string').map(x=>[x.id,safe(x.name,100)]));
  const tasks=raw.cards.filter(card=>!card.closed).map(card=>{
    const checklist=[];
    if(Array.isArray(card.idChecklists))for(const groupId of card.idChecklists.slice(0,30)){
      const group=checks.get(groupId);
      if(!group)continue;
      for(const item of group.checkItems.slice(0,300-checklist.length)){
        checklist.push({id:identifier('item-'),text:safe(item.name,300),done:item.state==='complete',cost:0});
      }
    }
    const stageId=listMap.get(card.idList)||fallback;
    const cardLabels=(Array.isArray(card.labels)?card.labels:[]).map(x=>safe(x.name,100)||labels.get(x.id)||'').filter(Boolean).slice(0,100);
    const date=typeof card.due==='string'&&/^\d{4}-\d\d-\d\d/.test(card.due)?card.due.slice(0,10):'';
    const now=new Date().toISOString();
    return {id:identifier('trello-card-'),projectId,boardId,listId:stageId,
      status:globalStatus,title:safe(card.name,300),description:safe(card.desc,5000),
      priority:'medium',dueDate:date,labels:cardLabels,checklist,reports:[],
      assignees:[],fileLinks:[],cost:0,costEnabled:false,createdAt:now,updatedAt:now};
  });
  const project={id:projectId,name:inspected.name,color:'#5d79bd',costEnabled:false,price:0,fileLinks:[]};
  const board={id:boardId,workspaceId,projectId,name:inspected.name,color:project.color,archived:false,
    stages,labelDefinitions:[],customFields:[]};
  return {...state,projects:[...state.projects,project],boards:[...(state.boards||[]),board],
    tasks:[...tasks,...state.tasks]};
};
