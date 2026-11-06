import React, {useEffect, useState} from 'react';
import {Download, HardDrive} from 'lucide-react';

export function WebPwaBanner({onBackup}) {
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
      <strong>مدار وب · حالت محلی</strong>
      <span>داده‌ها فقط در این مرورگر ذخیره می‌شوند؛ همگام‌سازی آنلاین هنوز فعال نیست.</span>
    </div>
    <div className="web-pwa-banner__actions">
      <button type="button" onClick={onBackup}><Download size={15}/> پشتیبان</button>
      {installPrompt&&<button type="button" onClick={async()=>{
        try{await installPrompt.prompt();}finally{setInstallPrompt(null);}
      }}>نصب وب‌اپ</button>}
    </div>
  </section>;
}
