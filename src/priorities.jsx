import React,{useState} from 'react';
import {Flag,Plus,Trash2} from 'lucide-react';
import {DEFAULT_PRIORITIES,PRIORITY_EFFECTS,priorityDefs} from './priorities.js';
import {CommonColorOptions} from './common_color_palette.jsx';
import './priorities.css';

export function PrioritySettings({settings,usedIds=[],onChange,canManage=true}){
  const definitions=priorityDefs(settings);
  const [name,setName]=useState('');
  const [draftNames,setDraftNames]=useState({});
  const [warning,setWarning]=useState('');
  const update=(id,fields)=>{
    if(!canManage)return;
    onChange(definitions.map(p=>p.id===id?{...p,...fields}:p));
  };
  const add=()=>{
    if(!canManage||!name.trim()||definitions.length>=30)return;
    const id='p-'+Math.random().toString(36).slice(2,11);
    onChange([...definitions,{id,label:name.trim().slice(0,60),color:'#6d65df',effect:'none'}]);
    setName('');setWarning('');
  };
  const remove=id=>{
    if(DEFAULT_PRIORITIES.some(x=>x.id===id))return;
    if(usedIds.includes(id)){setWarning('این اولویت روی کارت استفاده می‌شود. قبل از حذف، اولویت کارت‌های مرتبط را تغییر دهید.');return;}
    onChange(definitions.filter(p=>p.id!==id));setWarning('');
  };
  return <div className="setting-block priority-settings">
    <h3><Flag size={17}/> تعریف و شخصی‌سازی اولویت‌ها</h3>
    <p>برای هر اولویت یک نام، رنگ و جلوه انتخاب کنید. حرکات در تنظیم «کاهش حرکت» سیستم متوقف می‌شوند.</p>
    <div className="priority-definition-list">
      {definitions.map(p=><div key={p.id} className="priority-definition" style={{'--priority-color':p.color}}>
        <div className={'priority-demo priority-effect-'+p.effect}><Flag size={16}/><span>{p.label}</span></div>
        <label>نام<input aria-label={'نام اولویت '+p.label} maxLength={60} disabled={!canManage} value={draftNames[p.id]??p.label} onChange={e=>setDraftNames(current=>({...current,[p.id]:e.target.value}))} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();e.currentTarget.blur();}}} onBlur={e=>{const label=e.target.value.trim();if(label&&label!==p.label)update(p.id,{label});setDraftNames(current=>{const next={...current};delete next[p.id];return next;});}}/></label>
        <div className="priority-color-cell">
          <CommonColorOptions value={p.color} disabled={!canManage} label={'اولویت '+p.label} onChange={color=>update(p.id,{color})}/>
        </div>
        <label>موشن<select aria-label={'جلوه اولویت '+p.label} disabled={!canManage} value={p.effect} onChange={e=>update(p.id,{effect:e.target.value})}>{PRIORITY_EFFECTS.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        {!DEFAULT_PRIORITIES.some(item=>item.id===p.id)&&<button type="button" disabled={!canManage} aria-label={'حذف اولویت '+p.label} onClick={()=>remove(p.id)}><Trash2 size={16}/></button>}
      </div>)}
    </div>
    {canManage&&<div className="priority-new"><input maxLength={60} value={name} placeholder="نام اولویت جدید، مثلاً فوری" aria-label="اولویت جدید" onChange={e=>setName(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();add();}}}/><button disabled={!name.trim()||definitions.length>=30} type="button" className="btn primary" onClick={add}><Plus size={16}/> تعریف اولویت</button></div>}
    {warning&&<p role="alert" className="priority-warning">{warning}</p>}
  </div>;
}
