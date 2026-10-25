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

export function moveCardToBoard(task,board,globalStages){
  if(!board||board.archived||board.projectId!==task.projectId||!board.stages?.length)
    throw new Error('برد مقصد معتبر نیست');
  if(task.boardId===board.id)return task;
  const available=board.stages.find(stage=>stage.archived!==true);
  if(!available)throw new Error('برد مقصد ستون فعال ندارد');
  return {...boardStageUpdate(task,board,globalStages,available.id),boardId:board.id,
    labelIds:[],customFieldValues:{}};
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
