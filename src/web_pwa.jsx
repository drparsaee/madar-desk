import React, {useEffect, useState} from 'react';
import {Download, HardDrive} from 'lucide-react';

export function WebPwaBanner({onBackup,onSync,status={}}) {
  const [installPrompt,setInstallPrompt]=useState(null);
  useEffect(()=>{
    const onPrompt=event=>{event.preventDefault();setInstallPrompt(event);};
    const onInstalled=()=>setInstallPrompt(null);
    window.addEventListener('beforeinstallprompt',onPrompt);
    window.addEventListener('appinstalled',onInstalled);
    return()=>{
      window.removeEventListener('beforeinstallprompt',onPrompt);
      window.removeEventListener('appinstalled',onInstalled);
    };
  },[]);
  return <section className="web-pwa-banner" role="status" aria-label="وضعیت ذخیره‌سازی نسخهٔ وب" dir="rtl">
    <div className="web-pwa-banner__identity"><HardDrive size={17}/>
      <strong>مدار وب · {status.connected?'حساب متصل':'ذخیره‌سازی محلی'}</strong>
      <span>{status.conflict?'تعارض نسخه نیازمند انتخاب است.':
        status.pending?'تغییرات محلی در صف ارسال هستند.':
        status.connected?'فضای کاری محلی به حساب متصل است؛ وضعیت ارسال را بررسی کنید.':
        'داده‌ها در این مرورگر ذخیره می‌شوند؛ برای استفادهٔ چنددستگاهی حساب را متصل کنید.'}</span>
    </div>
    <div className="web-pwa-banner__actions">
      <button type="button" onClick={onBackup}><Download size={15}/> پشتیبان</button>
      <button type="button" onClick={onSync}><HardDrive size={15}/> اتصال آنلاین</button>
      {installPrompt&&<button type="button" onClick={async()=>{
        try{await installPrompt.prompt();}finally{setInstallPrompt(null);}
      }}>نصب وب‌اپ</button>}
    </div>
  </section>;
}
