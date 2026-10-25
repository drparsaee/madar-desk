import React,{useEffect,useState} from 'react';
import {Bell,Check,MessageCircle,Plus,RefreshCw,Trash2,X} from 'lucide-react';

const eventId=()=> 'ui_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2);
const date=v=>v?new Date(v).toLocaleString('fa-IR',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';

export function CardComments({cardId,api,canEdit,username}){
 const [items,setItems]=useState([]),[value,setValue]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 const load=async()=>{try{setItems(await api.collabRead('comments',cardId));setError('');}catch(e){setError('خواندن نظرات: '+e.message);}};
 useEffect(()=>{load();},[cardId]);
 const add=async()=>{if(!value.trim()||busy)return;setBusy(true);setError('');
   try{await api.collabCommand({type:'comment.add',eventId:eventId(),cardId,text:value.trim()});setValue('');await load();}
   catch(e){setError('ثبت نظر: '+e.message);}finally{setBusy(false);}};
 const remove=async item=>{if(!window.confirm('این نظر حذف شود؟'))return;setBusy(true);
   try{await api.collabCommand({type:'comment.delete',eventId:eventId(),commentId:item.id});await load();}
   catch(e){setError(e.message);}finally{setBusy(false);}};
 return <div className="team-comment-section">
   <div className="section-header"><h3><MessageCircle size={17}/> نظرات و گفتگو</h3><button className="tiny-icon" title="تازه‌سازی نظرات" onClick={load}><RefreshCw size={15}/></button></div>
   <div className="comment-thread">{items.filter(x=>!x.deletedAt).map(item=><article key={item.id}><div className="comment-meta"><strong>@{item.author}</strong><time>{date(item.createdAt)}</time>{canEdit&&username===item.author&&<button title="حذف نظر" disabled={busy} onClick={()=>remove(item)}><Trash2 size={13}/></button>}</div><p dir="auto">{item.text}</p></article>)}{!items.some(x=>!x.deletedAt)&&<small>هنوز نظری وجود ندارد.</small>}</div>
   {canEdit&&<div className="comment-compose"><textarea rows={3} dir="auto" placeholder="نظر بنویس؛ با @username به کاربر اشاره کن." value={value} maxLength={4000} onChange={e=>setValue(e.target.value)}/><button className="btn primary" onClick={add} disabled={busy||!value.trim()}><Plus size={15}/> ارسال نظر</button></div>}
   {error&&<p role="alert" className="field-error">{error}</p>}
 </div>;
}

export function NotificationsDialog({api,onClose}){
 const [items,setItems]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const load=async()=>{try{setItems(await api.collabRead('notifications'));setError('');}catch(e){setError(e.message);}};
 useEffect(()=>{load();},[]);
 const mark=async item=>{setBusy(true);try{await api.collabCommand({type:'notification.read',eventId:eventId(),notificationId:item.id});await load();}catch(e){setError(e.message);}finally{setBusy(false);}};
 return <div className="overlay" onMouseDown={onClose}><section className="dialog notifications-dialog" role="dialog" aria-modal="true" onMouseDown={e=>e.stopPropagation()}>
   <div className="dialog-head"><h2><Bell size={18}/> اعلان‌های من</h2><button className="icon-btn" onClick={onClose}><X size={19}/></button></div>
   <div className="dialog-body notifications-body"><button className="btn secondary" onClick={load}><RefreshCw size={15}/> تازه‌سازی</button>
   {items.map(item=><article key={item.id} className={item.readAt?'notice-read':''}><div><strong>{item.kind==='mention'?'اشاره به شما':item.kind==='watch'?'نظر جدید':'قانون خودکار'}</strong><small>{date(item.createdAt)}</small></div><p>{item.message}</p>{!item.readAt&&<button disabled={busy} onClick={()=>mark(item)}><Check size={15}/> خوانده شد</button>}</article>)}
   {!items.length&&<p className="shared-empty">اعلان جدیدی وجود ندارد.</p>}{error&&<p className="field-error">{error}</p>}</div>
 </section></div>;
}

export function ActivityDialog({api,onClose}){
 const [items,setItems]=useState([]),[error,setError]=useState('');
 useEffect(()=>{api.collabRead('activity').then(setItems).catch(e=>setError(e.message));},[]);
 return <div className="overlay" onMouseDown={onClose}><section className="dialog notifications-dialog" role="dialog" aria-modal="true" onMouseDown={e=>e.stopPropagation()}>
   <div className="dialog-head"><h2><MessageCircle size={18}/> تاریخچه فعالیت</h2><button className="icon-btn" onClick={onClose}><X size={19}/></button></div>
   <div className="dialog-body notifications-body">{items.map(item=><article key={item.id}><div><strong>@{item.actor}</strong><small>{date(item.at)}</small></div><p>{item.action} · {item.cardId||item.projectId}</p></article>)}{!items.length&&<p>هنوز رویدادی در ماژول همکاری ثبت نشده است.</p>}{error&&<p className="field-error">{error}</p>}</div>
 </section></div>;
}
