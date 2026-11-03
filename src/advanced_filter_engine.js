// A small, independently authored predicate tree for Madar task filters.
// The application intersects its result with the already authorized board cards.
export const FILTER_LIMITS=Object.freeze({depth:3,nodes:32,children:8,text:120});
export const FILTER_FIELDS=Object.freeze(['priority','member','label','status','due','attachments','title']);

const groupOps=new Set(['and','or']);
const ordinaryOps=new Set(['is','isNot']);
const textOps=new Set(['contains','notContains']);
const dueValues=new Set(['today','overdue','unset']);
const attachmentValues=new Set(['yes','no']);

export function validateFilterTree(tree,{allowEmptyText=false}={}){
 if(tree===null||tree===undefined)return {valid:true,nodes:0,error:''};
 if(!tree||typeof tree!=='object'||Array.isArray(tree))return {valid:false,nodes:0,error:'ساختار فیلتر معتبر نیست.'};
 const seen=new Set(),stack=[{node:tree,depth:0}],max=FILTER_LIMITS;
 let nodes=0;
 while(stack.length){
   const {node,depth}=stack.pop();
   if(!node||typeof node!=='object'||Array.isArray(node)||seen.has(node))return {valid:false,nodes,error:'ساختار تکراری یا نامعتبر است.'};
   seen.add(node);nodes++;
   if(nodes>max.nodes)return {valid:false,nodes,error:`حداکثر ${max.nodes} بخش برای فیلتر مجاز است.`};
   if(depth>max.depth)return {valid:false,nodes,error:`حداکثر ${max.depth} سطح تو در تو مجاز است.`};
   const keys=Object.keys(node);
   if(Object.prototype.hasOwnProperty.call(node,'op')){
     if(!groupOps.has(node.op)||!Array.isArray(node.children)||node.children.length>max.children||
         keys.some(key=>key!=='op'&&key!=='children')||
         (depth>0&&!node.children.length))return {valid:false,nodes,error:'گروه شرط‌ها معتبر نیست.'};
     for(let i=node.children.length-1;i>=0;i--)stack.push({node:node.children[i],depth:depth+1});
   }else{
     if(depth===0||!FILTER_FIELDS.includes(node.field)||keys.some(key=>!['field','comparison','value'].includes(key))||
         typeof node.value!=='string'||node.value.length>max.text||(!node.value.trim()&&!(allowEmptyText&&node.field==='title')))return {valid:false,nodes,error:'شرط فیلتر معتبر نیست.'};
     if(node.field==='title'){
       if(!textOps.has(node.comparison))return {valid:false,nodes,error:'عملگر متن نامعتبر است.'};
     }else if(!ordinaryOps.has(node.comparison))return {valid:false,nodes,error:'عملگر شرط نامعتبر است.'};
     if(node.field==='due'&&!dueValues.has(node.value))return {valid:false,nodes,error:'سررسید نامعتبر است.'};
     if(node.field==='attachments'&&!attachmentValues.has(node.value))return {valid:false,nodes,error:'وضعیت پیوست نامعتبر است.'};
   }
 }
 return {valid:true,nodes,error:''};
}

function hasAttachment(task){return Boolean((task?.fileLinks||[]).length||(task?.attachments||[]).length);}
function dateKey(date){
 const p=n=>String(n).padStart(2,'0');
 return `${date.getFullYear()}-${p(date.getMonth()+1)}-${p(date.getDate())}`;
}
function ruleMatches(task,rule,boardId,today){
 const {field,value,comparison}=rule;
 if(field==='title'){
   const contains=String(task?.title||'').toLocaleLowerCase().includes(value.trim().toLocaleLowerCase());
   return comparison==='contains'?contains:!contains;
 }
 let matches=false;
 switch(field){
   case 'priority':matches=task?.priority===value;break;
   case 'member':matches=Array.isArray(task?.assignees)&&task.assignees.includes(value);break;
   case 'label':matches=Array.isArray(task?.labels)&&task.labels.some(label=>(typeof label==='string'?label:label?.name)===value);break;
   case 'status':matches=(boardId&&task?.boardId===boardId?(task.listId||task.status):task?.status)===value;break;
   case 'attachments':matches=hasAttachment(task)===(value==='yes');break;
   case 'due':{
     const due=typeof task?.dueDate==='string'?task.dueDate.slice(0,10):'';
     matches=value==='unset'?!due:value==='today'?due===today:!!due&&due<today;
     break;
   }
 }
 return comparison==='is'?matches:!matches;
}

export function matchFilterTree(task,tree,boardId,today){
 if(tree===null||tree===undefined)return true;
 if(!validateFilterTree(tree).valid)return false; // Never ignore an invalid saved criterion.
 const todayKey=today??dateKey(new Date());
 function evaluate(node){
   if(!Object.prototype.hasOwnProperty.call(node,'op'))return ruleMatches(task,node,boardId,todayKey);
   return node.op==='and'?node.children.every(evaluate):node.children.some(evaluate);
 }
 return tree.children.length===0?true:evaluate(tree);
}
