/** Browser sends reference IDs only. Financial facts are resolved on the host.
 * No user-controlled actor, price, party or operational text leaves this path.
 */
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/;
const validId=v=>typeof v==='string'&&ID.test(v);

export async function prepareStandaloneFromTask(api,{task,expense=null}){
  if(typeof api?.standaloneAccountingPrepare!=='function')
    throw Error('مسیر آماده‌سازی حسابداری توسط میزبان فعال نیست.');
  if(!validId(task?.id)||(expense!==null&&!validId(expense?.id)))
    throw Error('شناسه تسک یا قلم هزینه معتبر نیست.');
  const result=await api.standaloneAccountingPrepare({
    taskId:task.id,expenseId:expense?.id??null});
  if(!result||!validId(result.id)||typeof result.existing!=='boolean')
    throw Error('پاسخ آماده‌سازی حسابداری معتبر نیست.');
  return result;
}
