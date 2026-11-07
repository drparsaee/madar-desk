/** Device-local display preferences. Never part of the shared project state. */
export const DEFAULT_GENERAL_UI = Object.freeze({
  font:'estedad',density:'comfortable',textWidth:'standard',motion:'system',
});
const OPTIONS=Object.freeze({
  font:['estedad','vazirmatn','system'],
  density:['comfortable','compact'],
  textWidth:['standard','wide'],
  motion:['system','reduce'],
});
export function normalizeGeneralUi(value){
  const input=value&&typeof value==='object'&&!Array.isArray(value)?value:{};
  return Object.fromEntries(Object.entries(OPTIONS).map(([key,choices])=>[
    key,choices.includes(input[key])?input[key]:DEFAULT_GENERAL_UI[key],
  ]));
}
const keyFor=scope=>'madar-general-ui:'+scope;
export function readGeneralUi(storage,scope){
  try{return normalizeGeneralUi(JSON.parse(storage.getItem(keyFor(scope))||'null'));}
  catch{return normalizeGeneralUi(null);}
}
export function writeGeneralUi(storage,scope,value){
  const normalized=normalizeGeneralUi(value);
  try{storage.setItem(keyFor(scope),JSON.stringify(normalized));}
  catch{/* In hardened WebView2, the React state remains effective for the session. */}
  return normalized;
}
export function readThemeMode(storage,scope,fallback='dark'){
  try{const mode=storage.getItem('madar-theme-mode:'+scope);
    if(['system','light','dark'].includes(mode))return mode;}
  catch{}
  return fallback==='light'?'light':'dark';
}
export function writeThemeMode(storage,scope,value){
  if(!['system','light','dark'].includes(value))throw new TypeError('Invalid theme mode');
  try{storage.setItem('madar-theme-mode:'+scope,value);}catch{}
  return value;
}
export const resolveTheme=(mode,systemDark)=>
  mode==='system'?(systemDark?'dark':'light'):mode==='light'?'light':'dark';

// A separate explicit consent flag. Merely having a local exchange folder does
// not authorize sharing a task with another application.
export function readTarazQueueConsent(storage,scope){
  try{return storage.getItem('madar-taraz-manual-consent:'+scope)==='true';}
  catch{return false;}
}
export function writeTarazQueueConsent(storage,scope,enabled){
  if(typeof enabled!=='boolean')throw new TypeError('Taraz consent must be boolean');
  try{storage.setItem('madar-taraz-manual-consent:'+scope,String(enabled));}
  catch{/* Memory-only consent lasts only for this session if storage is blocked. */}
  return enabled;
}
