export function legacyStatusForStage(listId,globalStages=[]){
  if(globalStages.some(stage=>stage.id===listId))return listId;
  return globalStages.some(stage=>stage.id==='inbox')?'inbox':globalStages[0]?.id;
}

export function boardStageUpdate(task,board,globalStages,listId){
  if(!board?.stages?.some(stage=>stage.id===listId))throw new Error('مرحله مقصد در این برد وجود ندارد');
  const status=legacyStatusForStage(listId,globalStages);
  if(!status)throw new Error('برد فاقد مرحله عمومی معتبر است');
  return {...task,listId,status};
}

const normalizedName=value=>String(value||'').trim().toLocaleLowerCase();
function transferLabels(task,sourceBoard,destinationBoard){
  const originalIds=Array.isArray(task.labelIds)?task.labelIds:[];
  if(originalIds.length&&!sourceBoard)throw new Error('شناسهٔ برچسب مبدأ مشخص نیست؛ انتقال بدون حذف اطلاعات متوقف شد');
  const names=(Array.isArray(task.labels)?task.labels:[]).map(label=>
    typeof label==='string'?label:label?.name).filter(name=>typeof name==='string'&&name.trim());
  for(const id of originalIds){
    const definition=sourceBoard?.labelDefinitions?.find(label=>label.id===id);
    if(!definition)throw new Error('تعریف برچسب مبدأ یافت نشد؛ انتقال بدون حذف اطلاعات متوقف شد');
    if(!names.some(name=>normalizedName(name)===normalizedName(definition.name)))names.push(definition.name);
  }
 const sourceDefinitions=sourceBoard?.labelDefinitions||[];
 for(const id of originalIds){
   const original=sourceDefinitions.find(item=>item.id===id);
   if(sourceDefinitions.filter(item=>normalizedName(item.name)===normalizedName(original.name)).length!==1)
     throw new Error('نام برچسب مبدأ یکتا نیست؛ انتقال متوقف شد');
 }
  const labelIds=[];
  for(const name of names){
   const matches=(destinationBoard.labelDefinitions||[]).filter(item=>normalizedName(item.name)===normalizedName(name));
   if(matches.length>1)throw new Error('نام برچسب مقصد مبهم است؛ انتقال متوقف شد');
   const match=matches[0];
    if(match&&!labelIds.includes(match.id))labelIds.push(match.id);
  }
  return {labels:names,labelIds};
}

function compatibleFieldValues(task,sourceBoard,destinationBoard){
  const values=task.customFieldValues||{};
  const entries=Object.entries(values);
  if(!entries.length)return {};
  if(!sourceBoard)throw new Error('تعریف فیلدهای سفارشی مبدأ مشخص نیست؛ انتقال بدون حذف اطلاعات متوقف شد');
  const transferred={},used=new Set();
  for(const [id,value] of entries){
    const origin=sourceBoard.customFields?.find(field=>field.id===id);
    if(!origin)throw new Error('فیلد سفارشی مبدأ ناشناخته است؛ انتقال بدون حذف اطلاعات متوقف شد');
    const matches=(destinationBoard.customFields||[]).filter(field=>
      field.type===origin.type&&normalizedName(field.name)===normalizedName(origin.name));
    if(matches.length!==1){
      if(value===null||value===undefined)continue;
      throw new Error('فیلد «'+origin.name+'» در برد مقصد معادل یکتا ندارد؛ انتقال متوقف شد');
    }
    const target=matches[0];
    if(used.has(target.id))throw new Error('نگاشت فیلد سفارشی مقصد تکراری است');
    used.add(target.id);
    if(origin.type==='select'&&value!==null&&value!==undefined){
      const option=origin.options?.find(item=>item.id===value);
      const targets=(target.options||[]).filter(item=>
        normalizedName(item.label)===normalizedName(option?.label));
      if(!option||targets.length!==1)throw new Error('گزینهٔ فیلد «'+origin.name+'» در مقصد سازگار نیست؛ انتقال متوقف شد');
      transferred[target.id]=targets[0].id;
    }else transferred[target.id]=value;
  }
  return transferred;
}

/** Preserve matching board-local data; reject transfers that would erase user data. */
export function moveCardToBoard(task,board,globalStages,sourceBoard=null){
  if(!board||board.archived||board.projectId!==task.projectId||!board.stages?.length)
    throw new Error('برد مقصد معتبر نیست');
  if(task.boardId===board.id)return task;
  const available=board.stages.find(stage=>stage.archived!==true);
  if(!available)throw new Error('برد مقصد ستون فعال ندارد');
  const labels=transferLabels(task,sourceBoard,board);
  const customFieldValues=compatibleFieldValues(task,sourceBoard,board);
  return {...boardStageUpdate(task,board,globalStages,available.id),boardId:board.id,
    ...labels,customFieldValues};
}

export function archiveBoardState(state,id){
  const board=state.boards?.find(b=>b.id===id&&!b.archived);
  if(!board)return state;
  return {...state,boards:state.boards.map(b=>b.id===id?{...b,archived:true}:b),
    tasks:state.tasks.map(t=>t.boardId===id&&!t.archived?{...t,archived:true,archivedByBoard:true}:t)};
}

export function restoreBoardState(state,id){
  const board=state.boards?.find(b=>b.id===id&&b.archived);
  if(!board)return state;
  return {...state,boards:state.boards.map(b=>b.id===id?{...b,archived:false}:b),
    tasks:state.tasks.map(t=>t.boardId===id&&t.archivedByBoard?
      {...t,archived:false,archivedByBoard:false}:t)};
}

export function renameBoardState(state,id,name){
  const title=String(name||'').trim();
  if(!title||title.length>180)throw new Error('نام برد باید بین ۱ تا ۱۸۰ کاراکتر باشد');
  if(!state.boards?.some(b=>b.id===id))throw new Error('برد یافت نشد');
  return {...state,boards:state.boards.map(b=>b.id===id?{...b,name:title}:b)};
}
