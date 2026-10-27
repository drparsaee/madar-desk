import React, {useId, useRef, useState} from 'react';
import {CircleHelp, Search, X} from 'lucide-react';
import './searchplus.css';

const EXAMPLES = [
  {query: 'title:"طراحی بسته"', description: 'عبارت دقیق در عنوان'},
  {query: 'برچسب:فوری priority:high', description: 'دو شرط هم‌زمان (AND)'},
  {query: 'member:ali OR report:"آماده تحویل"', description: 'یکی از دو شرط (OR)'},
  {query: 'due:1405/07/01..1405/07/30', description: 'بازه موعد شمسی'},
  {query: 'created>=2026-10-01 -status:done', description: 'از تاریخ ایجاد به بعد، به‌جز تکمیل‌شده‌ها'}
];

/**
 * Controlled task search input. Parent owns the state and applies filterTasks().
 * Usage: <SearchPlus query={search} onQueryChange={setSearch} resultCount={filtered.length}/>
 */
export function SearchPlus({query = '', onQueryChange = () => {}, resultCount, totalCount,
  placeholder = 'جست‌وجو در عنوان، شرح، برچسب، گزارش و اعضا...'}) {
  const [helpOpen, setHelpOpen] = useState(false);
  const inputRef = useRef(null);
  const helpId = useId();
  const current = String(query ?? '');
  const clear = () => { onQueryChange(''); inputRef.current?.focus(); };
  return <div className="searchplus-shell" data-no-floating-label="" dir="rtl" onKeyDown={event => {
    if (event.key === 'Escape') {
      if (helpOpen) setHelpOpen(false);
      else if (current) clear();
      else return;
      event.stopPropagation();
    }
  }}>
    <div className="searchplus-control" role="search">
      <Search size={18} className="searchplus-icon" aria-hidden="true"/>
      <input ref={inputRef} className="searchplus-input" type="search"
        aria-label="جست‌وجوی پیشرفته کارها" aria-controls={helpOpen ? helpId : undefined}
        value={current} onChange={event => onQueryChange(event.target.value)}
        placeholder={placeholder} spellCheck={false} autoComplete="off"/>
      {current.length > 0 && <button type="button" className="searchplus-action"
        onClick={clear} title="پاک‌کردن جست‌وجو" aria-label="پاک‌کردن جست‌وجو">
        <X size={16}/>
      </button>}
      <button type="button" className={'searchplus-action searchplus-help-button'+(helpOpen?' selected':'')}
        onClick={() => setHelpOpen(open => !open)} aria-label="راهنمای جست‌وجوی پیشرفته"
        aria-expanded={helpOpen} aria-controls={helpId} title="راهنمای جست‌وجو">
        <CircleHelp size={18}/>
      </button>
    </div>
    {current.trim() && typeof resultCount === 'number' && <span className="searchplus-count" role="status" aria-live="polite">
      {resultCount.toLocaleString('fa-IR')} نتیجه{typeof totalCount === 'number' ? ` از ${totalCount.toLocaleString('fa-IR')} کار` : ''}
    </span>}
    {helpOpen && <section id={helpId} className="searchplus-help" aria-label="راهنمای عبارت‌های جست‌وجو">
      <div className="searchplus-help-title"><strong>راهنمای جست‌وجوی پیشرفته</strong>
        <button type="button" onClick={() => setHelpOpen(false)} aria-label="بستن راهنما"><X size={16}/></button></div>
      <p>چند واژه به معنی «و» است. برای «یا» از <code>OR</code> یا <code>|</code> استفاده کن.
        عبارت داخل گیومه با همان ترتیب واژه‌ها جست‌وجو می‌شود. <code>-</code> قبل از واژه یعنی حذف آن نتیجه.</p>
      <p>فیلدها: <code>title</code>، <code>description</code>، <code>label</code>، <code>checklist</code>،
        <code>report</code>، <code>project</code>، <code>member</code>، <code>status</code>، <code>priority</code>،
        <code>due</code> و <code>created</code>. نام‌های فارسی هم پذیرفته می‌شوند.</p>
      <p>بازه تاریخ: <code>due:2026-10-01..2026-10-31</code> یا <code>due:1405/07/01..1405/07/30</code>.
        مقایسه‌های <code>&gt;=</code> و <code>&lt;=</code> هم کار می‌کنند.</p>
      <div className="searchplus-examples">
        {EXAMPLES.map(example => <button type="button" key={example.query}
          onClick={() => {onQueryChange(example.query); setHelpOpen(false); inputRef.current?.focus();}}>
          <span>{example.description}</span><code dir="auto">{example.query}</code>
        </button>)}
      </div>
    </section>}
  </div>;
}

export default SearchPlus;
