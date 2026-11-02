import React, {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {Archive, ExternalLink, X} from 'lucide-react';
import {laneContextPopupPosition} from './board_lane_actions.jsx';

/** Context actions on an individual card. Caller owns permission checks. */
export function CardContextMenu({request,onClose,onOpen,onArchive,canEdit=false}) {
  const panel=useRef(null);
  const [position,setPosition]=useState(null);
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
    {canEdit&&<button type="button" role="menuitem" onClick={()=>{onClose();onArchive(request.cardId);}}>
      <Archive size={16}/> بایگانی کارت</button>}
  </div>,document.body);
}
