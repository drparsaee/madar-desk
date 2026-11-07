/** Safe, independent card duplication that preserves reusable instructions. */
export function duplicateCard(source, newId, timestamp, idFactory){
 if(!source||typeof source!=='object'||typeof idFactory!=='function')throw new Error('Invalid card');
 const copy=globalThis.structuredClone?globalThis.structuredClone(source):JSON.parse(JSON.stringify(source));
 // Clone reusable instructions, not the previous work's obligations or ledger.
 const cloneItem=item=>({...item,id:idFactory(),done:false,cost:0,expenseItems:[],
   assignees:[],dueDate:'',costCategory:'',costDate:''});
 copy.id=newId;
 copy.title=source.title+' (مشابه)';
 copy.createdAt=timestamp;
 copy.updatedAt=timestamp;
 copy.completed=false;
 copy.deleted=false;
 copy.deletedAt='';
 copy.cost=0;copy.costEnabled=null;
 copy.costCategory='';copy.costDate='';
 copy.saleUnitPrice=0;copy.salePartyId='';
 // A copied work template may not reuse an existing invoice or ledger source.
 for(const key of ['invoiceId','linkedFinanceIds','linkedPurchaseIds','financeSourceId',
   'purchaseId','saleId','purchaseSourceId','accountingEntryId'])delete copy[key];
 copy.assignees=[];copy.fileLinks=[];copy.attachments=[];
 copy.reports=[];copy.actualMinutes=0;copy.dueDate='';
 // Dependencies and scheduled dates belong to the original execution, not its template.
 copy.dependencies=[];copy.plannedStart='';copy.plannedEnd='';
 // A duplicate is a new active task, not another archived item, even when
 // its source was recovered from a historical archived list/card.
 copy.archived=false;copy.archivedByBoard=false;
 copy.checklist=(source.checklist||[]).map(cloneItem);
 copy.checklists=(source.checklists||[]).map(group=>({
  ...group,
  id:group.id==='checklist-legacy'?'checklist-legacy':idFactory(),
  items:(group.items||[]).map(cloneItem)
 }));
 // The legacy group and the flat checklist represent the same work items.
 const legacy=copy.checklists.find(group=>group.id==='checklist-legacy');
 if(legacy){
   if(Array.isArray(source.checklist)&&source.checklist.length)
     legacy.items=copy.checklist.map(item=>({...item}));
   else copy.checklist=legacy.items.map(item=>({...item}));
 }
 return copy;
}
