import React, {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {Archive, ArrowLeft, ArrowRight, Check, Ellipsis, Palette, Plus, Settings2, X} from 'lucide-react';

const inset = 8;
export function lanePopupPosition(anchor, popup, width, height) {
  const w = Math.min(Math.max(220, popup.width || 280), Math.max(220, width - inset * 2));
  const h = Math.min(popup.height || 300, Math.max(120, height - inset * 2));
  return {
    left: Math.max(inset, Math.min(width - inset - w, anchor.left)),
    top: anchor.bottom + h + inset > height
      ? Math.max(inset, anchor.top - h - 5)
      : Math.max(inset, anchor.bottom + 5),
  };
}

/**
 * Each board list owns its configuration. Popup is rendered through a portal,
 * not into the horizontally scrolling board, to prevent CSS overflow clipping.
 * This is presentation only: the parent performs permission checks and changes.
 */
export function LaneActionsMenu({
  stage, count, canManage, canEdit, index, total, onSave,
  onMove, onArchive, onAddCard,
}) {
  const [open,setOpen]=useState(false);
  const [name,setName]=useState(stage.label);
  const [subtitle,setSubtitle]=useState(stage.subtitle||'');
  const [position,setPosition]=useState(null);
  const trigger=useRef(null);
  const panel=useRef(null);
  const id='lane-actions-'+stage.id.replace(/[^a-zA-Z0-9_-]/g,'_');
  const openMenu=()=>{
    setName(stage.label);
    setSubtitle(stage.subtitle||'');
    setPosition(null);
    setOpen(v=>!v);
  };
  const closeMenu=()=>setOpen(false);
  useEffect(()=>{
    if(!open)return;
    const close=e=>{
      if(e.type==='keydown'&&e.key==='Escape'){
        e.preventDefault();e.stopPropagation();closeMenu();trigger.current?.focus();return;
      }
      if((e.type==='pointerdown'||e.type==='focusin') &&
         !panel.current?.contains(e.target)&&!trigger.current?.contains(e.target))closeMenu();
    };
    document.addEventListener('pointerdown',close,true);
    document.addEventListener('focusin',close,true);
    document.addEventListener('keydown',close,true);
    return()=>{
      document.removeEventListener('pointerdown',close,true);
      document.removeEventListener('focusin',close,true);
      document.removeEventListener('keydown',close,true);
    };
  },[open]);
  useLayoutEffect(()=>{
    if(!open||!trigger.current||!panel.current)return;
    let frame=0;
    const update=()=>{
      const a=trigger.current?.getBoundingClientRect(),p=panel.current?.getBoundingClientRect();
      if(a&&p){
        const next=lanePopupPosition(a,p,window.innerWidth,window.innerHeight);
        setPosition(prev=>prev?.left===next.left&&prev?.top===next.top?prev:next);
      }
    };
    const schedule=()=>{
      if(frame)return;
      frame=requestAnimationFrame(()=>{frame=0;update();});
    };
    update();
    window.addEventListener('resize',schedule);
    document.addEventListener('scroll',schedule,true);
    return()=>{
      if(frame)cancelAnimationFrame(frame);
      window.removeEventListener('resize',schedule);
      document.removeEventListener('scroll',schedule,true);
    };
  },[open]);
  const save=e=>{
    e.preventDefault();
    if(!canManage||!name.trim())return;
    onSave?.({label:name.trim(),subtitle:subtitle.trim()});
    closeMenu();
    trigger.current?.focus();
  };
  return <>
    <button ref={trigger} type="button" className="lane-menu-trigger"
      aria-label={'عملیات ستون '+stage.label} title={'تنظیمات '+stage.label}
      aria-haspopup="dialog" aria-expanded={open} aria-controls={open?id:undefined}
      onClick={openMenu}><Ellipsis size={19}/></button>
    {open&&typeof document!=='undefined'&&createPortal(
      <div ref={panel} id={id} role="dialog" aria-label={'تنظیمات ستون '+stage.label}
        className="lane-actions-popover" dir="rtl"
        style={position?{left:position.left,top:position.top,visibility:'visible'}:{left:inset,top:inset,visibility:'hidden'}}>
        <div className="lane-actions-popover__head"><strong>عملیات ستون</strong>
          <button type="button" aria-label="بستن عملیات ستون" onClick={closeMenu}><X size={16}/></button>
        </div>
        <button type="button" className="lane-actions-popover__action" disabled={!canEdit}
          onClick={()=>{closeMenu();onAddCard?.();}}><Plus size={16}/> افزودن کارت</button>
        {canManage&&<>
          <form className="lane-actions-popover__editor" onSubmit={save}>
            <label>نام ستون
              <input maxLength={100} value={name} onChange={e=>setName(e.target.value)} required/>
            </label>
            <label>توضیح کوتاه
              <input maxLength={180} value={subtitle} onChange={e=>setSubtitle(e.target.value)}/>
            </label>
            <button type="submit" className="lane-actions-popover__save" disabled={!name.trim()}><Check size={15}/> ذخیره تغییرات</button>
          </form>
          <label className="lane-actions-popover__color"><Palette size={16}/> رنگ ستون
            <input type="color" aria-label={'رنگ ستون '+stage.label} value={/^#[0-9a-f]{6}$/i.test(stage.color)?stage.color:'#64748b'}
              onChange={e=>onSave?.({color:e.target.value})}/>
          </label>
          <div className="lane-actions-popover__moves" role="group" aria-label="جابجایی ستون">
            <button type="button" disabled={index===0} onClick={()=>{onMove?.(-1);closeMenu();}}><ArrowRight size={15}/> یک ستون به راست</button>
            <button type="button" disabled={index>=total-1} onClick={()=>{onMove?.(1);closeMenu();}}><ArrowLeft size={15}/> یک ستون به چپ</button>
          </div>
          {onArchive&&<button type="button" className="lane-actions-popover__action lane-actions-popover__archive"
            disabled={total<=1} onClick={()=>{closeMenu();onArchive?.();}}>
            <Archive size={16}/> بایگانی ستون {count>0&&<small>({count.toLocaleString('fa-IR')} کارت حفظ می‌شود)</small>}
          </button>}
          {!onArchive&&<p className="lane-actions-popover__hint">این ستون در نمای سراسری است. بایگانی بدون حذف کارت‌ها در برد اختصاصی در دسترس است.</p>}
        </>}
        {!canManage&&<small className="lane-actions-popover__hint"><Settings2 size={14}/> تنظیم ستون فقط برای مدیر مجاز است.</small>}
      </div>,document.body)}
  </>;
}
