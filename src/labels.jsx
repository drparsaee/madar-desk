import React, {useState} from 'react';
import {Plus, X, Pencil, Search, Check} from 'lucide-react';
import {LabelChip, labelColor} from './boardplus.jsx';
import {CommonColorOptions} from './common_color_palette.jsx';
import {coverTextColor} from './cardextras.jsx';
import './labels.css';

const HEX_COLOR = /^#[\da-f]{6}$/i;
const DEFAULT_COLOR = '#64748b';
const MAX_LABELS = 200;
const MAX_NAME = 100;

export const validLabelColor = color => typeof color === 'string' && HEX_COLOR.test(color)
  ? color.toLowerCase() : null;

const nameOf = item => typeof item === 'string'
  ? item : item && typeof item === 'object' && typeof item.name === 'string' ? item.name : '';

const cleanName = value => typeof value === 'string' ? value.trim().slice(0, MAX_NAME) : '';

// Kept separate from task.labels so older LAN clients and task filters still see strings.
// Accepts legacy strings and transitional {name,color} labels without mutating either input.
export function normalizeTaskLabels(labels = [], colors = {}) {
  const names = [];
  const entries = [];
  const seen = new Set();
  const palette = colors && typeof colors === 'object' && !Array.isArray(colors) ? colors : {};
  for (const item of Array.isArray(labels) ? labels : []) {
    const name = cleanName(nameOf(item));
    if (!name || seen.has(name) || names.length === MAX_LABELS) continue;
    seen.add(name);
    const ownColor = item && typeof item === 'object' ? validLabelColor(item.color) : null;
    names.push(name);
    entries.push([name, validLabelColor(palette[name]) || ownColor || labelColor(name)]);
  }
  // fromEntries preserves unusual user labels such as "__proto__" as ordinary keys.
  return {labels: names, labelColors: Object.fromEntries(entries)};
}

// Pure operation helper: prevents duplicate/empty labels and prunes colors on removal.
export function editTaskLabels(labels, colors, {action, index, name, color} = {}) {
  const current = normalizeTaskLabels(labels, colors);
  const currentNames = current.labels;
  const nextColors = {...current.labelColors};
  if (action === 'add' || action === 'rename') {
    const nextName = cleanName(name);
    if (!nextName) return {...current, error: 'empty'};
    if (currentNames.includes(nextName) && (action === 'add' || currentNames[index] !== nextName)) {
      return {...current, error: 'duplicate'};
    }
    if (action === 'add') {
      if (currentNames.length >= MAX_LABELS) return {...current, error: 'limit'};
      return {labels: [...currentNames, nextName], labelColors: {...nextColors,
        [nextName]: validLabelColor(color) || DEFAULT_COLOR}};
    }
    if (!Number.isInteger(index) || index < 0 || index >= currentNames.length) return {...current, error: 'invalid'};
    if (currentNames[index] === nextName) return current;
    const oldName = currentNames[index];
    const previousColor = nextColors[oldName];
    delete nextColors[oldName];
    nextColors[nextName] = previousColor;
    return {labels: currentNames.map((item, i) => i === index ? nextName : item), labelColors: nextColors};
  }
  if (!Number.isInteger(index) || index < 0 || index >= currentNames.length) return {...current, error: 'invalid'};
  if (action === 'remove') {
    delete nextColors[currentNames[index]];
    return {labels: currentNames.filter((_, i) => i !== index), labelColors: nextColors};
  }
  if (action === 'color') {
    const nextColor = validLabelColor(color);
    if (!nextColor) return {...current, error: 'color'};
    return {labels: currentNames, labelColors: {...nextColors, [currentNames[index]]: nextColor}};
  }
  return {...current, error: 'invalid'};
}

// Use this where labels appear on board cards: names stay strings in state.
export function TaskLabelChip({label, colors = {}}) {
  const name = cleanName(nameOf(label));
  if (!name) return null;
  const color = validLabelColor(colors?.[name]) ||
    (label && typeof label === 'object' ? validLabelColor(label.color) : null);
  return <LabelChip label={color ? {name, color} : name}/>;
}

// One catalogue for the system; a checked item belongs ONLY to this card.
// Managing shared definitions is restricted to administrators on LAN.
export function LabelEditor({library=[],labels=[],disabled=false,canManage=false,onToggle,onCreate,onEdit}) {
  const [search,setSearch]=useState('');
  const [newName,setNewName]=useState('');
  const [newColor,setNewColor]=useState(DEFAULT_COLOR);
  const [creating,setCreating]=useState(false);
  const [editing,setEditing]=useState(null);
  const [editName,setEditName]=useState('');
  const [editColor,setEditColor]=useState(DEFAULT_COLOR);
  const [error,setError]=useState('');
  const selected=new Set(labels.map(nameOf));
  const filtered=library.filter(item=>item.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const create=()=>{
    const name=cleanName(newName);
    if(!name||library.some(item=>item.name===name)||library.length>=MAX_LABELS){
      setError('نام برچسب خالی، تکراری یا کتابخانه پر است.');return;
    }
    onCreate?.({name,color:newColor});
    setNewName('');setNewColor(DEFAULT_COLOR);setCreating(false);setError('');
  };
  const saveEdit=()=>{
    if(!editing)return;
    const name=cleanName(editName);
    if(!name||library.some(item=>item.id!==editing&&item.name===name)){
      setError('نام برچسب خالی یا تکراری است.');return;
    }
    onEdit?.({id:editing,name,color:editColor});
    setEditing(null);setError('');
  };
  return <div className="label-editor" dir="rtl" aria-label="کتابخانه برچسب‌های مشترک">
    <label className="label-editor-search"><Search size={15}/>
      <input type="search" aria-label="جست‌وجوی برچسب‌ها" placeholder="جست‌وجوی برچسب..." value={search}
        onChange={event=>setSearch(event.target.value)}/></label>
    <div className="label-editor-list">
      {filtered.map(item=><div className="label-editor-row" key={item.id}>
        <label className="label-editor-option">
          <input type="checkbox" disabled={disabled} aria-label={'انتخاب برچسب '+item.name}
            checked={selected.has(item.name)} onChange={event=>onToggle?.(item.id,event.target.checked)}/>
          <span className="label-editor-swatch" style={{backgroundColor:item.color,color:coverTextColor(item.color)}}>{item.name}</span>
        </label>
        {canManage&&<button type="button" className="label-editor-edit" aria-label={'ویرایش برچسب '+item.name}
          onClick={()=>{setEditing(editing===item.id?null:item.id);setEditName(item.name);setEditColor(item.color);setError('');}}>
          <Pencil size={15}/></button>}
        {editing===item.id&&canManage&&<div className="label-editor-editpanel">
          <input aria-label={'نام جدید برچسب '+item.name} value={editName} maxLength={MAX_NAME}
            onChange={event=>setEditName(event.target.value)}
            onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();saveEdit();}}}/>
          <CommonColorOptions label={'رنگ برچسب '+item.name} value={editColor} onChange={setEditColor}/>
          <button type="button" onClick={saveEdit}><Check size={14}/> ذخیره</button>
        </div>}
      </div>)}
      {!filtered.length&&<small className="label-editor-empty">برچسبی پیدا نشد.</small>}
    </div>
    {canManage&&<div className="label-editor-create">
      {creating?<div className="label-editor-editpanel">
        <input type="text" aria-label="نام برچسب جدید" maxLength={MAX_NAME} value={newName}
          placeholder="نام برچسب جدید..." onChange={event=>setNewName(event.target.value)}
          onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();create();}}}/>
        <CommonColorOptions label="برچسب جدید" value={newColor} onChange={setNewColor}/>
        <button type="button" disabled={!newName.trim()} aria-label="افزودن برچسب" onClick={create}><Plus size={14}/> ایجاد</button>
        <button type="button" aria-label="انصراف از ساخت برچسب" onClick={()=>setCreating(false)}><X size={15}/></button>
      </div>:
        <button type="button" className="label-editor-create-button" onClick={()=>setCreating(true)}><Plus size={15}/> ساخت برچسب مشترک</button>}
    </div>}
    {!!error&&<small role="alert" className="label-editor-error">{error}</small>}
  </div>;
}
