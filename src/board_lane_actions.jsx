import React, {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {Archive, ArrowLeft, ArrowRight, Check, ChevronsDownUp, ChevronsUpDown, Copy, Ellipsis, ListFilter, Palette, Plus, Settings2, X, Zap} from 'lucide-react';
import {CommonColorOptions} from './common_color_palette.jsx';

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

export function laneContextPopupPosition(point, popup, width, height) {
  const w = Math.min(popup.width || 280, Math.max(0, width - inset * 2));
  const h = Math.min(popup.height || 300, Math.max(0, height - inset * 2));
  const preferredTop = point.y + h + inset <= height ? point.y : point.y - h - 5;
  return {
    left: Math.max(inset, Math.min(width - inset - w, point.x)),
    top: Math.max(inset, Math.min(height - inset - h, preferredTop)),
  };
}

/**
 * Each board list owns its configuration. Popup is rendered through a portal,
 * not into the horizontally scrolling board, to prevent CSS overflow clipping.
 * This is presentation only: the parent performs permission checks and changes.
 */
export function LaneActionsMenu({
  stage, count, canManage, canEdit, index, total, onSave,
  onMove, onArchive, onCopyList, onAddCard, onAddCardTop, onToggleCollapse,
  onSort, onMoveAll, moveTargets=[], onAutomation,
  contextRequest, onContextConsumed, collapsed=false,
}) {
  const [open,setOpen]=useState(false);
  const [name,setName]=useState(stage.label);
  const [subtitle,setSubtitle]=useState(stage.subtitle||'');
  const [position,setPosition]=useState(null);
  const [contextPoint,setContextPoint]=useState(null);
  const trigger=useRef(null);
  const panel=useRef(null);
  const id='lane-actions-'+stage.id.replace(/[^a-zA-Z0-9_-]/g,'_');
  const openMenu=()=>{
    setName(stage.label);
    setSubtitle(stage.subtitle||'');
    setContextPoint(null);
    setPosition(null);
    setOpen(v=>!v);
  };
  const closeMenu=()=>setOpen(false);
  useEffect(()=>{
    if((contextRequest?.stageId??contextRequest?.id)!==stage.id||
       !Number.isFinite(contextRequest.x)||!Number.isFinite(contextRequest.y))return;
    setName(stage.label);
    setSubtitle(stage.subtitle||'');
    setContextPoint({x:contextRequest.x,y:contextRequest.y});
    setPosition(null);
    setOpen(true);
    // A right-click request is one-shot. Without acknowledgment, collapsing
    // swaps lane-menu components and replays the old request on remount.
    onContextConsumed?.(contextRequest.id);
  },[contextRequest,stage.id]);
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
    if(!open||!panel.current||(!contextPoint&&!trigger.current))return;
    let frame=0;
    const update=()=>{
      const a=contextPoint||trigger.current?.getBoundingClientRect();
      const p=panel.current?.getBoundingClientRect();
      if(a&&p){
        const next=contextPoint
          ?laneContextPopupPosition(contextPoint,p,window.innerWidth,window.innerHeight)
          :lanePopupPosition(a,p,window.innerWidth,window.innerHeight);
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
  },[open,contextPoint]);
  const save=e=>{
    e.preventDefault();
    if(!canManage||!onSave||!name.trim())return;
    onSave?.({label:name.trim(),subtitle:subtitle.trim()});
    closeMenu();
    trigger.current?.focus();
  };
  return <>
    <button ref={trigger} type="button" className="lane-menu-trigger"
      aria-label={'عملیات لیست '+stage.label} title={'عملیات لیست '+stage.label}
      aria-haspopup="dialog" aria-expanded={open} aria-controls={open?id:undefined}
      onClick={openMenu}><Ellipsis size={19}/></button>
    {open&&typeof document!=='undefined'&&createPortal(
      <div ref={panel} id={id} role="dialog" aria-label={'تنظیمات ستون '+stage.label}
        className="lane-actions-popover" dir="rtl"
        style={position?{left:position.left,top:position.top,visibility:'visible'}:{left:inset,top:inset,visibility:'hidden'}}>
        <div className="lane-actions-popover__head"><strong>عملیات لیست · {stage.label}</strong>
          <button type="button" aria-label="بستن عملیات ستون" onClick={closeMenu}><X size={16}/></button>
        </div>
        <button type="button" className="lane-actions-popover__action" disabled={!canEdit||!onAddCard}
          onClick={()=>{if(!canEdit||!onAddCard)return;closeMenu();onAddCard();}}><Plus size={16}/> افزودن کارت</button>
        <button type="button" className="lane-actions-popover__action" disabled={!canEdit||!onAddCardTop}
          onClick={()=>{if(!canEdit||!onAddCardTop)return;closeMenu();onAddCardTop();}}><Plus size={16}/> افزودن کارت در ابتدای ستون</button>
        {canManage&&<button type="button" className="lane-actions-popover__action" disabled={!onCopyList}
          title="ساخت نسخه خالی از ستون؛ کارت‌ها و اطلاعات مالی کپی نمی‌شوند"
          onClick={()=>{if(!onCopyList)return;closeMenu();onCopyList();}}><Copy size={16}/> کپی ستون خالی</button>}
        <button type="button" className="lane-actions-popover__action" disabled={!onToggleCollapse}
          onClick={()=>{if(!onToggleCollapse)return;closeMenu();onToggleCollapse();}}>
          {collapsed?<ChevronsUpDown size={16}/>:<ChevronsDownUp size={16}/>}
          {collapsed?'بازکردن ستون':'جمع‌کردن ستون'}
        </button>
        <details className="lane-actions-popover__group">
          <summary><ListFilter size={16}/> مرتب‌سازی کارت‌ها</summary>
          <div className="lane-actions-popover__choices">
            {[['newest','جدیدترین'],['oldest','قدیمی‌ترین'],['title','عنوان الفبایی'],['due','نزدیک‌ترین موعد']].map(([value,label])=><button key={value} type="button"
              disabled={!canEdit||!onSort} onClick={()=>{if(!canEdit||!onSort)return;closeMenu();onSort(value);}}>{label}</button>)}
          </div>
        </details>
        {canManage&&<details className="lane-actions-popover__group">
          <summary><ArrowLeft size={16}/> انتقال تمام کارت‌های لیست</summary>
          <div className="lane-actions-popover__choices">
            {moveTargets.length?moveTargets.map(target=><button type="button" key={target.id}
              disabled={!onMoveAll} onClick={()=>{if(!onMoveAll)return;closeMenu();onMoveAll(target.id);}}>
              انتقال به {target.label}</button>):<small>لیست مقصد دیگری وجود ندارد.</small>}
          </div>
        </details>}
        {canManage&&onAutomation&&<button type="button" className="lane-actions-popover__action"
          onClick={()=>{closeMenu();onAutomation();}}><Zap size={16}/> اتوماسیون لیست</button>}
        {canManage&&<>
          <details className="lane-actions-popover__group">
            <summary><Palette size={16}/> نام، توضیح و رنگ لیست</summary>
          <form className="lane-actions-popover__editor" onSubmit={save}>
            <label>نام ستون
              <input maxLength={100} value={name} onChange={e=>setName(e.target.value)} required/>
            </label>
            <label>توضیح کوتاه
              <input maxLength={180} value={subtitle} onChange={e=>setSubtitle(e.target.value)}/>
            </label>
            <button type="submit" className="lane-actions-popover__save" disabled={!onSave||!name.trim()}><Check size={15}/> ذخیره تغییرات</button>
          </form>
          <CommonColorOptions value={stage.color} disabled={!onSave} label={'ستون '+stage.label} onChange={color=>onSave?.({color})}/>
          </details>
          <div className="lane-actions-popover__moves" role="group" aria-label="جابجایی ستون">
            <button type="button" disabled={!onMove||index===0} onClick={()=>{onMove?.(-1);closeMenu();}}><ArrowRight size={15}/> یک ستون به راست</button>
            <button type="button" disabled={!onMove||index>=total-1} onClick={()=>{onMove?.(1);closeMenu();}}><ArrowLeft size={15}/> یک ستون به چپ</button>
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
