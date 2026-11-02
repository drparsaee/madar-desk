/** Backups are partial by design; never label a failed tick successful. */
export function hostBackupHealth(status,isClient=false) {
  if(isClient)return {kind:'client',description:'پشتیبان‌گیری خودکار فقط روی رایانه میزبان انجام می‌شود.'};
  if(!status)return {kind:'unknown',description:'وضعیت پشتیبان میزبان دریافت نشده است.'};
  if(status.lastError)return {kind:'error',description:'خطای آخرین پشتیبان‌گیری میزبان: '+String(status.lastError)};
  if(!status.running)return {kind:'stopped',description:'پشتیبان‌گیری خودکار میزبان فعال نیست.'};
  if(status.lastSuccess)return {kind:'ok',description:'پشتیبان خودکار آخرین بار با موفقیت ساخته شد.'};
  return {kind:'pending',description:'زمان‌بند فعال است اما هنوز پشتیبان موفق ثبت نشده است.'};
}
