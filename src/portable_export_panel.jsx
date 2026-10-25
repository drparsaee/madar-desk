import React,{useMemo,useState} from 'react';
import {createPortableExport,previewPortableExport,portableJson,portableTasksCsv} from './migration_export.js';

/** Client-side export of an already authorized operational snapshot.
 * This is deliberately NOT a backup/restore or an accounting export. */
export function PortableExportPanel({state,canManage=false,onClose=()=>{}}){
  const [ack,setAck]=useState(false);
  const [error,setError]=useState('');
  const result=useMemo(()=>{
    if(!canManage)return {preview:null,error:'دسترسی خروجی فقط برای مدیر مجاز است.'};
    try{return {preview:previewPortableExport(state),error:''};}
    catch(e){return {preview:null,error:e.message};}
  },[state,canManage]);
  const download=kind=>{
    if(!canManage||!result.preview||result.preview.financialDataPresent&&!ack)return;
    try{
      const bundle=createPortableExport(state,{acknowledgeFinancialExclusion:ack});
      const content=kind==='csv'?portableTasksCsv(bundle):portableJson(bundle);
      const blob=new Blob([content],{type:kind==='csv'?'text/csv;charset=utf-8':'application/json;charset=utf-8'});
      const url=URL.createObjectURL(blob);
      try{
        const node=document.createElement('a');
        node.href=url;node.download='madar-operational-subset.'+(kind==='csv'?'csv':'json');
        document.body.append(node);node.click();node.remove();setError('');
      }finally{setTimeout(()=>URL.revokeObjectURL(url),1000);}
    }catch(e){setError(e.message);}
  };
  const preview=result.preview;
  return <div className="dialog-body" dir="rtl" role="region" aria-label="خروجی قابل‌انتقال عملیات">
    <p>این خروجی فقط شامل اطلاعات عملیاتی کارها، بردها و چک‌لیست‌هاست. <strong>بکاپ کامل مدار نیست.</strong></p>
    {result.error&&<p className="warning" role="alert">ساخت پیش‌نمایش ممکن نیست: {result.error}</p>}
    {preview&&<>
      <p>دامنه: {preview.sourceCounts.projects.toLocaleString('fa-IR')} پروژه، {preview.sourceCounts.boards.toLocaleString('fa-IR')} برد، {preview.sourceCounts.tasks.toLocaleString('fa-IR')} کارت.</p>
      <p><strong>مستثنا:</strong> تمام مبالغ، هزینه‌ها، فاکتورها و دفاتر مالی، حساب‌ها و رمزها، فایل‌های پیوست، نظرات، گزارش‌ها و تاریخچه. هیچ فایل پیوست واقعی در این خروجی قرار نمی‌گیرد.</p>
      <p>تعداد ویژگی‌های حذف‌شده در تبدیل: {preview.excludedPropertyOccurrences.toLocaleString('fa-IR')} (نه تعداد رکورد ازدست‌رفته). متن آزاد کارت ممکن است اطلاعات خصوصی داشته باشد.</p>
      {preview.financialDataPresent&&<label className="setting-toggle"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/><span>می‌دانم داده مالی موجود از این خروجی حذف می‌شود و برای بازیابی کامل باید پشتیبان مستقل مالی/پیوست داشته باشم.</span></label>}
      <div className="form-footer">
        <button type="button" className="btn secondary" onClick={onClose}>بستن</button>
        <button type="button" className="btn secondary" disabled={preview.financialDataPresent&&!ack} onClick={()=>download('csv')}>CSV کارت‌ها</button>
        <button type="button" className="btn primary" disabled={preview.financialDataPresent&&!ack} onClick={()=>download('json')}>JSON عملیاتی</button>
      </div>
    </>}
    {error&&<p className="warning" role="alert">خروجی ایجاد نشد: {error}</p>}
  </div>;
}
