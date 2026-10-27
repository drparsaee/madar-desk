import React, {useEffect,useRef,useState} from 'react';
import {Check,Clock3,Settings2} from 'lucide-react';
import {CLOCK_WIDGET_CHOICES,normalizeClockWidget} from './clock_widget.js';
import './clock_widget.css';

/** User-controlled, persistently configurable visual widget in the task toolbar. */
export function ClockWidget({calendar='jalali',mode='both',onChange,disabled=false}){
  const [current,setCurrent]=useState(()=>new Date());
  const [open,setOpen]=useState(false);
  const holder=useRef(null);
  const choice=normalizeClockWidget(mode);
  useEffect(()=>{
    const interval=setInterval(()=>setCurrent(new Date()),1000);
    return ()=>clearInterval(interval);
  },[]);
  useEffect(()=>{
    if(!open)return;
    const close=e=>{
      if(e.key==='Escape')setOpen(false);
      else if(e.type==='pointerdown'&&!holder.current?.contains(e.target))setOpen(false);
    };
    document.addEventListener('keydown',close);
    document.addEventListener('pointerdown',close);
    return ()=>{document.removeEventListener('keydown',close);document.removeEventListener('pointerdown',close);};
  },[open]);
  const locale=calendar==='jalali'?'fa-IR-u-ca-persian':'fa-IR-u-ca-gregory';
  const date=new Intl.DateTimeFormat(locale,{weekday:'long',year:'numeric',month:'long',day:'numeric'}).format(current);
  const hour=new Intl.DateTimeFormat('fa-IR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(current);
  return <div className="clock-widget" ref={holder} dir="rtl">
    {choice!=='hidden'&&<div className={'live-clock clock-widget__display clock-widget__display--'+choice}
      role="timer" aria-label={choice==='both'?'ساعت و تاریخ دستگاه':choice==='date'?'تاریخ دستگاه':'ساعت دستگاه'}>
      {choice!=='date'&&<strong dir="ltr">{hour}</strong>}
      {choice!=='clock'&&<span>{date}</span>}
    </div>}
    <button type="button" className="top-icon clock-widget__trigger" title="تنظیم ویجت ساعت و تاریخ"
      aria-label="تنظیم ویجت ساعت و تاریخ" aria-haspopup="true" aria-expanded={open}
      onClick={()=>setOpen(value=>!value)}><Clock3 size={18}/><Settings2 size={10}/></button>
    {open&&<div className="clock-widget__menu" role="group" aria-label="نوع نمایش ساعت و تاریخ">
      <strong>نمایش ساعت و تاریخ</strong>
      <p>انتخاب شما روی همین دستگاه ذخیره می‌شود.</p>
      {CLOCK_WIDGET_CHOICES.map(item=><button key={item.id} type="button"
        className={item.id===choice?'selected':''}
        aria-pressed={item.id===choice} disabled={disabled}
        onClick={()=>{onChange?.(item.id);setOpen(false);}}>
        {item.label}{item.id===choice&&<Check size={15}/>}</button>)}
    </div>}
  </div>;
}
