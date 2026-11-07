import React,{useEffect,useRef,useState} from 'react';
import {Bell,Check,MessageCircle,Plus,RefreshCw,Trash2,X,CornerDownLeft,Pencil,Reply} from 'lucide-react';
import './teamplus.css';

const eventId=()=> 'ui_'+Date.now().toString(36)+'_'+Math.random().toString(36).slice(2);
const date=v=>v?new Date(v).toLocaleString('fa-IR',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';

function ConversationThread({kind,targetId,api,canEdit=false,canManage=false,username='',title='گفت‌وگو'}){
 const [items,setItems]=useState([]),[value,setValue]=useState(''),[busy,setBusy]=useState(false);
 const [error,setError]=useState(''),[replyTo,setReplyTo]=useState(null);
 const [editId,setEditId]=useState(''),[editValue,setEditValue]=useState('');
 const pending=useRef(null);
 const load=async()=>{
   const result=await api.collabRead(kind,targetId);
   if(!Array.isArray(result))throw Error('پاسخ گفت‌وگو معتبر نیست.');
   setItems(result);return result;
 };
 useEffect(()=>{
   let alive=true;
   api.collabRead(kind,targetId).then(next=>{if(alive)setItems(next);})
     .catch(e=>{if(alive)setError('خواندن گفتگو: '+e.message);});
   return()=>{alive=false;};
 },[api,kind,targetId]);
 const add=async()=>{
   const text=value.trim();
   if(!text||busy)return;
   setBusy(true);setError('');
   const payload=kind==='comments'?
     {type:replyTo?'comment.reply':'comment.add',cardId:targetId,text,
       ...(replyTo?{replyToId:replyTo.id}:{})}:
     {type:'project.comment.add',projectId:targetId,text,replyToId:replyTo?.id||''};
   const fingerprint=JSON.stringify(payload);
   const command=pending.current?.fingerprint===fingerprint?pending.current.command:
     {...payload,eventId:eventId()};
   pending.current={fingerprint,command};
   try{await api.collabCommand(command);pending.current=null;setValue('');setReplyTo(null);await load();}
   catch(e){setError('ارسال پیام: '+e.message+'؛ تلاش مجدد با همان شناسه انجام می‌شود.');}
   finally{setBusy(false);}
 };
 const edit=async item=>{
   if(!editValue.trim()||busy)return;
   setBusy(true);setError('');
   try{await api.collabCommand({type:kind==='comments'?'comment.edit':'project.comment.edit',
     eventId:eventId(),commentId:item.id,text:editValue.trim()});
     setEditId('');setEditValue('');await load();}
   catch(e){setError('ویرایش پیام: '+e.message);}
   finally{setBusy(false);}
 };
 const remove=async item=>{
   if(!window.confirm('این پیام حذف شود؟'))return;
   setBusy(true);setError('');
   try{await api.collabCommand({type:kind==='comments'?'comment.delete':'project.comment.delete',
     eventId:eventId(),commentId:item.id});await load();}
   catch(e){setError('حذف پیام: '+e.message);}
   finally{setBusy(false);}
 };
 const isAuthor=item=>username===item.author||username==='local';
 const canDelete=item=>canEdit&&(canManage||isAuthor(item));
 return <div className="team-comment-section" aria-label={title}>
   <div className="section-header"><h3><MessageCircle size={17}/>{title}</h3>
     <button className="tiny-icon" title="تازه‌سازی نظرات" onClick={()=>load().catch(e=>setError(e.message))}><RefreshCw size={15}/></button></div>
   <div className="comment-thread">
     {items.map(item=><article key={item.id} className={'team-comment-item'+(item.replyToId?' team-comment-reply':'')}>
       <div className="comment-meta"><strong>@{item.author}</strong><time>{date(item.createdAt)}</time>
         {item.updatedAt&&item.updatedAt!==item.createdAt&&!item.deletedAt&&<small>ویرایش‌شده</small>}
         {!item.deletedAt&&canEdit&&<button title="پاسخ" disabled={busy} onClick={()=>{setReplyTo(item);pending.current=null;}}><Reply size={13}/></button>}
         {!item.deletedAt&&canEdit&&isAuthor(item)&&<button title="ویرایش نظر" disabled={busy} onClick={()=>{setEditId(item.id);setEditValue(item.text);}}><Pencil size={13}/></button>}
         {!item.deletedAt&&canDelete(item)&&<button title="حذف نظر" disabled={busy} onClick={()=>remove(item)}><Trash2 size={13}/></button>}
       </div>
       {item.replyToId&&<small className="team-reply-label"><CornerDownLeft size={12}/> پاسخ به پیام قبلی</small>}
       {editId===item.id?<div className="comment-compose"><textarea dir="auto" rows={2} value={editValue} maxLength={4000}
         onChange={e=>setEditValue(e.target.value)}/><button className="btn primary" disabled={busy||!editValue.trim()} onClick={()=>edit(item)}>ذخیره</button>
         <button className="btn secondary" onClick={()=>setEditId('')}>انصراف</button></div>:
         <p dir="auto">{item.deletedAt?'پیام حذف شده است.':item.text}</p>}
     </article>)}
     {!items.length&&<small>هنوز پیامی وجود ندارد.</small>}
   </div>
   {canEdit&&<div className="comment-compose">
     {replyTo&&<div className="team-reply-hint">پاسخ به @{replyTo.author}
       <button type="button" aria-label="لغو پاسخ" onClick={()=>{setReplyTo(null);pending.current=null;}}><X size={13}/></button></div>}
     <textarea rows={3} dir="auto" placeholder="پیام بنویس؛ با @username به کاربر اشاره کن." value={value}
       maxLength={4000} onChange={e=>{setValue(e.target.value);pending.current=null;}}
       onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();add();}}}/>
     <button className="btn primary" onClick={add} disabled={busy||!value.trim()}><Plus size={15}/> ارسال پیام</button>
   </div>}
   {error&&<p role="alert" className="field-error">{error}</p>}
 </div>;
}
export function CardComments({cardId,api,canEdit,canManage=false,username}){
 return <ConversationThread kind="comments" targetId={cardId} api={api} canEdit={canEdit} canManage={canManage}
   username={username} title="نظرات و گفت‌وگوی کارت"/>;
}
export function ProjectConversation({projectId,projectName='',api,canEdit,canManage=false,username,onClose}){
 return <div className="overlay project-conversation-overlay" onMouseDown={onClose}>
   <section className="dialog project-conversation-dialog" role="dialog" aria-modal="true"
     aria-label={'گفت‌وگوی پروژه '+projectName} onMouseDown={e=>e.stopPropagation()}>
     <div className="dialog-head"><h2><MessageCircle size={19}/> گفت‌وگوی پروژه: {projectName}</h2>
       <button className="icon-btn" title="بستن گفت‌وگو" onClick={onClose}><X size={19}/></button></div>
     <div className="dialog-body"><ConversationThread key={projectId} kind="project-comments"
       targetId={projectId} api={api} canEdit={canEdit} canManage={canManage} username={username}
       title="پیام‌های پروژه"/></div>
   </section>
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
