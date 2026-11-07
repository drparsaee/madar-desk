import React, {useState} from 'react';
import {Download, HardDriveDownload, Upload, X} from 'lucide-react';
import {decodeWebBackup, downloadWebBackup} from './web_storage.js';

// Local-only web backup UI. Never offers Drive/LAN/SQLite operations that the
// browser does not implement. User must explicitly select and confirm a file.
export function WebBackupDialog({api, state, onClose, onRestoreStart, onRestore, onRestoreFinished}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const exportJson = async () => {
    setBusy(true);setError('');setMessage('');
    try {
      downloadWebBackup(await api.webBackup());
      setMessage('فایل پشتیبان برای دریافت آماده شد. آن را خارج از مرورگر نگهدارید.');
    } catch (failure) { setError(failure.message || String(failure)); }
    finally { setBusy(false); }
  };
  const importJson = async event => {
    const file=event.target.files?.[0];
    event.target.value='';
    if (!file) return;
    setError('');setMessage('');setBusy(true);
    try {
      if (file.size > 16 * 1024 * 1024)
        throw Error('فایل بیش از حد مجاز است.');
      const replacement=decodeWebBackup(await file.text());
      if (!window.confirm('ورود فایل، تمام کارت‌ها و بردهای این مرورگر را جایگزین می‌کند. این داده‌ها آنلاین نیستند. ادامه؟'))return;
      // Initiate download before replacement. The browser, not the app,
      // controls whether the user actually retains the backup file.
      if ((state?.__localRevision || 0) > 0)
        downloadWebBackup(await api.webBackup());
      onRestoreStart();
      let outcome='failed';
      try {
        await api.webReplaceState(replacement, state?.__localRevision || 0);
        const refreshed=await api.getState();
        onRestore(refreshed);
        outcome='applied';
        setMessage('فایل پشتیبان بازیابی شد.');
      } finally { onRestoreFinished(outcome); }
    } catch (failure) { setError(failure.message || String(failure)); }
    finally { setBusy(false); }
  };
  return <div className="overlay" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose();}}>
    <section className="web-backup-dialog" role="dialog" aria-modal="true" aria-label="پشتیبان محلی نسخهٔ وب" dir="rtl">
      <header><h2><HardDriveDownload size={20}/> پشتیبان نسخهٔ وب مدار</h2><button type="button" aria-label="بستن پشتیبان" disabled={busy} onClick={onClose}><X size={19}/></button></header>
      <p>اطلاعات فعلاً فقط در حافظهٔ همین مرورگر است. پاک‌کردن داده‌های سایت یا تغییر دستگاه می‌تواند آن‌ها را از دسترس خارج کند. برای حفاظت، خروجی JSON را در محل دیگری نگهدارید.</p>
      <div className="web-backup-actions">
        <button type="button" disabled={busy} onClick={exportJson}><Download size={17}/> دریافت پشتیبان JSON</button>
        <label className="web-backup-import"><Upload size={17}/> ورود پشتیبان نسخهٔ وب
          <input type="file" accept=".json,application/json" aria-label="انتخاب پشتیبان نسخه وب" disabled={busy} onChange={importJson}/>
        </label>
      </div>
      {message&&<p role="status" className="web-backup-success">{message}</p>}
      {error&&<p role="alert" className="web-backup-error">{error}</p>}
      <small>اطلاعات حسابداری، فایل‌های پیوست، حساب‌های شبکه و اطلاعات نصب ویندوز در این نسخه منتقل نمی‌شوند.</small>
    </section>
  </div>;
}
