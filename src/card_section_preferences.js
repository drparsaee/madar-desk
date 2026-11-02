/**
 * Editor disclosure layout is a user preference, never a task/finance field.
 * A single saved layout is applied whenever another card is opened.
 */
export const CARD_SECTIONS=Object.freeze([
  'metadata','description','assignees','attachments','checklist',
  'tags','cover','time','dependencies','reports','accounting','settings'
]);
export const DEFAULT_CARD_SECTIONS=Object.freeze(Object.fromEntries(
  CARD_SECTIONS.map(section=>[section,section==='metadata'||section==='description'])));
const keyFor=identity=>'madar-card-sections-v1:'+encodeURIComponent(
  typeof identity==='string'&&identity.trim()?identity:'local');

export function readCardSectionPreferences(storage,identity) {
  try {
    const raw=storage?.getItem(keyFor(identity));
    if(!raw)return {...DEFAULT_CARD_SECTIONS};
    const value=JSON.parse(raw);
    if(!value||typeof value!=='object'||Array.isArray(value)||
       Object.keys(value).some(key=>!CARD_SECTIONS.includes(key)))return {...DEFAULT_CARD_SECTIONS};
    return Object.fromEntries(CARD_SECTIONS.map(key=>[
      key,value[key]===undefined?DEFAULT_CARD_SECTIONS[key]:value[key]===true
    ]));
  } catch {return {...DEFAULT_CARD_SECTIONS};}
}
export function saveCardSectionPreferences(storage,identity,options) {
  const clean=Object.fromEntries(CARD_SECTIONS.map(key=>[key,options?.[key]===true]));
  try{storage?.setItem(keyFor(identity),JSON.stringify(clean));}catch{}
  return clean;
}
