import React,{useState} from 'react';
import {Download,RefreshCw,ShieldCheck} from 'lucide-react';
import packageInfo from '../package.json';
import './update_settings.css';

/** Shared UI, two separately authenticated native bridges.
 * Never accepts an external URL, executable path or SHA from the renderer.
 * Native methods perform the GitHub asset digest verification and the installer
 * is scheduled only after explicit confirmation and full desktop exit.
 */
export function UpdateSettings({api,desktop=true}){
  const [phase,setPhase]=useState('idle');
  const [info,setInfo]=useState(null);
  const [message,setMessage]=useState('');
  const available=desktop&&typeof api?.releaseCheck==='function';
  const busy=phase==='checking'||phase==='downloading'||phase==='scheduling';
  async function check(){
    if(!available||busy)return;
    setPhase('checking');setMessage('');
    try{
      const result=await api.releaseCheck();
      if(!result||typeof result.available!=='boolean'||
          typeof result.current!=='string'||typeof result.latest!=='string')
        throw new Error('پاسخ سرویس انتشار معتبر نیست.');
      setInfo(result);
      setPhase(result.available?'available':'current');
      setMessage(result.available?'نسخهٔ جدید قابل دریافت است.':'نسخهٔ جدیدتری در کانال رسمی تأیید نشد.');
    }catch(error){
      setPhase('error');setInfo(null);
      setMessage('بررسی به‌روزرسانی انجام نشد: '+(error?.message||String(error)));
    }
  }
  async function download(){
    if(!info?.available||!available||busy||typeof api.releaseDownload!=='function')return;
    setPhase('downloading');setMessage('');
    try{
      const result=await api.releaseDownload();
      if(result?.verified!==true)throw new Error('صحت فایل نصب تأیید نشد.');
      setPhase('downloaded');
      setMessage('بستهٔ رسمی دریافت و SHA-256 آن تأیید شد. نصب پس از خروج برنامه انجام می‌شود.');
    }catch(error){setPhase('error');setMessage('دریافت نسخه ناموفق بود: '+(error?.message||String(error)));}
  }
  async function install(){
    if(phase!=='downloaded'||!available||busy||typeof api.releaseInstall!=='function')return;
    if(!window.confirm('نصب به‌روزرسانی فقط بعد از خروج کامل از مدار آغاز می‌شود. اطلاعات دفتر قبل از تعویض نسخه باید در مرحلهٔ نصب پشتیبان‌گیری شوند. ادامه دهید؟'))return;
    setPhase('scheduling');setMessage('');
    try{
      const result=await api.releaseInstall();
      if(result?.scheduledAfterExit!==true)throw new Error('زمان‌بندی نصب تأیید نشد.');
      setPhase('scheduled');
      setMessage('نصب نسخهٔ '+result.version+' پس از بسته‌شدن کامل این برنامه آغاز خواهد شد. برای ادامه، از برنامه خارج شوید.');
    }catch(error){setPhase('error');setMessage('آماده‌سازی نصب انجام نشد: '+(error?.message||String(error)));}
  }
  return <section className="madar-update-settings" aria-label="به‌روزرسانی نرم‌افزار">
    <div className="madar-update-settings__heading">
      <h3><RefreshCw size={17}/> به‌روزرسانی نرم‌افزار</h3>
      <span dir="ltr">v{packageInfo.version}</span>
    </div>
    <p>بررسی نسخه فقط از کانال انتشار رسمی مدار انجام می‌شود. فایل نصب باید با هش SHA-256 انتشار مطابقت داشته باشد.</p>
    {!available?<p role="status">به‌روزرسانی خودکار فقط در نسخهٔ نصب‌شدهٔ ویندوز در دسترس است.</p>:<>
      <div className="madar-update-settings__actions">
        <button type="button" onClick={check} disabled={busy||phase==='scheduled'}>
          <RefreshCw size={16}/> {phase==='checking'?'در حال بررسی…':'بررسی به‌روزرسانی'}
        </button>
        {(phase==='available'||phase==='error'&&info?.available)&&
          <button type="button" onClick={download} disabled={busy} className="madar-update-settings__accent">
            <Download size={16}/> دریافت نسخهٔ {info?.latest}
          </button>}
        {phase==='downloaded'&&<button type="button" onClick={install} disabled={busy} className="madar-update-settings__accent">
          <ShieldCheck size={16}/> نصب امن پس از خروج
        </button>}
      </div>
      {info&&<p>نسخهٔ جاری: <b dir="ltr">{info.current}</b> · آخرین نسخهٔ بررسی‌شده: <b dir="ltr">{info.latest}</b></p>}
      {message&&<p role="status" aria-live="polite" className={phase==='error'?'madar-update-settings__error':''}>{message}</p>}
    </>}
  </section>;
}
