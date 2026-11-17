import React, {useCallback, useEffect, useState} from 'react';
import {Cloud, CloudOff, Download, LogIn, LogOut, RefreshCw, ShieldCheck, X} from 'lucide-react';
import {WEB_API_BASE} from './web_api_client.mjs';
import {WEB_BACKUP_FORMAT, downloadWebBackup} from './web_storage.js';

const roleLabel = role => ({admin:'مدیر',editor:'ویرایشگر',viewer:'فقط مشاهده'})[role]||'کاربر';
const backupText = state => JSON.stringify({format:WEB_BACKUP_FORMAT,schema:1,
  exportedAt:new Date().toISOString(),state},null,2);

export function WebSyncDialog({api,storage,onClose,onSessionChange,onRemoteState}) {
  const [health,setHealth]=useState(null);
  const [session,setSession]=useState(null);
  const [syncState,setSyncState]=useState(null);
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState('');
  const [error,setError]=useState('');

  const refresh=useCallback(async()=>{
    const nextHealth=await api.webHealth();
    setHealth(nextHealth);
    const nextSession=await api.webSession();
    setSession(nextSession);
    setSyncState(await storage.readSyncState());
    return {health:nextHealth,session:nextSession};
  },[api,storage]);

  useEffect(()=>{
    let live=true;
    setBusy(true);
    refresh().then(()=>onSessionChange?.()).catch(failure=>{
      if(live)setError(failure.message||String(failure));
    }).finally(()=>{if(live)setBusy(false);});
    return()=>{live=false;};
  },[refresh]);

  useEffect(()=>{
    // Background/other-tab sync can finish while this dialog is open. Its
    // journal is authoritative; do not leave a detected conflict hidden until
    // a user manually refreshes the account dialog.
    let live=true;
    const signature=value=>[
      value?.workspaceId,value?.remoteRevision,value?.remoteEtag,
      value?.inFlight?.id,value?.pending?.id,value?.pending?.localRevision,
      value?.conflict?.createdAt,value?.conflict?.localRevision,
      value?.lastError?.at,
    ].join('|');
    const poll=async()=>{
      try{
        const next=await storage.readSyncState();
        if(live)setSyncState(previous=>signature(previous)===signature(next)?previous:next);
      }catch{/* Keep the currently displayed state until storage recovers. */}
    };
    const timer=setInterval(poll,1200);
    return()=>{live=false;clearInterval(timer);};
  },[storage]);

  const login=async event=>{
    event.preventDefault();setBusy(true);setError('');setMessage('');
    try{
      const user=await api.webLogin(username,password);
      setSession(user);setPassword('');
      await onSessionChange?.();
      await refresh();
      setMessage('ورود انجام شد. داده‌های این دستگاه هنوز خودکار روی سرور جایگزین نشده‌اند.');
    }catch(failure){setError(failure.message||String(failure));}
    finally{setBusy(false);}
  };

  const logout=async()=>{
    setBusy(true);setError('');setMessage('');
    try{
      await api.webLogout();
      setSession(null);
      await onSessionChange?.();
      await refresh();
      setMessage('از حساب خارج شدید. اطلاعات محلی این مرورگر باقی مانده است.');
    }catch(failure){setError(failure.message||String(failure));}
    finally{setBusy(false);}
  };

  const sync=async()=>{
    setBusy(true);setError('');setMessage('');
    try{
      let result=await api.webSyncNow(false);
      if(result.kind==='bootstrap_required'){
        if(!window.confirm('حساب سرور خالی است. تمام فضای کاری فعلی این دستگاه به‌عنوان نسخهٔ اولیه ارسال می‌شود. این کار فقط پس از تأیید شما انجام می‌شود. ادامه؟'))return;
        result=await api.webSyncNow(true);
      }
      if(result.kind==='conflict')setMessage('تعارض نسخه پیدا شد. هیچ‌کدام از دو نسخه حذف یا بازنویسی نشده‌اند.');
      else if(result.kind==='pending')setMessage('تغییرات محلی محفوظ‌اند؛ ارسال هنوز تأیید نشده و برای تلاش بعدی در صف می‌مانند.');
      else setMessage(result.processed?'همگام‌سازی سرور تأیید شد.':'نسخهٔ سرور و این دستگاه همگام هستند.');
      await refresh();
      await onSessionChange?.();
    }catch(failure){setError(failure.message||String(failure));}
    finally{setBusy(false);}
  };

  const resolve=async choice=>{
    const conflict=syncState?.conflict;
    if(!conflict)return;
    setBusy(true);setError('');setMessage('');
    try{
      if(choice==='remote'){
        downloadWebBackup(backupText(conflict.localSnapshot));
        if(!window.confirm('ابتدا خروجی نسخهٔ محلی برای دانلود آماده شد. نسخهٔ سرور جایگزین داده‌های محلی این مرورگر شود؟'))return;
        if(onRemoteState)await onRemoteState(()=>storage.resolveConflict('remote'));
        else await storage.resolveConflict('remote');
        setMessage('نسخهٔ سرور پذیرفته شد؛ خروجی محلی نیز برای نگهداری آماده شد.');
      }else{
        downloadWebBackup(backupText(conflict.remoteSnapshot));
        if(!window.confirm('ابتدا خروجی نسخهٔ سرور برای دانلود آماده شد. نسخهٔ محلی جایگزین نسخهٔ فعلی سرور شود؟ این انتخاب ممکن است تغییرات دیگران را کنار بزند. ادامه؟'))return;
        await storage.resolveConflict('local');
        const result=await api.webSyncNow(false);
        if(result.kind==='conflict')setMessage('تعارض تازه‌ای رخ داده؛ هر دو نسخه همچنان محفوظ‌اند.');
        else if(result.kind==='pending')setMessage('نسخهٔ محلی محفوظ است و ارسال آن در صف باقی مانده است.');
        else setMessage('نسخهٔ محلی با تأیید سرور جایگزین شد.');
      }
      await refresh();
      await onSessionChange?.();
    }catch(failure){setError(failure.message||String(failure));}
    finally{setBusy(false);}
  };

  const status=syncState?.conflict?'تعارض نیازمند انتخاب':
    syncState?.inFlight||syncState?.pending?'تغییرات در صف ارسال':
    syncState?.remoteRevision?'دارای نسخهٔ مرجع سرور':'هنوز متصل نشده';

  return <div className="overlay" role="presentation" onMouseDown={event=>{
    if(event.target===event.currentTarget&&!busy)onClose();
  }}>
    <section className="web-sync-dialog" role="dialog" aria-modal="true"
      aria-label="اتصال آنلاین مدار" dir="rtl">
      <header>
        <div className="web-sync-dialog__title"><Cloud size={20}/><div>
          <h2>اتصال آنلاین مدار</h2><small>حساب کاربری و همگام‌سازی فضای کاری</small>
        </div></div>
        <button type="button" aria-label="بستن اتصال آنلاین" disabled={busy} onClick={onClose}><X size={19}/></button>
      </header>

      {!health?<div className="web-sync-empty">
        <CloudOff size={27}/>
        <strong>زیرساخت سرور هنوز در دسترس نیست</strong>
        <p>وب‌سرور باید API نسخهٔ ۱ مدار را روی همین دامنه و مسیر زیر ارائه کند:</p>
        <code dir="ltr">{WEB_API_BASE}</code>
        <small>تا آن زمان ذخیره‌سازی محلی فعال است و هیچ اطلاعاتی به آدرس دیگری ارسال نمی‌شود.</small>
        <button type="button" className="web-sync-secondary" disabled={busy} onClick={async()=>{
          setBusy(true);setError('');try{await refresh();}catch(failure){setError(failure.message||String(failure));}
          finally{setBusy(false);}
        }}><RefreshCw size={16}/> بررسی دوباره</button>
      </div>:!session?<form className="web-sync-login" onSubmit={login}>
        <div className="web-sync-secure"><ShieldCheck size={18}/>
          <span>اتصال فقط به API هم‌دامنه انجام می‌شود. رمز عبور در مرورگر ذخیره نمی‌شود.</span>
        </div>
        <label>نام کاربری
          <input autoComplete="username" maxLength={128} value={username}
            onChange={event=>setUsername(event.target.value)} required/>
        </label>
        <label>گذرواژه
          <input type="password" autoComplete="current-password" maxLength={1024}
            value={password} onChange={event=>setPassword(event.target.value)} required/>
        </label>
        <button type="submit" className="web-sync-primary" disabled={busy||!username.trim()||!password}>
          <LogIn size={17}/> ورود به حساب مدار
        </button>
      </form>:<div className="web-sync-account">
        <div className="web-sync-user">
          <div><strong>{session.displayName||session.username}</strong>
            <small>{session.username} · {roleLabel(session.role)}</small></div>
          <span>{status}</span>
        </div>
        {syncState?.lastError&&!syncState?.conflict&&<p className="web-sync-error" role="alert">
          {syncState.lastError.message||syncState.lastError.code}
        </p>}
        {syncState?.conflict?<div className="web-sync-conflict" role="alert">
          <strong>دو نسخهٔ متفاوت وجود دارد</strong>
          <p>نسخهٔ این دستگاه و نسخهٔ سرور جداگانه حفظ شده‌اند. هیچ ادغام یا بازنویسی خودکاری انجام نشده است.</p>
          <div className="web-sync-conflict__actions">
            <button type="button" disabled={busy} onClick={()=>resolve('remote')}>پذیرش نسخهٔ سرور</button>
            <button type="button" disabled={busy} onClick={()=>resolve('local')}>جایگزینی سرور با نسخهٔ محلی</button>
          </div>
        </div>:<div className="web-sync-info">
          <p>ذخیرهٔ محلی مستقل ادامه دارد. پس از اتصال اولیه، تغییرات بعدی با کنترل نسخه و کلید تکرار امن ارسال می‌شوند.</p>
          <button type="button" className="web-sync-primary" disabled={busy} onClick={sync}>
            <RefreshCw size={17}/> همگام‌سازی اکنون
          </button>
        </div>}
        <button type="button" className="web-sync-logout" disabled={busy} onClick={logout}>
          <LogOut size={16}/> خروج از حساب
        </button>
      </div>}
      {message&&<p className="web-sync-message" role="status">{message}</p>}
      {error&&<p className="web-sync-error" role="alert">{error}</p>}
      <footer>نسخهٔ وب هیچ دسترسی مستقیمی به دیتابیس حسابداری ویندوز ندارد.</footer>
    </section>
  </div>;
}
