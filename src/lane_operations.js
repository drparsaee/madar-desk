import {getOrderedLaneCards, moveCardInState} from './cardorder.js';

const SORTS=new Set(['title','newest','oldest','due']);

/** Pure, board-scoped list actions. No financial field is ever projected. */
export function sortLaneState(state,boardId,listId,sortBy){
  if(!SORTS.has(sortBy))throw new RangeError('Unsupported list sort');
  const board=state?.boards?.find(item=>item.id===boardId&&!item.archived);
  if(!board?.stages?.some(stage=>stage.id===listId&&stage.archived!==true))
    throw new RangeError('List is not active in board');
  const lane=getOrderedLaneCards(state.tasks,boardId,listId).filter(t=>t.deleted!==true);
  const ordered=lane.map((card,index)=>({card,index})).sort((a,b)=>{
    let diff=0;
    if(sortBy==='title')diff=String(a.card.title||'').localeCompare(String(b.card.title||''),'fa');
    if(sortBy==='newest'||sortBy==='oldest'){
      diff=String(a.card.createdAt||'').localeCompare(String(b.card.createdAt||''));
      if(sortBy==='newest')diff=-diff;
    }
    if(sortBy==='due'){
      const aDate=a.card.dueDate||'9999-99-99';
      const bDate=b.card.dueDate||'9999-99-99';
      diff=String(aDate).localeCompare(String(bDate));
    }
    return diff||a.index-b.index;
  }).map(x=>x.card);
  let next=state;
  // Using the same native-compatible, validated mutation as manual drag/drop.
  for(const card of ordered)next=moveCardInState(next,{cardId:card.id,toBoardId:boardId,
    toListId:listId,placement:'end'});
  return next;
}

/** Explicit move of all visible active cards; no project/board changes. */
export function moveAllLaneCardsState(state,boardId,sourceListId,destinationListId){
  if(sourceListId===destinationListId)return state;
  const board=state?.boards?.find(item=>item.id===boardId&&!item.archived);
  if(!board?.stages?.some(stage=>stage.id===sourceListId&&stage.archived!==true)||
    !board.stages.some(stage=>stage.id===destinationListId&&stage.archived!==true))
    throw new RangeError('Source or destination list is unavailable');
  const items=getOrderedLaneCards(state.tasks,boardId,sourceListId).filter(t=>t.deleted!==true);
  let next=state;
  for(const item of items)next=moveCardInState(next,{cardId:item.id,toBoardId:boardId,
    toListId:destinationListId,placement:'end'});
  return next;
}
