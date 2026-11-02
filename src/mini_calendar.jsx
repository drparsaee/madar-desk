import React,{useEffect,useMemo,useState} from 'react';
import {ChevronLeft,ChevronRight} from 'lucide-react';
import {fromJalali,jalaliDigits} from './productivity.jsx';
import {localTodayISO} from './calendar_today.js';

const ISO_DATE=/^\d{4}-\d{2}-\d{2}$/;
const pad=n=>String(n).padStart(2,'0');
const isoUTC=date=>date.toISOString().slice(0,10);
const dateUTC=iso=>new Date(iso+'T12:00:00Z');
const partsFromISO=(iso,calendar)=>{
  if(calendar==='jalali')return jalaliDigits(dateUTC(iso)).split('/').map(Number);
  return iso.split('-').map(Number);
};
const monthStart=(year,month,calendar)=>
  calendar==='jalali'?fromJalali(year+'/'+pad(month)+'/01'):
  year+'-'+pad(month)+'-01';

/** Small click-to-select month calendar. Outputs only validated Gregorian ISO dates. */
export function MiniCalendar({id,value,calendar='jalali',onSelect,onClose,popupRef,popupStyle}) {
  const today=localTodayISO();
  const initial=ISO_DATE.test(value||'')?value:today;
  const [visible,setVisible]=useState(()=>partsFromISO(initial,calendar).slice(0,2));
  useEffect(()=>setVisible(partsFromISO(initial,calendar).slice(0,2)),[calendar]);
  const [year,month]=visible;
  const first=monthStart(year,month,calendar);
  const days=useMemo(()=>{
    if(!first)return [];
    const base=dateUTC(first);
    const offset=(base.getUTCDay()+1)%7; // Saturday is first
    return Array.from({length:42},(_,index)=>{
      const current=new Date(base.getTime()+(index-offset)*86400000);
      const date=isoUTC(current);
      const [candidateYear,candidateMonth,candidateDay]=partsFromISO(date,calendar);
      return {date,day:candidateDay,inside:candidateYear===year&&candidateMonth===month};
    });
  },[first,year,month,calendar]);
  const changeMonth=step=>{
    let nextYear=year,nextMonth=month+step;
    if(nextMonth<1){nextYear--;nextMonth=12;}
    if(nextMonth>12){nextYear++;nextMonth=1;}
    if(monthStart(nextYear,nextMonth,calendar))setVisible([nextYear,nextMonth]);
  };
  const monthLabel=first?new Intl.DateTimeFormat(
    calendar==='jalali'?'fa-IR-u-ca-persian':'fa-IR-u-ca-gregory',
    {month:'long',year:'numeric',timeZone:'UTC'}
  ).format(dateUTC(first)):'';
  return <div id={id} ref={popupRef} style={popupStyle} className="madar-mini-calendar" role="group" aria-label="تقویم انتخاب تاریخ" dir="rtl">
    <div className="madar-mini-calendar__head">
      <button type="button" aria-label="ماه قبل" onClick={()=>changeMonth(-1)}><ChevronRight size={16}/></button>
      <strong>{monthLabel}</strong>
      <button type="button" aria-label="ماه بعد" onClick={()=>changeMonth(1)}><ChevronLeft size={16}/></button>
    </div>
    <div className="madar-mini-calendar__days">
      {['ش','ی','د','س','چ','پ','ج'].map((name,index)=><span key={index} className="madar-mini-calendar__weekday">{name}</span>)}
      {days.map(day=><button key={day.date} type="button" className={
        (day.inside?'':'madar-mini-calendar__outside ')+(day.date===value?'madar-mini-calendar__selected ':'')+
        (day.date===today?'madar-mini-calendar__today':'')
      } aria-label={'انتخاب '+day.date} aria-pressed={day.date===value} onClick={()=>{onSelect(day.date);onClose?.();}}>
        {Number(day.day).toLocaleString('fa-IR')}
      </button>)}
    </div>
    <div className="madar-mini-calendar__foot">
      <button type="button" onClick={()=>{onSelect(today);onClose?.();}}>امروز</button>
      <button type="button" onClick={()=>{onSelect('');onClose?.();}}>پاک‌کردن تاریخ</button>
    </div>
  </div>;
}
