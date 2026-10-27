import React,{useLayoutEffect,useMemo,useRef,useState} from 'react';
import {
  advanceProgressiveLaneState,captureProgressiveLaneScroll,createProgressiveLaneState,
  getProgressiveLaneView,reconcileProgressiveLaneState
} from './board_progressive.js';

/** M03 bounded React card DOM. Full authorized lane stays with the caller for
 * drag, keyboard neighbors and counts; this component never changes task data. */
export function ProgressiveLane({items,scopeKey,regionId,label,renderCard,empty,containerClassName='lane-cards'}){
  const root=useRef(null);
  // Kanban columns now own their scrollport; list view still scrolls the page.
  // Capturing/restoring on .workspace-scroll would jump the entire board when
  // a long list extends past the progressive page limit.
  const nearestScroller=()=>root.current?.closest('.kanban-lane')
    ?root.current:root.current?.closest('.workspace-scroll');
  const [saved,setSaved]=useState(()=>({key:scopeKey,pager:createProgressiveLaneState(items)}));
  const pager=useMemo(()=>saved.key===scopeKey
    ?reconcileProgressiveLaneState(items,saved.pager)
    :createProgressiveLaneState(items),[items,saved,scopeKey]);
  const view=getProgressiveLaneView(items,pager,{regionId,laneLabel:label});
  const mounted=useRef(false);
  useLayoutEffect(()=>{
    if(!mounted.current){mounted.current=true;return;}
    const container=root.current;
    if(!container)return;
    const wrappers=Array.from(container.querySelectorAll('[data-progressive-card-id]'));
    const itemFor=id=>wrappers.find(element=>element.getAttribute('data-progressive-card-id')===id);
    if(view.scrollRestore.cardId){
      const anchor=itemFor(view.scrollRestore.cardId);
      const scroller=nearestScroller();
      if(anchor&&scroller){
        const currentOffset=anchor.getBoundingClientRect().top-scroller.getBoundingClientRect().top;
        const difference=currentOffset-view.scrollRestore.offsetPx;
        if(Number.isFinite(difference)&&Math.abs(difference)>1)scroller.scrollTop+=difference;
      }
    }
    if(view.focusTarget){
      const target=itemFor(view.focusTarget.cardId)?.querySelector('button,[role="button"]');
      target?.focus({preventScroll:true});
    }
  },[saved,scopeKey]);
  const advance=direction=>{
    // Capture the first visible anchor before changing the window, so trimming
    // earlier pages does not unexpectedly jump the scroll viewport.
    const first=root.current?.querySelector('[data-progressive-card-id]');
    const scroller=nearestScroller();
    const anchorId=first?.getAttribute('data-progressive-card-id');
    let captured=pager;
    if(anchorId&&scroller){
      try{
        captured=captureProgressiveLaneScroll(items,pager,{
          cardId:anchorId,
          offsetPx:first.getBoundingClientRect().top-scroller.getBoundingClientRect().top,
          scrollTopPx:scroller.scrollTop
        });
      }catch{captured=pager;}
    }
    setSaved({key:scopeKey,pager:advanceProgressiveLaneState(items,captured,direction)});
  };
  return <div ref={root}>
    <div className={containerClassName} id={regionId} role="list" aria-label={label}>
      {view.entries.length?view.entries.map(entry=><div className="progressive-lane-card" key={entry.key}
        data-progressive-card-id={entry.card.id} role="listitem"
        aria-posinset={entry.ariaPosInSet} aria-setsize={entry.ariaSetSize}>
          {renderCard(entry.card,entry.index)}
        </div>):empty}
    </div>
    {(view.hasNext||view.hasPrevious)&&<div className="progressive-lane-controls" style={{display:'flex',gap:8,flexWrap:'wrap',padding:8}}>
      {view.hasPrevious&&<button type="button" aria-controls={regionId} onClick={()=>advance('previous')}>کارت‌های قبلی</button>}
      {view.hasNext&&<button type="button" aria-controls={regionId} onClick={()=>advance('next')}>نمایش {Math.min(pager.pageSize,view.remaining).toLocaleString('fa-IR')} کارت بیشتر</button>}
      <small aria-live="polite">{view.liveStatus}</small>
    </div>}
  </div>;
}

