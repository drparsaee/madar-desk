import React,{useEffect,useState} from 'react';
import {Paperclip,Upload,Download,Eye,Trash2,RefreshCw,X} from 'lucide-react';
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

export function CardAttachments({cardId,api,canEdit}){
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
 const get=async item=>run(async()=>{const result=await api.attachmentRead(item.id);download(item,result.contentBase64);});
 return <div className="card-attachments">
  <div className="section-header"><h3><Paperclip size={17}/> پیوست‌های واقعی کارت ({items.length})</h3><button className="tiny-icon" disabled={busy} onClick={()=>refresh().catch(e=>setMessage(e.message))}><RefreshCw size={15}/></button></div>
  <p className="attachment-warning">فایل در دستگاه میزبان نگهداری می‌شود. هنگام خاموشی میزبان یا بدون دسترسی شبکه، پیوست‌ها قابل دریافت نیستند. همگام‌سازی Google Drive فقط شامل داده‌های کار است، نه این فایل‌ها.</p>
  {canEdit&&<label className="attachment-upload"><Upload size={16}/> انتخاب فایل برای بارگذاری<input type="file" accept=".png,.jpg,.jpeg,.pdf,.txt" onChange={upload} disabled={busy}/></label>}
  {items.map(item=><div className="attachment-row" key={item.id}><div title={item.filename}><strong dir="auto">{item.filename}</strong><small>{Math.ceil(item.size/1024).toLocaleString('fa-IR')} کیلوبایت | {item.uploadedBy}</small></div><button disabled={busy} onClick={()=>show(item)} title="پیش‌نمایش"><Eye size={16}/></button><button disabled={busy} onClick={()=>get(item)} title="دریافت فایل"><Download size={16}/></button>{canEdit&&<button disabled={busy} onClick={()=>{if(window.confirm('پیوست از کارت حذف شود؟'))run(async()=>{await api.attachmentDelete(item.id,identifier());setPreview(null);});}} title="حذف"><Trash2 size={16}/></button>}</div>)}
  {!items.length&&<small>هنوز فایل واقعی بارگذاری نشده است. لینک‌های اشتراک ویندوز در بخش جداگانه قرار دارند.</small>}
  {preview&&<div className="attachment-preview"><div><strong>پیش‌نمایش</strong><button onClick={()=>setPreview(null)}><X size={15}/></button></div>{preview.kind==='image'&&preview.available&&<img alt={preview.attachment.filename} src={'data:'+preview.attachment.mime+';base64,'+preview.content}/>}
   {preview.kind==='plain-text'&&<pre dir="auto">{preview.content}</pre>}
   {!preview.available&&<p>برای این فایل پیش‌نمایش امن نمایش داده نمی‌شود. از گزینه دریافت استفاده کن.</p>}</div>}
  {message&&<small role="alert" className="attachment-error">{message}</small>}
 </div>;
}
