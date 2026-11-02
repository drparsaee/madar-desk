import React, {useEffect, useState} from 'react';
import {Plus, X} from 'lucide-react';
import {LabelChip, labelColor} from './boardplus.jsx';
import {CommonColorOptions} from './common_color_palette.jsx';
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

const ERROR_MESSAGES = {
  empty: 'نام برچسب نمی‌تواند خالی باشد.',
  duplicate: 'این نام برچسب قبلاً ثبت شده است.',
  limit: 'حداکثر ۲۰۰ برچسب برای هر کار مجاز است.',
  color: 'رنگ انتخابی معتبر نیست.',
  invalid: 'امکان تغییر این برچسب وجود ندارد.'
};

// onChange receives {labels: string[], labelColors: {[name]: '#rrggbb'}}.
export function LabelEditor({labels = [], colors = {}, onChange, disabled = false}) {
  const [drafts, setDrafts] = useState({});
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState(DEFAULT_COLOR);
  const [error, setError] = useState('');
  const normalized = normalizeTaskLabels(labels, colors);
  const namesSignature = JSON.stringify(normalized.labels);

  useEffect(() => {setDrafts({}); setError('');}, [namesSignature]);

  const apply = operation => {
    if (disabled || typeof onChange !== 'function') return false;
    const next = editTaskLabels(labels, colors, operation);
    if (next.error) {setError(ERROR_MESSAGES[next.error]); return false;}
    setError('');
    if (JSON.stringify(normalized) !== JSON.stringify(next)) onChange(next);
    return true;
  };
  const rename = (index, name) => {
    if (apply({action: 'rename', index, name})) {
      setDrafts(prev => {const next = {...prev}; delete next[index]; return next;});
    }
  };
  const add = () => {
    if (apply({action: 'add', name: newName, color: newColor})) {
      setNewName('');
      setNewColor(DEFAULT_COLOR);
    }
  };

  return <div className="label-editor" dir="rtl" aria-label="برچسب‌ها">
    {normalized.labels.map((name, index) => <div className="label-editor-row" key={`${index}-${name}`}>
      <div className="label-editor-name-wrap">
        <span className="label-editor-dot" style={{backgroundColor: normalized.labelColors[name]}} aria-hidden="true"/>
        <input type="text" aria-label={`نام برچسب ${name}`} maxLength={MAX_NAME} disabled={disabled}
          value={drafts[index] ?? name}
          onChange={event => {setDrafts(prev => ({...prev, [index]: event.target.value})); setError('');}}
          onBlur={event => rename(index, event.currentTarget.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') {event.preventDefault(); event.currentTarget.blur();}
            if (event.key === 'Escape') {event.currentTarget.value = name; event.currentTarget.blur();}
          }}/>
      </div>
      <button type="button" className="label-editor-remove" disabled={disabled} aria-label={`حذف برچسب ${name}`}
        title="حذف برچسب" onClick={() => apply({action: 'remove', index})}><X size={15}/></button>
      <CommonColorOptions disabled={disabled} label={'برچسب '+name} value={normalized.labelColors[name]}
        onChange={color=>apply({action:'color',index,color})}/>
    </div>)}
    {!disabled && <div className="label-editor-row label-editor-create">
      <input type="text" aria-label="نام برچسب جدید" maxLength={MAX_NAME} value={newName}
        placeholder="نام برچسب جدید..." onChange={event => {setNewName(event.target.value); setError('');}}
        onKeyDown={event => {if (event.key === 'Enter') {event.preventDefault(); add();}}}/>
      <button type="button" className="label-editor-add" aria-label="افزودن برچسب" title="افزودن برچسب"
        disabled={!newName.trim() || normalized.labels.length >= MAX_LABELS} onClick={add}><Plus size={17}/></button>
      <CommonColorOptions disabled={disabled} label="برچسب جدید" value={newColor} onChange={setNewColor}/>
    </div>}
    {!!error && <small role="alert" className="label-editor-error">{error}</small>}
  </div>;
}
