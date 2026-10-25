import React,{useState} from 'react';
import {FileInput,X} from 'lucide-react';
import {inspectTrelloExport,importTrelloBoard} from './trello_import.js';
import './trello_import.css';
export function TrelloImportPanel({onImport,onClose}){
  const [data,setData]=useState(null),[summary,setSummary]=useState(null),[error,setError]=useState('');
  const read=async e=>{
    setError('');setData(null);setSummary(null);
    const file=e.target.files?.[0];if(!file)return;
    if(file.size>3*1024*1024){setError('فایل خروجی باید حداکثر سه مگابایت باشد.');return;}
    try{const value=JSON.parse(await file.text());const details=inspectTrelloExport(value);setSummary(details);setData(value);}
    catch(err){setError(err.message);}
  };
  return <div className="trello-import-backdrop" onMouseDown={onClose}>
    <section role="dialog" aria-label="ورود فایل Trello" aria-modal="true" className="trello-import-dialog" onMouseDown={e=>e.stopPropagation()}>
      <header><h2><FileInput size={20}/> ورود برد Trello</h2><button aria-label="بستن" onClick={onClose}><X size={18}/></button></header>
      <div className="trello-import-body"><p>فایل JSON خروجی یک برد Trello را انتخاب کنید. یک پروژه و برد جدید ایجاد می‌شود؛ پروژه‌ها و کارت‌های فعلی حفظ خواهند شد.</p>
        <input aria-label="فایل JSON خروجی Trello" type="file" accept=".json,application/json" onChange={read}/>
        {summary&&<p role="status"><b>{summary.name}</b>: {summary.lists} ستون، {summary.cards} کارت ({summary.openCards} کارت فعال).</p>}
        {error&&<p role="alert" className="trello-error">{error}</p>}
        <small>بخش‌های منتقل‌شده: عنوان، توضیح، برچسب، موعد و چک‌لیست. اعضا، پیوست‌ها، دیدگاه‌ها، تاریخچه و اطلاعات مالی انتقال داده نمی‌شوند. برای مهاجرت کامل نیاز به مسیر جداگانه است.</small>
        <div className="trello-import-actions"><button onClick={onClose}>انصراف</button><button disabled={!data} className="btn primary" onClick={()=>{try{onImport(s=>importTrelloBoard(s,data));onClose();}catch(err){setError(err.message);}}}>وارد کردن در پروژه جدید</button></div>
      </div>
    </section>
  </div>;
}
