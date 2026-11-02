import React,{useMemo,useState} from 'react';
import {Check, Pipette} from 'lucide-react';
import {CommonColorPalette} from './common_color_palette.jsx';
import './cover_color_picker.css';

const HEX=/^#[0-9A-F]{6}$/i;
export function hsvToHex(h,s,v){
  if(![h,s,v].every(Number.isFinite))throw new RangeError('HSV must be finite');
  const hh=((h%360)+360)%360,ss=Math.max(0,Math.min(1,s)),vv=Math.max(0,Math.min(1,v));
  const c=vv*ss,x=c*(1-Math.abs((hh/60)%2-1)),m=vv-c;
  const [r,g,b]=hh<60?[c,x,0]:hh<120?[x,c,0]:hh<180?[0,c,x]:
    hh<240?[0,x,c]:hh<300?[x,0,c]:[c,0,x];
  return '#'+[r,g,b].map(n=>Math.round((n+m)*255).toString(16).padStart(2,'0')).join('').toUpperCase();
}
export function hexToHsv(value){
  if(typeof value!=='string'||!HEX.test(value))throw new TypeError('Invalid HEX color');
  const rgb=[1,3,5].map(i=>parseInt(value.slice(i,i+2),16)/255);
  const [r,g,b]=rgb,min=Math.min(...rgb),max=Math.max(...rgb),d=max-min;
  let h=0;
  if(d){h=max===r?((g-b)/d)%6:max===g?(b-r)/d+2:(r-g)/d+4;h*=60;if(h<0)h+=360;}
  return {h,s:max===0?0:d/max,v:max};
}
const LEVELS=[1,.91,.8,.68,.56,.42,.3,.18];
const SATURATIONS=[0,.1,.22,.35,.48,.6,.7,.8,.9,1];

/**
 * Compact Trello-like solid color picker. No CSS string/URL is accepted.
 * The spectrum and ready colors emit only #RRGGBB. Edits are disabled
 * independently of preview, and existing saved cover data is not changed.
 */
export function CoverColorPicker({value='#5672CA',onChange,disabled=false}){
  const current=HEX.test(value)?value.toUpperCase():'#5672CA';
  const [hue,setHue]=useState(()=>Math.round(hexToHsv(current).h));
  const [draft,setDraft]=useState(current);
  const selected=useMemo(()=>hexToHsv(current),[current]);
  const grid=useMemo(()=>LEVELS.map(v=>SATURATIONS.map(s=>hsvToHex(hue,s,v))),[hue]);
  return <div className="cover-picker" dir="rtl">
    <CommonColorPalette value={current} onChange={color=>{setDraft(color);onChange(color);}} disabled={disabled} label="کاور"/>
    <details className="cover-picker__advanced">
      <summary><Pipette size={15}/> ساخت رنگ دلخواه <span dir="ltr">{current}</span></summary>
      <div className="cover-picker__panel">
        <div className="cover-picker__grid" role="group" aria-label="شبکه انتخاب رنگ">
          {grid.map((row,i)=>row.map((color,j)=><button type="button" key={i+'-'+j}
            title={color} aria-label={'انتخاب رنگ '+color} disabled={disabled}
            aria-pressed={current===color} className="cover-picker__cell"
            style={{backgroundColor:color}} onClick={()=>{setDraft(color);onChange(color);}}>
            {current===color&&<Check size={12}/>}</button>))}
        </div>
        <label className="cover-picker__hue">طیف رنگ
          <input type="range" min="0" max="359" step="1" value={hue}
            disabled={disabled} aria-label="طیف رنگ کاور" onChange={e=>setHue(Number(e.target.value))}/>
        </label>
        <div className="cover-picker__custom">
          <input type="color" aria-label="انتخاب رنگ آزاد کاور" disabled={disabled}
            value={HEX.test(draft)?draft:current} onChange={e=>{setDraft(e.target.value);onChange(e.target.value);}}/>
          <input type="text" aria-label="کد شش رقمی رنگ" dir="ltr" maxLength={7}
            value={draft} disabled={disabled} onChange={e=>setDraft(e.target.value)} placeholder="#RRGGBB"/>
          <button type="button" disabled={disabled||!HEX.test(draft)} onClick={()=>onChange(draft.toUpperCase())}>
            اعمال
          </button>
        </div>
        <small>رنگ انتخابی: {current} · روشنایی {Math.round(selected.v*100)}٪</small>
      </div>
    </details>
  </div>;
}
