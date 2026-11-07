import React, {useEffect, useState} from 'react';
import {Plus, X, Pencil, Search, Check, ArrowRight, Trash2} from 'lucide-react';
import {LabelChip, labelColor} from './boardplus.jsx';
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

// Six rows and five columns, in the same compact order as Trello's label picker.
// Any existing custom HEX value is also preserved by the native color input.
export const LABEL_PALETTE = Object.freeze([
  '#baf3db','#f8e6a0','#fedec8','#ffd5d2','#dfd8fd',
  '#7ee2b8','#f5cd47','#fea362','#f87168','#b8acf6',
  '#4bce97','#e2b203','#fe8a4b','#e2483d','#9f8fef',
  '#1f845a','#946f00','#c25100','#ae2a19','#6e5dc6',
  '#216e4e','#7f5f01','#a54800','#942a09','#5243aa',
  '#164b35','#533f04','#702e00','#5d1f11','#352c63'
]);

// Selection belongs to the current card; the catalogue and edits are global.
// labels={null} switches to the same editor in management-only mode.
export function LabelEditor({library=[],labels=[],disabled=false,canManage=false,manageOnly=false,
  initialEditId=null,onToggle,onCreate,onEdit,onDelete,onClose}) {
  const [screen,setScreen]=useState(initialEditId&&canManage?'edit':'list');
  const [editingId,setEditingId]=useState(initialEditId);
  const initial=library.find(item=>item.id===initialEditId);
  const [name,setName]=useState(initial?.name||'');
  const [color,setColor]=useState(validLabelColor(initial?.color)||DEFAULT_COLOR);
  const [search,setSearch]=useState('');
  const [confirmDelete,setConfirmDelete]=useState(false);
  const [error,setError]=useState('');
  const selectionEnabled=Array.isArray(labels)&&!manageOnly;
  const selected=new Set(selectionEnabled?labels.map(nameOf):[]);
  const filtered=library.filter(item=>item.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const editing=library.find(item=>item.id===editingId);

  useEffect(()=>{
    if(!initialEditId||!canManage)return;
    const item=library.find(entry=>entry.id===initialEditId);
    if(!item)return;
    setEditingId(item.id);setName(item.name);
    setColor(validLabelColor(item.color)||DEFAULT_COLOR);
    setScreen('edit');setConfirmDelete(false);setError('');
  },[initialEditId,canManage]);

  const list=()=>{setScreen('list');setEditingId(null);setConfirmDelete(false);setError('');};
  const openEdit=item=>{
    setEditingId(item.id);setName(item.name);
    setColor(validLabelColor(item.color)||DEFAULT_COLOR);
    setConfirmDelete(false);setError('');setScreen('edit');
  };
  const openCreate=()=>{
    setEditingId(null);setName('');setColor(DEFAULT_COLOR);
    setConfirmDelete(false);setError('');setScreen('create');
  };
  const save=event=>{
    event.preventDefault();
    const nextName=cleanName(name);
    if(!nextName||library.some(item=>item.id!==editingId&&item.name===nextName)||
        (screen==='create'&&library.length>=MAX_LABELS)){
      setError('نام برچسب خالی، تکراری یا کتابخانه پر است.');return;
    }
    try{
      if(screen==='edit')onEdit?.({id:editingId,name:nextName,color});
      else onCreate?.({name:nextName,color});
      list();
    }catch(failure){setError(failure?.message||'ذخیره برچسب انجام نشد.');}
  };
  const remove=()=>{
    if(!editingId||!onDelete)return;
    try{onDelete({id:editingId});list();}
    catch(failure){setError(failure?.message||'حذف برچسب انجام نشد.');}
  };
  const detail=screen==='edit'||screen==='create';
  return <section className="label-editor" dir="rtl" aria-label="مدیریت برچسب‌ها"
    onKeyDown={event=>{if(event.key==='Escape'&&detail){event.stopPropagation();list();}}}>
    <header className="label-editor-header">
      {detail?<button type="button" className="label-editor-back" aria-label="بازگشت به فهرست برچسب‌ها" onClick={list}>
        <ArrowRight size={16}/></button>:null}
      <h3>{screen==='edit'?'ویرایش برچسب':screen==='create'?'ساخت برچسب':'برچسب‌ها'}</h3>
      {screen==='edit'&&canManage&&onDelete&&<button type="button"
        className="label-editor-delete label-editor-delete--header"
        aria-expanded={confirmDelete} aria-controls="label-editor-delete-confirm"
        onClick={()=>setConfirmDelete(value=>!value)}><Trash2 size={15}/> حذف برچسب</button>}
      {onClose&&<button type="button" className="label-editor-close" aria-label="بستن مدیریت برچسب‌ها" onClick={onClose}>
        <X size={16}/></button>}
    </header>
    {confirmDelete&&screen==='edit'&&canManage&&onDelete&&<div id="label-editor-delete-confirm"
      className="label-editor-confirm" role="group" aria-label="تأیید حذف برچسب">
      <p>این برچسب از همهٔ کارت‌ها حذف می‌شود. حذف برچسب را تأیید می‌کنید؟</p>
      <div className="label-editor-confirm-actions">
        <button type="button" onClick={()=>setConfirmDelete(false)}>انصراف</button>
        <button type="button" className="label-editor-delete" onClick={remove}>حذف از همهٔ کارت‌ها</button>
      </div>
    </div>}
    {!detail?<>
      <label className="label-editor-search"><Search size={15} aria-hidden="true"/>
        <input type="search" aria-label="جست‌وجوی برچسب‌ها" placeholder="جست‌وجوی برچسب..." value={search}
          onChange={event=>setSearch(event.target.value)}/></label>
      <div className="label-editor-list">
        {filtered.map(item=><div className={'label-editor-row'+(!canManage?' label-editor-row--readonly':'')} key={item.id}>
          {selectionEnabled?<label className="label-editor-option">
            <input type="checkbox" disabled={disabled||!onToggle} aria-label={'انتخاب برچسب '+item.name}
              checked={selected.has(item.name)} onChange={event=>onToggle?.(item.id,event.target.checked)}/>
            <span className="label-editor-swatch" style={{backgroundColor:validLabelColor(item.color)||DEFAULT_COLOR,
              color:coverTextColor(validLabelColor(item.color)||DEFAULT_COLOR)}}>{item.name}</span>
          </label>:<span className="label-editor-swatch" style={{backgroundColor:validLabelColor(item.color)||DEFAULT_COLOR,
            color:coverTextColor(validLabelColor(item.color)||DEFAULT_COLOR)}}>{item.name}</span>}
          {canManage&&<button type="button" className="label-editor-edit" aria-label={'ویرایش برچسب '+item.name}
            onClick={()=>openEdit(item)}><Pencil size={16}/></button>}
        </div>)}
        {!filtered.length&&<small className="label-editor-empty">برچسبی پیدا نشد.</small>}
      </div>
      {canManage&&<button type="button" className="label-editor-create-button" onClick={openCreate}>
        <Plus size={16}/> ساخت برچسب</button>}
    </>:canManage?<form className="label-editor-form" onSubmit={save}>
      <div className="label-editor-field-title">پیش‌نمایش</div>
      <div className="label-editor-preview" style={{backgroundColor:color,color:coverTextColor(color)}}>
        {name.trim()||'نام برچسب'}</div>
      <label className="label-editor-name">عنوان
        <input type="text" autoFocus maxLength={MAX_NAME} aria-label={screen==='edit'?'نام جدید برچسب '+(editing?.name||''):'نام برچسب جدید'}
          placeholder="عنوان برچسب" value={name} onChange={event=>setName(event.target.value)}/>
      </label>
      <fieldset className="label-editor-colors"><legend>رنگ برچسب</legend>
        <div className="label-editor-palette">
          {LABEL_PALETTE.map((swatch,index)=><button key={swatch} type="button" className="label-editor-palette-color"
            aria-label={'انتخاب رنگ '+(index+1)} aria-pressed={swatch===color} title={swatch}
            style={{backgroundColor:swatch}} onClick={()=>setColor(swatch)}>
            {swatch===color&&<Check size={17} strokeWidth={3} color={coverTextColor(swatch)}/>}
          </button>)}
        </div>
        <label className="label-editor-custom-color">رنگ دلخواه
          <input type="color" aria-label="رنگ دلخواه برچسب" value={color}
            onChange={event=>setColor(event.target.value)}/>
          <output dir="ltr">{color.toUpperCase()}</output>
        </label>
      </fieldset>
      {!!error&&<small role="alert" className="label-editor-error">{error}</small>}
      <div className="label-editor-actions">
        <button type="submit" className="label-editor-save" disabled={!name.trim()}>
          <Check size={15}/> {screen==='edit'?'ذخیره':'ایجاد'}</button>
      </div>
    </form>:null}
  </section>;
}
