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

// Resolve only inside the caller's authenticated task snapshot. The host still
// checks current ACL before navigation; a notification ID is never a grant.
export function resolveNotificationLocation(notice,{projects=[],boards=[],workspaces=[],tasks=[]}={}){
 if(!notice||typeof notice.projectId!=='string')return null;
 if(!projects.some(project=>project.id===notice.projectId))return null;
 const visibleBoard=board=>board&&!board.archived&&board.projectId===notice.projectId&&
   workspaces.some(space=>space.id===board.workspaceId&&!space.archived);
 if(notice.cardId!=null){
   const card=tasks.find(item=>item.id===notice.cardId&&item.projectId===notice.projectId&&
     item.deleted!==true&&item.archived!==true);
   const board=boards.find(item=>item.id===card?.boardId);
   if(!card||!visibleBoard(board)||board.stages?.some(stage=>
     stage.id===(card.listId||card.status)&&stage.archived===true))return null;
   return {kind:'card',projectId:notice.projectId,cardId:card.id,boardId:board.id,workspaceId:board.workspaceId};
 }
 const board=boards.find(visibleBoard);
 return board?{kind:'project',projectId:notice.projectId,boardId:board.id,workspaceId:board.workspaceId}:null;
}

export function NotificationsDialog({api,onClose,onOpenTarget}){
 const [items,setItems]=useState([]),[loading,setLoading]=useState(true);
 const [busyId,setBusyId]=useState(''),[error,setError]=useState('');
 const [message,setMessage]=useState('');
 const dialogRef=useRef(null),mounted=useRef(false),pendingReads=useRef(new Map());
 const load=async()=>{
   setLoading(true);setError('');setMessage('');
   try{
     const received=await api.collabRead('notifications');
     if(!Array.isArray(received))throw Error('Invalid notifications response');
     if(mounted.current)setItems(received);
   }catch{
     if(mounted.current)setError('دریافت اعلان‌ها ممکن نشد. اتصال و دسترسی خود را بررسی کنید.');
   }finally{if(mounted.current)setLoading(false);}
 };
 useEffect(()=>{
   mounted.current=true;
   const previous=document.activeElement;
   dialogRef.current?.querySelector('.notifications-close')?.focus();
   const handleKey=event=>{
     if(event.key==='Escape'){
       event.preventDefault();event.stopPropagation();onClose();return;
     }
     if(event.key!=='Tab')return;
     const controls=Array.from(dialogRef.current?.querySelectorAll('button:not(:disabled),[href],[tabindex]:not([tabindex="-1"])')||[])
       .filter(node=>node.getClientRects().length>0);
     if(!controls.length){event.preventDefault();dialogRef.current?.focus();return;}
     if(event.shiftKey&&(document.activeElement===controls[0]||!dialogRef.current?.contains(document.activeElement))){
       event.preventDefault();controls[controls.length-1].focus();
     }else if(!event.shiftKey&&(document.activeElement===controls[controls.length-1]||!dialogRef.current?.contains(document.activeElement))){
       event.preventDefault();controls[0].focus();
     }
   };
   document.addEventListener('keydown',handleKey);
   load();
   return()=>{mounted.current=false;document.removeEventListener('keydown',handleKey);if(previous?.isConnected)previous.focus();};
 },[]);
 const mark=async item=>{
   if(busyId||item.readAt)return;
   setBusyId(item.id);setError('');setMessage('');
   // Reuse the same event ID on retry when an ACK may have been lost.
   const command=pendingReads.current.get(item.id)||
     {type:'notification.read',eventId:eventId(),notificationId:item.id};
   pendingReads.current.set(item.id,command);
   try{
     const result=await api.collabCommand(command);
     if(!result||result.notificationId!==item.id||!result.readAt)throw Error('Missing read acknowledgment');
     pendingReads.current.delete(item.id);
     if(mounted.current){
       setItems(current=>current.map(notice=>notice.id===item.id?{...notice,readAt:result.readAt}:notice));
       setMessage('اعلان به‌عنوان خوانده‌شده ثبت شد.');
     }
   }catch{
     if(mounted.current)setError('ثبت وضعیت خوانده‌شدن ناموفق یا نامشخص بود. دوباره تلاش کنید.');
   }finally{if(mounted.current)setBusyId('');}
 };
 const openTarget=async item=>{
   if(busyId||typeof onOpenTarget!=='function')return;
   setBusyId(item.id);setError('');setMessage('');
   try{
     if(await onOpenTarget(item)!==true)throw Error('Not available');
     onClose();
   }catch{
     if(mounted.current)setError('مقصد این اعلان در دسترس نیست یا مجوز مشاهده آن وجود ندارد.');
   }finally{if(mounted.current)setBusyId('');}
 };
 const unread=items.filter(item=>!item.readAt).length;
 return <div className="overlay" onMouseDown={event=>{if(event.target===event.currentTarget)onClose();}}>
   <section ref={dialogRef} tabIndex={-1} className="dialog notifications-dialog" role="dialog" aria-modal="true"
     aria-label="اعلان‌های من" onMouseDown={event=>event.stopPropagation()}>
     <div className="dialog-head"><h2><Bell size={18}/> اعلان‌های من <span className="notifications-unread" aria-label={`${unread.toLocaleString('fa-IR')} اعلان خوانده‌نشده`}>{unread.toLocaleString('fa-IR')} خوانده‌نشده</span></h2>
       <button type="button" className="icon-btn notifications-close" aria-label="بستن اعلان‌ها" onClick={onClose}><X size={19}/></button></div>
     <div className="dialog-body notifications-body">
       <button type="button" className="btn secondary" disabled={!!busyId||loading} onClick={load}><RefreshCw size={15}/> تازه‌سازی</button>
       {loading&&<p role="status">در حال دریافت اعلان‌ها…</p>}
       {items.map(item=><article key={item.id} className={item.readAt?'notice-read':''}>
         <div className="notifications-meta"><strong>{item.kind==='mention'?'اشاره به شما':item.kind==='watch'?'نظر جدید':'قانون خودکار'}</strong>
           <small>{date(item.createdAt)}</small>{!item.readAt&&<span className="notifications-dot">خوانده‌نشده</span>}</div>
         <p dir="auto">{item.message}</p>
         <div className="notifications-actions">
           {typeof onOpenTarget==='function'&&<button type="button" disabled={!!busyId}
             onClick={()=>openTarget(item)} aria-label="نمایش مقصد اعلان">نمایش مقصد</button>}
           {!item.readAt&&<button type="button" disabled={!!busyId} onClick={()=>mark(item)}><Check size={15}/> خوانده شد</button>}
         </div>
       </article>)}
       {!loading&&!items.length&&!error&&<p className="shared-empty">اعلانی برای نمایش وجود ندارد.</p>}
       {error&&<p role="alert" className="field-error">{error}</p>}
       {message&&<p role="status" className="notifications-status">{message}</p>}
     </div>
   </section>
 </div>;
}

export function ActivityDialog({api,onClose}){
 const [items,setItems]=useState([]),[error,setError]=useState('');
 useEffect(()=>{api.collabRead('activity').then(setItems).catch(e=>setError(e.message));},[]);
 return <div className="overlay" onMouseDown={onClose}><section className="dialog notifications-dialog" role="dialog" aria-modal="true" onMouseDown={e=>e.stopPropagation()}>
   <div className="dialog-head"><h2><MessageCircle size={18}/> تاریخچه فعالیت</h2><button className="icon-btn" onClick={onClose}><X size={19}/></button></div>
   <div className="dialog-body notifications-body">{items.map(item=><article key={item.id}><div><strong>@{item.actor}</strong><small>{date(item.at)}</small></div><p>{item.action} · {item.cardId||item.projectId}</p></article>)}{!items.length&&<p>هنوز رویدادی در ماژول همکاری ثبت نشده است.</p>}{error&&<p className="field-error">{error}</p>}</div>
 </section></div>;
}
