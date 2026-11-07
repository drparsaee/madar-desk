/**
 * M-02. UI-only sync signal. Never infer a successful host commit from a
 * locally saved draft. The host's CAS and outbox remain authoritative.
 */
export function syncHealth(status={}, {conflict=false, saving=false}={}) {
  const client=status?.mode==='client';
  if (status?.localOnly===true && status?.pending!==true)
    return {kind:'local',label:'ذخیرهٔ محلی فعال',pending:false};
  if (status?.localOnly===true && status?.pending===true)
    return {kind:'pending',label:'تغییرات محلی آمادهٔ اتصال',pending:true};
  if (conflict === true) {
    return {kind:'conflict', label:'تداخل ذخیره · نیازمند بررسی', pending:true};
  }
  if (status?.pending===true) {
    return {kind:'pending',label:status?.connected===false?'تغییرات محلی در صف · سرور قطع':'تغییرات در انتظار تأیید سرور',pending:true};
  }
  if (saving===true) {
    return {kind:'saving',label:'در حال ذخیره · هنوز تأیید نشده',pending:true};
  }
  if (client && status?.connected!==true) {
    return {kind:'offline',label:'ارتباط سرور قطع · فقط اطلاعات ذخیره‌شده محلی',pending:false};
  }
  return client
    ?{kind:'synced',label:'همگام با سرور',pending:false}
    :{kind:'local',label:'اطلاعات محلی آماده',pending:false};
}
