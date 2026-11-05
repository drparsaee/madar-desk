import React, {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {Archive, CheckCircle2, Copy, ExternalLink, Image, Move, Tag, Trash2, Users, CalendarDays, X} from 'lucide-react';
import {laneContextPopupPosition} from './board_lane_actions.jsx';
import {CardCover} from './cardextras.jsx';

/** Context actions on an individual card. Caller owns permission checks. */
export function CardContextMenu({request,task,onClose,onOpen,onOpenSection,onCoverChange,onDuplicate,onArchive,onDelete,
  onToggleComplete,canEdit=false}) {
  const panel=useRef(null);
  const returnFocus=useRef(null);
  const closeRef=useRef(onClose);
  closeRef.current=onClose;
  const [position,setPosition]=useState(null);
  const [pendingDanger,setPendingDanger]=useState(null);
  const [coverOpen,setCoverOpen]=useState(false);
  useEffect(()=>{setPendingDanger(null);setCoverOpen(false);},[request?.id]);
  useLayoutEffect(()=>{
    if(!request||!panel.current)return;
    const bounds=panel.current.getBoundingClientRect();
    setPosition(laneContextPopupPosition(request,bounds,window.innerWidth,window.innerHeight));
  },[request,coverOpen]);
  useEffect(()=>{
    if(!request)return;
    returnFocus.current=document.activeElement;
    const focusFrame=requestAnimationFrame(()=>panel.current?.querySelector('[role="menuitem"]')?.focus());
    const close=event=>{
      if(event.type==='keydown'&&event.key==='Escape'){
        event.preventDefault();event.stopPropagation();closeRef.current();return;
      }
      if(event.type==='keydown'&&['ArrowDown','ArrowUp','Home','End'].includes(event.key)
        &&panel.current?.contains(document.activeElement)
        &&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)){
        const choices=Array.from(panel.current.querySelectorAll('[role="menuitem"]'))
          .filter(item=>!item.disabled&&item.getClientRects().length);
        if(choices.length){
          event.preventDefault();event.stopPropagation();
          const current=choices.indexOf(document.activeElement);
          const target=event.key==='Home'?0:event.key==='End'?choices.length-1:
            (current+(event.key==='ArrowDown'?1:-1)+choices.length)%choices.length;
          choices[target].focus();return;
        }
      }
      if(event.type==='pointerdown'&&!panel.current?.contains(event.target))closeRef.current();
      if(event.type==='scroll'&&!panel.current?.contains(event.target))closeRef.current();
    };
    document.addEventListener('pointerdown',close,true);
    document.addEventListener('keydown',close,true);
    document.addEventListener('scroll',close,true);
    const resize=()=>closeRef.current();
    window.addEventListener('resize',resize);
    return()=>{
      cancelAnimationFrame(focusFrame);
      document.removeEventListener('pointerdown',close,true);
      document.removeEventListener('keydown',close,true);
      document.removeEventListener('scroll',close,true);
      window.removeEventListener('resize',resize);
      if(returnFocus.current?.isConnected)returnFocus.current.focus();
    };
  },[request?.id]);
  if(!request)return null;
  return createPortal(<div ref={panel} role="menu" aria-label={'عملیات کارت '+request.title}
    className={'madar-card-context-menu'+(coverOpen?' madar-card-context-menu--cover':'')} dir="rtl"
    style={{left:position?.left??request.x,top:position?.top??request.y,visibility:position?'visible':'hidden'}}>
    <div className="madar-card-context-menu__head"><strong>{request.title}</strong>
      <button type="button" aria-label="بستن منوی کارت" onClick={onClose}><X size={15}/></button></div>
    <button type="button" role="menuitem" onClick={()=>{onClose();onOpen(request.cardId);}}>
      <ExternalLink size={16}/> بازکردن کارت</button>
    {canEdit&&<>
      <div className="madar-card-context-menu__group" aria-label="ویرایش کارت">
        <button type="button" role="menuitem" onClick={()=>{onClose();onOpenSection?.(request.cardId,'tags');}}>
          <Tag size={16}/> ویرایش برچسب‌ها</button>
        <button type="button" role="menuitem" onClick={()=>{onClose();onOpenSection?.(request.cardId,'assignees');}}>
          <Users size={16}/> تغییر مسئولان</button>
        {task&&onCoverChange&&<button type="button" role="menuitem" aria-expanded={coverOpen}
          onClick={()=>setCoverOpen(open=>!open)}><Image size={16}/> کاور و رنگ کارت</button>}
        {coverOpen&&task&&onCoverChange&&<div className="madar-card-context-menu__cover" role="group" aria-label="تنظیم کاور کارت">
          <CardCover task={task} disabled={!canEdit} onChange={changes=>onCoverChange(request.cardId,changes)}/>
        </div>}
        <button type="button" role="menuitem" onClick={()=>{onClose();onOpenSection?.(request.cardId,'metadata');}}>
          <CalendarDays size={16}/> تغییر تاریخ و مشخصات</button>
        <button type="button" role="menuitem" onClick={()=>{onClose();onOpenSection?.(request.cardId,'metadata');}}>
          <Move size={16}/> انتقال به ستون یا برد دیگر</button>
      </div>
      {onToggleComplete&&<button type="button" role="menuitem"
        onClick={()=>{onClose();onToggleComplete(request.cardId);}}>
        <CheckCircle2 size={16}/> {request.completed?'لغو تکمیل کارت':'تکمیل کارت'}</button>}
      {onDuplicate&&<button type="button" role="menuitem" onClick={()=>{onClose();onDuplicate(request.cardId);}}>
        <Copy size={16}/> کپی کارت</button>}
      <div className="madar-card-context-menu__group madar-card-context-menu__danger" aria-label="آرشیو و حذف">
        {onArchive&&<button type="button" role="menuitem" onClick={()=>setPendingDanger('archive')}>
          <Archive size={16}/> بایگانی کارت</button>}
        {onDelete&&<button type="button" role="menuitem" onClick={()=>setPendingDanger('delete')}>
          <Trash2 size={16}/> حذف کارت</button>}
      </div>
      {pendingDanger&&<div className="madar-card-context-menu__confirm" role="group" aria-label="تأیید عملیات کارت">
        <span>{pendingDanger==='archive'?'کارت بایگانی شود؟ قابل بازیابی خواهد بود.':'کارت به زباله‌دان منتقل شود؟ اطلاعات آن حفظ می‌شود.'}</span>
        <div>
          <button type="button" onClick={()=>setPendingDanger(null)}>انصراف</button>
          <button type="button" onClick={()=>{const action=pendingDanger==='archive'?onArchive:onDelete;onClose();action?.(request.cardId);}}>
            {pendingDanger==='archive'?'تأیید بایگانی':'تأیید حذف'}
          </button>
        </div>
      </div>}
    </>}
  </div>,document.body);
}
