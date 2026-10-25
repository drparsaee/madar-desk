/**
 * M03: bounded, accessible progressive lane data windows.
 *
 * Feed ONLY a stable, already-authorized/filtered and ordered lane array from
 * createBoardPerformanceIndex().groupActiveCards({boardId,...}). This module
 * does not authenticate users, virtualize React/DOM, or modify saved state.
 * It stores window/scroll *metadata*, not the task array or financial fields.
 */
export const PROGRESSIVE_LANE_LIMITS = Object.freeze({
  maxCards: 20_000,
  defaultPageSize: 48,
  maxPageSize: 100,
  defaultMaxRendered: 240,
  maxRendered: 300,
});

const VERSION = 1;

function plainObject(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError(name + ' must be an object');
  }
  return value;
}
function integer(value, name, min, max) {
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new RangeError(name + ' must be an integer in ' + min + '..' + max);
  }
  return value;
}
function offsetNumber(value, name, nonNegative = false) {
  if (!Number.isFinite(value) || (nonNegative && value < 0)) {
    throw new RangeError(name + ' must be a finite ' +
      (nonNegative ? 'nonnegative ' : '') + 'number');
  }
  return value;
}
function laneCards(cards) {
  if (!Array.isArray(cards) || cards.length > PROGRESSIVE_LANE_LIMITS.maxCards) {
    throw new RangeError('cards must be an authorized lane array of at most 20000');
  }
  const seen = new Set();
  for (const card of cards) {
    plainObject(card, 'card');
    // Legacy task IDs may be empty, contain control chars or exceed 100 chars.
    if (typeof card.id !== 'string') throw new TypeError('card.id must be a string');
    if (seen.has(card.id)) throw new RangeError('Duplicate card ID');
    seen.add(card.id);
  }
  return cards;
}
function findId(cards, id) {
  return cards.findIndex(card => card.id === id);
}
function pagerState(pager) {
  plainObject(pager, 'pager');
  if (pager.version !== VERSION) throw new RangeError('Unsupported pager version');
  const pageSize = integer(pager.pageSize, 'pageSize', 1,
    PROGRESSIVE_LANE_LIMITS.maxPageSize);
  const maxRendered = integer(pager.maxRendered, 'maxRendered', pageSize,
    PROGRESSIVE_LANE_LIMITS.maxRendered);
  const start = integer(pager.start, 'start', 0, PROGRESSIVE_LANE_LIMITS.maxCards);
  const end = integer(pager.end, 'end', start, PROGRESSIVE_LANE_LIMITS.maxCards);
  if (end - start > maxRendered) throw new RangeError('Pager exceeds render cap');
  if (pager.anchorId !== null && typeof pager.anchorId !== 'string') {
    throw new TypeError('anchorId must be a string or null');
  }
  offsetNumber(pager.anchorOffsetPx, 'anchorOffsetPx');
  offsetNumber(pager.scrollTopPx, 'scrollTopPx', true);
  if (pager.anchorIndexInWindow !== null) {
    integer(pager.anchorIndexInWindow, 'anchorIndexInWindow', 0, maxRendered - 1);
  }
  if (pager.focusCardId !== null && typeof pager.focusCardId !== 'string') {
    throw new TypeError('focusCardId must be a string or null');
  }
  if (typeof pager.anchorLost !== 'boolean') throw new TypeError('anchorLost must be boolean');
  return pager;
}
function build(pager, updates) {
  return Object.freeze({...pager, ...updates});
}
function initial(pageSize, maxRendered, length) {
  return Object.freeze({
    version: VERSION,
    pageSize,
    maxRendered,
    start: 0,
    end: Math.min(pageSize, length),
    anchorId: null,
    anchorIndexInWindow: null,
    anchorOffsetPx: 0,
    scrollTopPx: 0,
    anchorLost: false,
    focusCardId: null,
  });
}

/** New lane/filter/auth scope: reset to a small first page. */
export function createProgressiveLaneState(cards,
  {pageSize = PROGRESSIVE_LANE_LIMITS.defaultPageSize,
   maxRendered = PROGRESSIVE_LANE_LIMITS.defaultMaxRendered} = {}) {
  laneCards(cards);
  integer(pageSize, 'pageSize', 1, PROGRESSIVE_LANE_LIMITS.maxPageSize);
  integer(maxRendered, 'maxRendered', pageSize, PROGRESSIVE_LANE_LIMITS.maxRendered);
  return initial(pageSize, maxRendered, cards.length);
}

/**
 * Capture current browser measurement before state change. cardId MUST be
 * actually rendered and authorized; never cache offscreen or foreign IDs.
 * offsetPx = top of card relative to scroll viewport, measured by UI.
 */
export function captureProgressiveLaneScroll(cards, pager,
  {cardId, offsetPx = 0, scrollTopPx = 0} = {}) {
  laneCards(cards);
  pagerState(pager);
  if (typeof cardId !== 'string') throw new TypeError('cardId must be a string');
  const index = findId(cards, cardId);
  if (index < pager.start || index >= Math.min(cards.length, pager.end)) {
    throw new RangeError('Anchor card is not in current permitted rendered window');
  }
  offsetNumber(offsetPx, 'offsetPx');
  offsetNumber(scrollTopPx, 'scrollTopPx', true);
  return build(pager, {
    anchorId: cardId,
    anchorIndexInWindow: index - pager.start,
    anchorOffsetPx: offsetPx,
    scrollTopPx,
    anchorLost: false,
  });
}

function adjustAnchor(cards, pager, start, end) {
  if (start === end) return {
    anchorId: null, anchorIndexInWindow: null, anchorOffsetPx: 0,
    scrollTopPx: 0, anchorLost: pager.anchorId !== null,
  };
  if (pager.anchorId !== null) {
    const found = findId(cards, pager.anchorId);
    if (found >= start && found < end) {
      return {
        anchorId: pager.anchorId,
        anchorIndexInWindow: found - start,
        anchorOffsetPx: pager.anchorOffsetPx,
        scrollTopPx: pager.scrollTopPx,
        anchorLost: false,
      };
    }
  }
  const replacement = cards[start];
  return {
    anchorId: replacement.id,
    anchorIndexInWindow: 0,
    anchorOffsetPx: 0,
    scrollTopPx: 0,
    anchorLost: pager.anchorId !== null,
  };
}

/**
 * Grow one side by at most pageSize and trim the opposite side to maxRendered.
 * On a no-op boundary it returns pager unchanged. Newly revealed first card
 * is a safe focus destination (keyboard/screen reader); parent UI executes it.
 */
export function advanceProgressiveLaneState(cards, pager, direction = 'next') {
  laneCards(cards);
  pagerState(pager);
  if (direction !== 'next' && direction !== 'previous') {
    throw new TypeError('direction must be next or previous');
  }
  if (pager.end > cards.length) {
    throw new RangeError('Lane has changed; reconcile before advancing');
  }
  const {start, end, pageSize, maxRendered} = pager;
  if (direction === 'next' && end >= cards.length) return pager;
  if (direction === 'previous' && start === 0) return pager;
  const newEnd = direction === 'next' ? Math.min(cards.length, end + pageSize) :
    Math.min(end, Math.max(0, start - pageSize) + maxRendered);
  const newStart = direction === 'next' ? Math.max(start, newEnd - maxRendered) :
    Math.max(0, start - pageSize);
  const newlyRevealed = direction === 'next' ? end : newStart;
  return build(pager, {
    start: newStart,
    end: newEnd,
    ...adjustAnchor(cards, pager, newStart, newEnd),
    focusCardId: cards[newlyRevealed]?.id ?? null,
  });
}

/**
 * Reconcile AFTER an immutable filtered/authorized lane replacement:
 * preserve captured anchor ID and its prior relative index when still allowed,
 * otherwise clamp to a visible window WITHOUT retaining the stale ID.
 */
export function reconcileProgressiveLaneState(cards, pager) {
  laneCards(cards);
  pagerState(pager);
  const size = cards.length;
  if (!size) {
    return build(pager, {
      start: 0, end: 0, anchorId: null, anchorIndexInWindow: null,
      anchorOffsetPx: 0, scrollTopPx: 0, anchorLost: pager.anchorId !== null,
      focusCardId: null,
    });
  }
  const previousWindow = Math.min(pager.maxRendered,
    Math.max(pager.pageSize, pager.end - pager.start));
  let start = Math.min(pager.start, Math.max(0, size - previousWindow));
  let end = Math.min(size, start + previousWindow);
  if (pager.anchorId !== null) {
    const anchorPosition = findId(cards, pager.anchorId);
    if (anchorPosition !== -1) {
      const relative = pager.anchorIndexInWindow ?? 0;
      start = Math.max(0, Math.min(size - previousWindow, anchorPosition - relative));
      end = Math.min(size, start + previousWindow);
    }
  }
  const anchor = adjustAnchor(cards, pager, start, end);
  const focusValid = pager.focusCardId !== null &&
    findId(cards, pager.focusCardId) >= start &&
    findId(cards, pager.focusCardId) < end;
  return build(pager, {start,end,...anchor,
    focusCardId: focusValid ? pager.focusCardId : null});
}

/** Jump for search/keyboard navigation to an authorized card, bounded window. */
export function revealProgressiveLaneCard(cards, pager, cardId) {
  laneCards(cards);
  pagerState(pager);
  if (typeof cardId !== 'string') throw new TypeError('cardId must be a string');
  const index = findId(cards, cardId);
  if (index === -1) throw new RangeError('Card is not in current permitted lane');
  if (pager.end > cards.length) {
    throw new RangeError('Lane has changed; reconcile before reveal');
  }
  if (index >= pager.start && index < pager.end) {
    return build(pager, {focusCardId:cardId});
  }
  const windowSize = Math.min(pager.maxRendered,
    Math.max(pager.pageSize, pager.end - pager.start));
  const start = Math.min(Math.max(0, index - Math.floor(windowSize/2)),
    Math.max(0, cards.length - windowSize));
  const end = Math.min(cards.length, start + windowSize);
  return build(pager, {
    start,end,anchorId:cardId,anchorIndexInWindow:index-start,
    anchorOffsetPx:0,scrollTopPx:0,anchorLost:pager.anchorId !== null,
    focusCardId:cardId,
  });
}

/** Stable full-list neighbor for drag/keyboard order, NOT only rendered cards. */
export function progressiveLaneNeighbor(cards, cardId, delta) {
  laneCards(cards);
  if (typeof cardId !== 'string') throw new TypeError('cardId must be a string');
  if (delta !== 1 && delta !== -1) throw new RangeError('delta must be +1 or -1');
  const index = findId(cards, cardId);
  if (index === -1) throw new RangeError('Card is not in current permitted lane');
  return cards[index + delta] || null;
}

function safeRegionId(id) {
  if (typeof id !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,79}$/.test(id)) {
    throw new TypeError('regionId must be a stable DOM-safe identifier');
  }
  return id;
}

/**
 * Pure SSR/React render model with full-lane 1-based ARIA positions.
 * The caller renders ONLY entries, adds aria-posinset/aria-setsize and a
 * keyboard-accessible BUTTON for each load control, then honors focusTarget
 * and scrollRestore after commit. No timers, DOM reads or hidden side effects.
 */
export function getProgressiveLaneView(cards, pager, {
  regionId, laneLabel = 'ستون',
} = {}) {
  laneCards(cards);
  pagerState(pager);
  safeRegionId(regionId);
  if (typeof laneLabel !== 'string' || !laneLabel.trim() || laneLabel.length > 180) {
    throw new TypeError('laneLabel must be a short nonempty string');
  }
  if (pager.end > cards.length) {
    throw new RangeError('Lane has changed; reconcile before rendering');
  }
  const total = cards.length;
  const entries = cards.slice(pager.start,pager.end).map((card, offset) => {
    const index = pager.start + offset;
    return Object.freeze({
      card,
      key:card.id,
      index,
      ariaPosInSet:index + 1,
      ariaSetSize:total,
    });
  });
  const remaining = total - pager.end;
  const shown = entries.length;
  const previous = pager.start > 0;
  const next = remaining > 0;
  const region = Object.freeze({
    id:regionId, role:'list', 'aria-label':laneLabel,
    'aria-busy':false,
  });
  const previousControl = previous ? Object.freeze({
    type:'button',
    'aria-controls':regionId,
    'aria-label':'نمایش کارت‌های قبلی '+laneLabel,
    text:'نمایش کارت‌های قبلی',
  }) : null;
  const nextControl = next ? Object.freeze({
    type:'button',
    'aria-controls':regionId,
    'aria-label':'نمایش '+Math.min(pager.pageSize,remaining)+' کارت بیشتر در '+laneLabel,
    text:'نمایش '+Math.min(pager.pageSize,remaining)+' کارت بیشتر',
  }) : null;
  const restoredAnchorVisible = pager.anchorId !== null &&
    entries.some(entry => entry.card.id === pager.anchorId);
  return Object.freeze({
    entries,
    total,
    shown,
    rangeStart:shown ? pager.start + 1 : 0,
    rangeEnd:pager.end,
    remaining,
    hasNext:next,
    hasPrevious:previous,
    region,
    controls:Object.freeze({previous:previousControl,next:nextControl}),
    liveStatus:total
      ? 'نمایش کارت‌های '+(pager.start + 1)+' تا '+pager.end+' از '+total+' در '+laneLabel
      : 'کارتی در '+laneLabel+' وجود ندارد',
    focusTarget:pager.focusCardId !== null &&
      entries.some(entry => entry.card.id === pager.focusCardId)
      ? Object.freeze({cardId:pager.focusCardId, preventScroll:true}) : null,
    scrollRestore:restoredAnchorVisible
      ? Object.freeze({cardId:pager.anchorId,
        offsetPx:pager.anchorOffsetPx, fallbackScrollTopPx:pager.scrollTopPx,
        strategy:'measure-anchor-after-render'})
      : Object.freeze({cardId:null,offsetPx:0,
        fallbackScrollTopPx:0,strategy:'reset'}),
    anchorLost:pager.anchorLost,
  });
}
