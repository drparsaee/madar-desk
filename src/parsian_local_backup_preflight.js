/**
 * Client-side media HEADER preflight. It never uploads or inspects business
 * records, and does not pretend that a SQL Server TAPE prefix is a valid BAK.
 */
export const MAX_LOCAL_BACKUP_BYTES = 50 * 1024 ** 3;
export const MIN_LOCAL_BACKUP_BYTES = 512;

export function classifyLocalParsianBackup({name, size, header}) {
  if (typeof name !== 'string' || !/\.bak$/i.test(name.trim())) {
    return {status:'invalid', message:'فایل انتخابی باید پسوند BAK داشته باشد.'};
  }
  if (!Number.isSafeInteger(size) || size < MIN_LOCAL_BACKUP_BYTES ||
      size > MAX_LOCAL_BACKUP_BYTES) {
    return {status:'invalid', message:'اندازه فایل برای بررسی اولیه معتبر نیست.'};
  }
  if (!(header instanceof Uint8Array) || header.length !== 16) {
    return {status:'invalid', message:'خواندن ۱۶ بایت ابتدایی فایل کامل نشد.'};
  }
  const signature = Array.from(header.slice(0, 4)).map(x => String.fromCharCode(x)).join('');
  if (signature !== 'TAPE') {
    return {status:'unknown', size, signature:'نامشخص',
      message:'امضای بکاپ SQL Server شناسایی نشد. هیچ اطلاعاتی منتقل نشده است.'};
  }
  return {status:'sqlserver-media', size, signature:'TAPE',
    message:'امضای رسانه بکاپ SQL Server شناسایی شد. صحت فایل، جداول و مبالغ هنوز بررسی نشده است؛ انتقال غیرفعال است.'};
}

export async function inspectBackupFileLocally(file) {
  if (!file || typeof file.slice !== 'function') {
    return {status:'invalid', message:'فایل معتبر برای بررسی انتخاب نشده است.'};
  }
  if (typeof file.name !== 'string' || !/\.bak$/i.test(file.name.trim()) ||
      !Number.isSafeInteger(file.size) || file.size < MIN_LOCAL_BACKUP_BYTES ||
      file.size > MAX_LOCAL_BACKUP_BYTES) {
    return classifyLocalParsianBackup({name:file.name,size:file.size,
      header:new Uint8Array(0)});
  }
  // File.slice(0,16) is a browser-local read. The file body is never read.
  const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  return classifyLocalParsianBackup({name:file.name,size:file.size,header:bytes});
}
