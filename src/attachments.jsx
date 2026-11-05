import React,{useEffect,useState} from 'react';
import {Paperclip,Upload,Download,Eye,Trash2,RefreshCw,X,HelpCircle} from 'lucide-react';
import './attachments.css';

const identifier=()=>('ui-file-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
const limit=4*1024*1024;
const accepted=/\.(png|jpg|jpeg|pdf|txt)$/i;

function encodedFile(file){
 return new Promise((resolve,reject)=>{
  const reader=new FileReader();
  reader.onerror=()=>reject(new Error('فایل در این دستگاه خوانده نشد.'));
  reader.onload=()=>resolve(String(reader.result).split(',')[1]);
  reader.readAsDataURL(file);
 });
}

function download(item,encoded){
 const raw=atob(encoded),bytes=new Uint8Array(raw.length);
 for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
 const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));
 const a=document.createElement('a');a.href=url;a.download=item.filename;a.click();
 window.setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function CardAttachments({cardId,api,canEdit,compact=false}){
 const [items,setItems]=useState([]),[preview,setPreview]=useState(null);
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const refresh=async()=>{setItems(await api.attachmentList(cardId));};
 useEffect(()=>{setItems([]);setPreview(null);refresh().catch(e=>setMessage(e.message));},[cardId]);
 const run=async task=>{setBusy(true);setMessage('');try{await task();await refresh();}catch(e){setMessage(e.message||String(e));}finally{setBusy(false);}};
 const upload=async e=>{
  const file=e.target.files?.[0];e.target.value='';
  if(!file)return;
  if(!accepted.test(file.name)||file.size<=0||file.size>limit){
   setMessage('فقط فایل PNG/JPEG/PDF/TXT با اندازه حداکثر ۴ مگابایت مجاز است.');return;
  }
  await run(async()=>{await api.attachmentUpload(cardId,file.name,await encodedFile(file),identifier());});
 };
 const show=async item=>run(async()=>{
  const result=await api.attachmentPreview(item.id);
  setPreview(result);
 });
 const get=async item=>run(async()=>{const result=await api.attachmentSave(item.id);if(result.saved)setMessage('فایل با موفقیت در پوشه انتخابی ذخیره شد.');});
 return <div className={'card-attachments'+(compact?' card-attachments--compact':'')}>
  <div className="section-header attachment-heading"><h3><Paperclip size={16}/> فایل‌های بارگذاری‌شده ({items.length})</h3>
   {canEdit&&<label className="attachment-upload"><Upload size={15}/> بارگذاری<input type="file" aria-label="بارگذاری فایل کارت" accept=".png,.jpg,.jpeg,.pdf,.txt" onChange={upload} disabled={busy}/></label>}
   <button type="button" className="tiny-icon" aria-label="تازه‌سازی فایل‌ها" disabled={busy} onClick={()=>refresh().catch(e=>setMessage(e.message))}><RefreshCw size={15}/></button>
   <details className="attachment-help"><summary title="راهنمای بارگذاری و نگهداری فایل" aria-label="راهنمای پیوست‌ها"><HelpCircle size={15}/></summary>
    <p className="attachment-warning">فایل روی دستگاه میزبان نگهداری می‌شود؛ بدون دسترسی به میزبان یا شبکه دریافت نمی‌شود. پشتیبان Google Drive فقط داده‌های کار را شامل می‌شود، نه این فایل‌ها. فرمت‌های مجاز PNG/JPEG/PDF/TXT تا ۴ مگابایت‌اند.</p>
   </details>
  </div>
  {items.map(item=><div className="attachment-row" key={item.id}>
   <button type="button" className="attachment-filename" onClick={()=>get(item)} disabled={busy} title={'دانلود '+item.filename}><Paperclip size={15}/><strong dir="auto">{item.filename}</strong></button>
   <button type="button" aria-label={'دانلود '+item.filename} disabled={busy} onClick={()=>get(item)} title="دریافت فایل"><Download size={16}/></button>
   {!compact&&<button type="button" aria-label={'پیش‌نمایش '+item.filename} disabled={busy} onClick={()=>show(item)} title="پیش‌نمایش"><Eye size={16}/></button>}
   {canEdit&&<button type="button" aria-label={'حذف '+item.filename} disabled={busy} onClick={()=>{if(window.confirm('پیوست از کارت حذف شود؟'))run(async()=>{await api.attachmentDelete(item.id,identifier());setPreview(null);});}} title="حذف"><Trash2 size={16}/></button>}
  </div>)}
  {!items.length&&!compact&&<small>هنوز فایلی بارگذاری نشده است.</small>}
  {preview&&<div className="attachment-preview"><div><strong>پیش‌نمایش</strong><button onClick={()=>setPreview(null)}><X size={15}/></button></div>{preview.kind==='image'&&preview.available&&<img alt={preview.attachment.filename} src={'data:'+preview.attachment.mime+';base64,'+preview.content}/>}
   {preview.kind==='plain-text'&&<pre dir="auto">{preview.content}</pre>}
   {!preview.available&&<p>برای این فایل پیش‌نمایش امن نمایش داده نمی‌شود. از گزینه دریافت استفاده کن.</p>}</div>}
  {message&&<small role="alert" className="attachment-error">{message}</small>}
 </div>;
}
