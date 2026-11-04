import React, {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {Archive, CheckCircle2, Copy, ExternalLink, Image, Move, Tag, Trash2, Users, CalendarDays, X} from 'lucide-react';
import {laneContextPopupPosition} from './board_lane_actions.jsx';

/** Context actions on an individual card. Caller owns permission checks. */
export function CardContextMenu({request,onClose,onOpen,onOpenSection,onDuplicate,onArchive,onDelete,
  onToggleComplete,canEdit=false}) {
  const panel=useRef(null);
  const [position,setPosition]=useState(null);
  const [pendingDanger,setPendingDanger]=useState(null);
  useEffect(()=>setPendingDanger(null),[request?.id]);
  useLayoutEffect(()=>{
    if(!request||!panel.current)return;
    const bounds=panel.current.getBoundingClientRect();
    setPosition(laneContextPopupPosition(request,bounds,window.innerWidth,window.innerHeight));
  },[request]);
  useEffect(()=>{
    if(!request)return;
    const close=event=>{
      if(event.type==='keydown'&&event.key==='Escape'){
        event.preventDefault();event.stopPropagation();onClose();return;
      }
      if(event.type==='pointerdown'&&!panel.current?.contains(event.target))onClose();
      if(event.type==='scroll')onClose();
    };
    document.addEventListener('pointerdown',close,true);
    document.addEventListener('keydown',close,true);
    document.addEventListener('scroll',close,true);
    window.addEventListener('resize',onClose);
    return()=>{
      document.removeEventListener('pointerdown',close,true);
      document.removeEventListener('keydown',close,true);
      document.removeEventListener('scroll',close,true);
      window.removeEventListener('resize',onClose);
    };
  },[request,onClose]);
  if(!request)return null;
  return createPortal(<div ref={panel} role="menu" aria-label={'عملیات کارت '+request.title}
    className="madar-card-context-menu" dir="rtl"
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
        <button type="button" role="menuitem" onClick={()=>{onClose();onOpenSection?.(request.cardId,'cover');}}>
          <Image size={16}/> تغییر کاور</button>
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
