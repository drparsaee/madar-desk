'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {transformSync}=require('esbuild');
const source=fs.readFileSync(path.resolve(__dirname,'../src/button_hints.js'),'utf8');
const compiled=transformSync(source,{format:'cjs',loader:'js'}).code;
const mod={exports:{}};
new Function('module','exports',compiled)(mod,mod.exports);
const {briefButtonHint,installButtonHints}=mod.exports;
const button=(attrs,text='')=>({tagName:'BUTTON',innerText:text,
  getAttribute:k=>attrs[k]||null});

test('accessible names yield short native hints without duplicated inline text',()=>{
  assert.equal(briefButtonHint(button({'aria-label':'تازه‌سازی اتصال'})),'تازه‌سازی');
  assert.equal(briefButtonHint(button({'aria-label':'راهنمای جست‌وجوی پیشرفته'})),'راهنمای جست‌وجو');
  assert.equal(briefButtonHint(button({},'افزودن کارت')),'افزودن کارت');
  assert.equal(briefButtonHint(button({'aria-label':'نمایش منوی کامل مدار'})),'منو');
});
test('installButtonHints delegates to future buttons on hover/focus without timers',()=>{
  const listeners={};
  const doc={addEventListener:(type,fn)=>{listeners[type]=fn;},
    removeEventListener:(type,fn)=>{if(listeners[type]===fn)delete listeners[type];}};
  const element={tagName:'BUTTON',disabled:false,attributes:{'aria-label':'نمایش پروفایل من'},
    getAttribute(k){return this.attributes[k]||null;},setAttribute(k,v){this.attributes[k]=v;},
    closest(){return null;}};
  const stop=installButtonHints(doc);
  listeners.pointerover({target:{closest:()=>element}});
  assert.equal(element.attributes.title,'پروفایل');
  stop();
  assert.deepEqual(Object.keys(listeners),[]);
});
