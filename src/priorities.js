export const DEFAULT_PRIORITIES = Object.freeze([
  {id:'low',label:'کم',color:'#94a3b8',effect:'none'},
  {id:'medium',label:'متوسط',color:'#628dde',effect:'none'},
  {id:'high',label:'بالا',color:'#eb6976',effect:'none'}
]);
export const PRIORITY_EFFECTS=[
  ['none','عادی'],['neon','نئون متحرک'],['shimmer','دورخط درخشان'],
  ['pulse','ضربان'],['glow','هاله نور'],['solid','پس‌زمینه رنگی']
];
export const isHexColor=value=>typeof value==='string'&&/^#[0-9a-f]{6}$/i.test(value);
export const priorityDefs=settings=>{
  const stored=settings?.priorityDefinitions;
  if(!Array.isArray(stored))return DEFAULT_PRIORITIES.map(item=>({...item}));
  const normalized=[];
  const seen=new Set();
  for(const value of stored){
    if(!value||typeof value!=='object'||typeof value.id!=='string'||seen.has(value.id))continue;
    if(!/^(low|medium|high|p-[a-z0-9]{3,32})$/.test(value.id))continue;
    if(normalized.length===30)break;
    seen.add(value.id);
    normalized.push({id:value.id,label:typeof value.label==='string'&&value.label.trim()?value.label.trim().slice(0,60):value.id,
      color:isHexColor(value.color)?value.color.toLowerCase():'#94a3b8',
      effect:PRIORITY_EFFECTS.some(([k])=>k===value.effect)?value.effect:'none'});
  }
  for(const base of DEFAULT_PRIORITIES)if(!seen.has(base.id))normalized.unshift({...base});
  return normalized;
};
export const priorityById=(definitions,id)=>definitions.find(value=>value.id===id)||DEFAULT_PRIORITIES.find(value=>value.id===id)||DEFAULT_PRIORITIES[1];
export const reorderStageArray=(stages,sourceId,targetId)=>{
  const a=stages.findIndex(item=>item.id===sourceId),b=stages.findIndex(item=>item.id===targetId);
  if(a<0||b<0||a===b)return stages;
  const next=[...stages];
  const [moved]=next.splice(a,1);
  next.splice(b,0,moved);
  return next;
};
