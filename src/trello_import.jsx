import React,{useState} from 'react';
import {FileInput,X} from 'lucide-react';
import {inspectTrelloExport,importTrelloBoard} from './trello_import.js';
import {inspectNotionCsv,importNotionCsvBoard} from './notion_csv_import.js';
import './trello_import.css';

// Legacy export name is kept for compatibility with Madar App.
export function TrelloImportPanel({onImport,onClose}){
  const [format,setFormat]=useState('trello');
  const [data,setData]=useState(null),[summary,setSummary]=useState(null),[error,setError]=useState('');
  const clear=()=>{setData(null);setSummary(null);setError('');};
  const read=async event=>{
    clear();
    const file=event.target.files?.[0];if(!file)return;
    if(file.size>3*1024*1024){setError('حجم فایل باید حداکثر سه مگابایت باشد.');return;}
    const expected=format==='notion'?/\.csv$/i:/\.json$/i;
    if(!expected.test(file.name)){setError('پسوند فایل با فرمت انتخاب‌شده یکسان نیست.');return;}
    try{
      const content=await file.text();
      if(format==='notion'){
        setSummary(inspectNotionCsv(content));setData(content);
      }else{
        const json=JSON.parse(content);
        setSummary(inspectTrelloExport(json));setData(json);
      }
    }catch(err){setError(err?.message||'فایل ورودی نامعتبر است.');}
  };
  const commit=()=>{
    if(data===null||!summary)return;
    try{
      if(format==='notion')onImport(state=>importNotionCsvBoard(state,data));
      else onImport(state=>importTrelloBoard(state,data));
      onClose();
    }catch(err){setError(err?.message||'ورود اطلاعات انجام نشد.');}
  };
  return <div className="trello-import-backdrop" onMouseDown={onClose}>
    <section role="dialog" aria-label="ورود اطلاعات برد" aria-modal="true"
      className="trello-import-dialog" onMouseDown={event=>event.stopPropagation()}>
      <header><h2><FileInput size={20}/> ورود اطلاعات برد</h2>
        <button aria-label="بستن" onClick={onClose}><X size={18}/></button></header>
      <div className="trello-import-body">
        <label>منبع اطلاعات
          <select aria-label="منبع اطلاعات" value={format}
            onChange={event=>{setFormat(event.target.value);clear();}}>
            <option value="trello">Trello (JSON)</option>
            <option value="notion">Notion (CSV)</option>
          </select>
        </label>
        <p>{format==='trello'
          ?'فایل JSON خروجی یک برد Trello را انتخاب کنید.'
          :'فایل CSV خروجی یک جدول Notion را انتخاب کنید. ستون Name یا Title الزامی است؛ Status و Description و Tags و Date اختیاری‌اند.'}</p>
        <input key={format} aria-label={format==='notion'?'فایل CSV خروجی Notion':'فایل JSON خروجی Trello'}
          type="file" accept={format==='notion'?'.csv,text/csv':'.json,application/json'} onChange={read}/>
        {summary&&<p role="status"><b>{summary.name}</b>: {summary.lists} ستون، {summary.cards} کارت
          {format==='notion'&&`، ${summary.properties} فیلد سفارشی`}.</p>}
        {error&&<p role="alert" className="trello-error">{error}</p>}
        <small>{format==='trello'
          ?'عنوان، توضیحات، برچسب، موعد و چک‌لیست منتقل می‌شود. اعضا، پیوست‌ها، تاریخچه و داده‌های مالی منتقل نمی‌شوند.'
          :'فقط یک جدول وارد می‌شود. اطلاعات مالی، اعضا، پیوست‌ها و فایل‌های داخلی Notion منتقل نمی‌شوند. ردیف‌های ورودی به پروژه و برد جدید افزوده می‌شوند؛ اطلاعات موجود حفظ می‌شوند.'}</small>
        <div className="trello-import-actions">
          <button onClick={onClose}>انصراف</button>
          <button disabled={data===null} className="btn primary" onClick={commit}>ورود به پروژه جدید</button>
        </div>
      </div>
    </section>
  </div>;
}
