import React, {useEffect, useId, useMemo, useRef, useState} from 'react';
import {
  MADAR_HELP_CATEGORIES, filterMadarHelpSections, resolveMadarHelpSection,
} from './mtr_context_help_data.js';
import './mtr_context_help.css';

/**
 * Standalone contextual help. Never performs an app command or changes access.
 *
 * Parent integration: <MadarContextHelp currentSection={sectionId}
 *   availableSections={visibleHelpIds} />. The parent derives sectionId from
 * its real mode or opened modal, and may omit unavailable/permission-gated ids.
 * Help itself is intentionally closed on initial render.
 */
export function MadarContextHelp({currentSection='board', availableSections}) {
  const [open,setOpen] = useState(false);
  const [selectedId,setSelectedId] = useState('');
  const [query,setQuery] = useState('');
  const [category,setCategory] = useState('');
  const triggerRef = useRef(null);
  const searchRef = useRef(null);
  const panelId = useId();
  const current = resolveMadarHelpSection(currentSection);

  const allowed = useMemo(
    ()=>filterMadarHelpSections({availableSections}),
    [availableSections],
  );
  const activeId = selectedId || current.id;
  const active = allowed.find(item=>item.id===activeId) || allowed[0] || null;

  useEffect(()=>{
    // A new board or open modal takes precedence over a previously browsed tip.
    setSelectedId('');
    setQuery('');
    setCategory('');
  },[currentSection]);

  useEffect(()=>{
    if(open)searchRef.current?.focus();
  },[open]);

  const close = ()=>{
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <div className="mtr-context-help" dir="rtl" lang="fa"
      onKeyDown={event=>{
        if(open && event.key==='Escape'){
          event.preventDefault();
          event.stopPropagation();
          close();
        }
      }}>
      <button ref={triggerRef} className="mtr-context-help__trigger"
        type="button" title={'راهنمای '+current.title}
        aria-label={'راهنمای '+current.title}
        aria-expanded={open} aria-controls={panelId}
        onClick={()=>open?close():setOpen(true)}>؟</button>
      {open&&<MadarContextHelpPanel
        panelId={panelId} searchRef={searchRef}
        currentSection={active?.id || current.id}
        availableSections={availableSections}
        query={query} onQueryChange={setQuery}
        category={category} onCategoryChange={setCategory}
        onSelect={id=>{setSelectedId(id);setQuery('');setCategory('');}}
        onClose={close}/>}
    </div>
  );
}

/**
 * Purely presentational open view: easy to audit and SSR-test without
 * pretending to have mounted the live Madar App or any authenticated service.
 */
export function MadarContextHelpPanel({
  panelId, searchRef, currentSection='board', availableSections,
  query='', onQueryChange=()=>{}, category='', onCategoryChange=()=>{},
  onSelect=()=>{}, onClose=()=>{},
}) {
  const available = filterMadarHelpSections({availableSections});
  const current = resolveMadarHelpSection(currentSection);
  const active = available.find(item=>item.id===current.id) || available[0] || null;
  const matches = filterMadarHelpSections({
    availableSections, query, category,
  });
  const visibleCategories = MADAR_HELP_CATEGORIES.filter(name=>
    available.some(item=>item.category===name));
  const titleId = panelId ? panelId+'-title' : 'madar-help-panel-title';

  return (
    <section id={panelId} className="mtr-context-help__panel"
      dir="rtl" lang="fa" role="region" aria-labelledby={titleId}>
      <header className="mtr-context-help__head">
        <h2 id={titleId}>راهنمای مدار</h2>
        <button type="button" className="mtr-context-help__close"
          onClick={onClose} aria-label="بستن راهنما">×</button>
      </header>
      {active
        ?<div className="mtr-context-help__current" aria-live="polite">
          <strong>{active.title}</strong>
          <ol>{active.steps.map((step,index)=>
            <li key={index}>{step}</li>)}</ol>
        </div>
        :<p role="status" className="mtr-context-help__empty">
          برای این بخش راهنمای مجازی در دسترس نیست.
        </p>}
      <div className="mtr-context-help__browse">
        <label htmlFor={panelId ? panelId+'-search' : 'madar-help-search'}>
          جست‌وجوی راهنما
        </label>
        <input ref={searchRef} id={panelId ? panelId+'-search' : 'madar-help-search'}
          type="search" value={query}
          onChange={event=>onQueryChange(event.target.value)}
          placeholder="مثلاً: کارت، اعلان، اتصال…" autoComplete="off"/>
        <div className="mtr-context-help__categories"
          role="group" aria-label="دسته‌های راهنما">
          <button type="button" aria-pressed={!category}
            onClick={()=>onCategoryChange('')}>همه</button>
          {visibleCategories.map(name=><button key={name} type="button"
            aria-pressed={category===name}
            onClick={()=>onCategoryChange(category===name?'':name)}>
            {name}
          </button>)}
        </div>
        {matches.length
          ?<nav className="mtr-context-help__results" aria-label="موضوعات راهنما">
            {matches.map(item=><button key={item.id} type="button"
              aria-current={item.id===active?.id?'true':undefined}
              onClick={()=>onSelect(item.id)}>
              {item.title}
            </button>)}
          </nav>
          :<p role="status" className="mtr-context-help__empty">
            نتیجه‌ای برای این جست‌وجو نیست.
          </p>}
      </div>
      <small className="mtr-context-help__foot">
        نمایش گزینه‌ها به دسترسی شما، نوع نسخه و وضعیت اتصال بستگی دارد.
      </small>
    </section>
  );
}

export default MadarContextHelp;
