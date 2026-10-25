/**
 * M-06: immutable, opt-in card dependency graph. Every dependency points from
 * the dependent card to a predecessor that must be completed first.
 * This module never changes money, invoice, audit, dueDate, or card ordering.
 */
export const MAX_DEPENDENCY_EDGES=200_000;
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
function validId(id) {
  return typeof id==='string'&&id.length>0&&id.length<=2048&&!/[\x00-\x1f\x7f]/.test(id);
}
export function dependencyGraph(tasks) {
  if(!Array.isArray(tasks)||tasks.length>20000)throw Error('Invalid card set');
  const byId=new Map(),successors=new Map(),inDegree=new Map();
  for(const t of tasks){
    if(!t||!validId(t.id)||byId.has(t.id))throw Error('Invalid or repeated card id');
    byId.set(t.id,t);successors.set(t.id,[]);inDegree.set(t.id,0);
  }
  let edges=0;
  for(const t of tasks){
    const deps=own(t,'dependencies')?t.dependencies:[];
    if(!Array.isArray(deps)||deps.length>128)throw Error('Invalid dependency list');
    const seen=new Set();
    for(const id of deps){
      if(!validId(id)||id===t.id||seen.has(id))throw Error('Invalid or repeated dependency');
      seen.add(id);
      const pred=byId.get(id);
      if(!pred||pred.projectId!==t.projectId||pred.deleted===true||t.deleted===true)throw Error('Dependency must target an accessible active card in same project');
      successors.get(id).push(t.id);
      inDegree.set(t.id,inDegree.get(t.id)+1);
      if(++edges>MAX_DEPENDENCY_EDGES)throw Error('Dependency graph exceeds edge budget');
    }
  }
  const queue=[];
  for(const [id,degree] of inDegree)if(!degree)queue.push(id);
  const order=[];
  for(let i=0;i<queue.length;i++){
    const id=queue[i];order.push(id);
    for(const next of successors.get(id)){
      const degree=inDegree.get(next)-1;
      inDegree.set(next,degree);
      if(!degree)queue.push(next);
    }
  }
  if(order.length!==tasks.length)throw Error('CONFLICT: dependency cycle detected');
  return {byId,successors,order,edges};
}
function permission(t,options){
  if(options?.canManage===true)return;
  if(options?.canEdit!==true||!Array.isArray(options.grantedProjectIds)||
     !options.grantedProjectIds.includes(t.projectId))throw Error('PERMISSION_DENIED');
}
export function addCardDependency(state,cardId,predecessorId,options={}){
  if(!state||!Array.isArray(state.tasks))throw Error('Invalid state');
  const graph=dependencyGraph(state.tasks);
  const card=graph.byId.get(cardId),pred=graph.byId.get(predecessorId);
  if(!card||!pred||cardId===predecessorId||card.projectId!==pred.projectId||
     card.deleted===true||pred.deleted===true||card.archived===true||pred.archived===true)
     throw Error('Invalid card dependency references');
  permission(card,options);
  const deps=card.dependencies||[];
  if(deps.includes(predecessorId))return state;
  const next={...state,tasks:state.tasks.map(t=>t.id===cardId?{...t,dependencies:[...deps,predecessorId]}:t)};
  dependencyGraph(next.tasks);
  return next;
}
export function removeCardDependency(state,cardId,predecessorId,options={}){
  if(!state||!Array.isArray(state.tasks))throw Error('Invalid state');
  const graph=dependencyGraph(state.tasks),card=graph.byId.get(cardId);
  if(!card)throw Error('Unknown card');
  permission(card,options);
  if(!(card.dependencies||[]).includes(predecessorId))return state;
  return {...state,tasks:state.tasks.map(t=>t.id===cardId?{...t,dependencies:t.dependencies.filter(id=>id!==predecessorId)}:t)};
}
export function cardBlockingStatus(tasks,cardId){
  const graph=dependencyGraph(tasks),card=graph.byId.get(cardId);
  if(!card)throw Error('Unknown card');
  const waiting=(card.dependencies||[]).filter(id=>{
    const predecessor=graph.byId.get(id);
    return predecessor?.status!=='done'&&predecessor?.completed!==true;
  });
  return {blocked:waiting.length>0,blockingIds:waiting};
}
export function criticalDependencyPath(tasks){
  const graph=dependencyGraph(tasks);
  // Store predecessor pointers rather than copying every prefix array.
  // A dependency chain of 20k cards must not allocate O(n^2) path memory.
  const minutes=new Map(),previous=new Map();
  for(const id of graph.order){
    const task=graph.byId.get(id),duration=task.estimatedMinutes??0;
    if(!Number.isSafeInteger(duration)||duration<0||duration>5256000)throw Error('Invalid estimated minutes');
    let best=0,ancestor=null;
    for(const dependency of (task.dependencies||[])){
      if(minutes.get(dependency)>best){best=minutes.get(dependency);ancestor=dependency;}
    }
    minutes.set(id,best+duration);previous.set(id,ancestor);
  }
  let finish=null;
  for(const id of graph.order)if(finish===null||minutes.get(id)>minutes.get(finish))finish=id;
  const path=[];
  for(let id=finish;id!==null;id=previous.get(id)??null)path.push(id);
  path.reverse();
  return {minutes:finish===null?0:minutes.get(finish),cardIds:path};
}
