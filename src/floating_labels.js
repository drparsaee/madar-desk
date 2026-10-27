/** Progressive floating captions, outside of all React-owned form subtrees.
 *
 * Call installFloatingLabels(document) once from each Vite entrypoint, after
 * createRoot(...).render(...); import floating_labels.css after other styles.
 * React can update/remove its original inputs and labels normally.
 */

const FIELD_SELECTOR = 'input, textarea, select';
const NON_TEXT_TYPES = new Set([
  'hidden', 'checkbox', 'radio', 'file', 'color', 'range', 'button', 'reset',
  'submit', 'image',
]);
const ALWAYS_RAISED_TYPES = new Set([
  'date', 'datetime-local', 'time', 'month', 'week',
]);

const clean = text => String(text ?? '').replace(/\s+/g, ' ').trim();

export function isFloatingCandidate(control) {
  if (!control || !['INPUT', 'TEXTAREA', 'SELECT'].includes(control.tagName)) return false;
  if (control.tagName === 'INPUT' && NON_TEXT_TYPES.has(control.type?.toLowerCase())) return false;
  if (control.closest?.('[inert], [aria-hidden="true"], [data-no-floating-label]')) return false;
  // An input without a real visible box (e.g. a hidden autocomplete helper)
  // must not acquire a visual overlay.
  return true;
}

function visibleLabelText(label, control) {
  if (!label?.childNodes) return '';
  const portions = [];
  for (const node of label.childNodes) {
    if (node === control || (node.nodeType === 1 && node.contains(control))) continue;
    if (node.nodeType === 3) portions.push(node.textContent);
    else if (node.nodeType === 1 &&
      !node.matches('input, textarea, select, button, [aria-hidden="true"], .madar-fl-caption') &&
      !node.querySelector('input, textarea, select, button')) {
      portions.push(node.textContent);
    }
  }
  return clean(portions.join(' '));
}

export function floatingLabelText(control, documentRoot = globalThis.document) {
  const nativeLabels = Array.from(control.labels || []);
  for (const label of nativeLabels) {
    const text = visibleLabelText(label, control);
    if (text) return text;
  }
  const labelledBy = control.getAttribute('aria-labelledby');
  if (labelledBy && documentRoot?.getElementById) {
    const text = clean(labelledBy.split(/\s+/).map(id =>
      documentRoot.getElementById(id)?.textContent || '').join(' '));
    if (text) return text;
  }
  return clean(control.getAttribute('aria-label') ||
    control.getAttribute('data-floating-label') ||
    control.getAttribute('placeholder') ||
    control.getAttribute('title'));
}

function isSimpleWrappingLabel(label, control) {
  if (label?.tagName !== 'LABEL' || control.parentElement !== label) return false;
  // Don't collapse compound labels with helper text, toggles, or more fields.
  const otherNodes = Array.from(label.children).filter(node =>
    node !== control && !node.classList.contains('madar-fl-caption'));
  return otherNodes.every(node =>
    node.tagName === 'SPAN' && !node.querySelector(FIELD_SELECTOR + ', button')) &&
    otherNodes.length <= 1;
}

function syncCaption(state) {
  const { control, caption } = state;
  const valuePresent = control.tagName === 'SELECT' ||
    Boolean(control.value) || control.matches(':focus') ||
    ALWAYS_RAISED_TYPES.has(control.type?.toLowerCase());
  caption.classList.toggle('madar-fl-raised', valuePresent);
  caption.classList.toggle('madar-fl-invalid', control.getAttribute('aria-invalid') === 'true');
  caption.classList.toggle('madar-fl-disabled', control.disabled);
}

/** Fixed captions follow the visible controls. They live in a portal outside
 * React's root, so neither reconciler children nor layout boxes are altered. */
function positionCaption(state) {
  const { control, caption } = state;
  const rect = control.getBoundingClientRect();
  const view = control.ownerDocument.defaultView;
  const modal = control.ownerDocument.querySelector('.overlay, .drawer-overlay, [aria-modal="true"]');
  const behindModal = modal && !modal.contains(control);
  if (rect.width < 45 || rect.height < 30 ||
      rect.bottom <= 0 || rect.top >= view.innerHeight ||
      rect.right <= 0 || rect.left >= view.innerWidth || behindModal) {
    caption.hidden = true;
    return;
  }
  caption.hidden = false;
  const right = Math.max(0, view.innerWidth - rect.right + 9);
  const top = rect.top + 7;
  const middle = rect.top + rect.height / 2;
  caption.style.setProperty('--madar-fl-right', `${right}px`);
  caption.style.setProperty('--madar-fl-top-y', `${top}px`);
  caption.style.setProperty('--madar-fl-mid-y', `${middle}px`);
  caption.style.setProperty('--madar-fl-width', `${Math.max(0, rect.width - 25)}px`);
}

export function installFloatingLabels(root = globalThis.document) {
  if (!root?.querySelectorAll || !root?.addEventListener) return () => {};
  const doc = root.nodeType === 9 ? root : root.ownerDocument;
  const view = doc.defaultView;
  if (!view?.MutationObserver || !view.requestAnimationFrame) return () => {};
  const appRoot = root.nodeType === 9 ? doc.getElementById('root') || doc.body : root;
  if (!appRoot) return () => {};
  const layer = doc.createElement('div');
  layer.className = 'madar-fl-layer';
  layer.setAttribute('aria-hidden', 'true');
  doc.body.appendChild(layer);
  const fields = new Map();
  let pending = false;
  let disposed = false;
  let dirty = true;

  const observer = new view.MutationObserver(records => {
    if (records.some(record => {
      if (record.type === 'attributes') return true;
      if (record.type === 'characterData') return !!record.target.parentElement?.closest('label');
      return Array.from(record.addedNodes).concat(Array.from(record.removedNodes))
        .some(node => node.nodeType === 1 &&
          (node.matches?.(FIELD_SELECTOR + ', label') || node.querySelector?.(FIELD_SELECTOR + ', label')));
    })) schedule(true);
  });
  const resizeObserver = view.ResizeObserver ? new view.ResizeObserver(() => schedule(false)) : null;

  function remove(control) {
    const state = fields.get(control);
    if (!state) return;
    state.caption.remove();
    control.classList.remove('madar-fl-control');
    control.style.removeProperty('--madar-fl-control-font');
    if (state.generatedAriaLabel && control.getAttribute('aria-label') === state.label) {
      control.removeAttribute('aria-label');
    }
    if (state.nativeLabel) {
      state.nativeLabel.classList.remove('madar-fl-native-label');
      state.sourceSpan?.classList.remove('madar-fl-original-caption');
    }
    resizeObserver?.unobserve(control);
    fields.delete(control);
  }

  function add(control) {
    if (!isFloatingCandidate(control) || !control.parentElement) return;
    const label = floatingLabelText(control, doc);
    if (!label) return; // Never invent an accessible name from a variable name.
    const caption = doc.createElement('span');
    caption.className = 'madar-fl-caption';
    caption.setAttribute('aria-hidden', 'true');
    caption.textContent = label;
    const nativeLabel = control.closest('label');
    const simple = isSimpleWrappingLabel(nativeLabel, control) ? nativeLabel : null;
    const sourceSpan = simple && Array.from(simple.children).find(node =>
      node.tagName === 'SPAN' && node !== caption);
    const generatedAriaLabel = !control.getAttribute('aria-label') &&
      !control.getAttribute('aria-labelledby') &&
      (Boolean(simple) || !control.labels?.length);
    if (generatedAriaLabel) control.setAttribute('aria-label', label);

    const font = view.getComputedStyle(control).fontSize;
    control.style.setProperty('--madar-fl-control-font', font);
    control.classList.add('madar-fl-control');
    if (simple) {
      simple.classList.add('madar-fl-native-label');
      sourceSpan?.classList.add('madar-fl-original-caption');
    }
    // The caption is a portal sibling of #root, never a React child.
    layer.appendChild(caption);
    const state = {control, caption, label, nativeLabel:simple, sourceSpan, generatedAriaLabel};
    fields.set(control, state);
    resizeObserver?.observe(control);
    syncCaption(state);
    positionCaption(state);
  }

  function scan() {
    if (disposed) return;
    const found = new Set(appRoot.querySelectorAll(FIELD_SELECTOR));
    for (const control of fields.keys()) {
      if (!found.has(control) || !control.isConnected || !isFloatingCandidate(control)) remove(control);
    }
    for (const control of found) {
      const state = fields.get(control);
      if (!state) add(control);
      else {
        const next = floatingLabelText(control, doc);
        if (next && next !== state.label) {
          state.label = next;
          state.caption.textContent = next;
          if (state.generatedAriaLabel) control.setAttribute('aria-label', next);
        }
        syncCaption(state);
        positionCaption(state);
      }
    }
  }

  function schedule(fullScan = false) {
    if (disposed) return;
    if (fullScan) dirty = true;
    if (pending) return;
    pending = true;
    view.requestAnimationFrame(() => {
      pending = false;
      if (disposed) return;
      if (dirty) { dirty = false; scan(); }
      else for (const state of fields.values()) positionCaption(state);
    });
  }
  function onFieldEvent(event) {
    const state = fields.get(event.target);
    if (state) syncCaption(state);
    else if (event.target?.matches?.(FIELD_SELECTOR)) schedule(true);
    if (event.type === 'focusout') view.requestAnimationFrame(() => {
      if (!disposed && fields.has(event.target)) syncCaption(fields.get(event.target));
    });
  }
  const onScroll = () => schedule(false);
  appRoot.addEventListener('focusin', onFieldEvent, true);
  appRoot.addEventListener('focusout', onFieldEvent, true);
  appRoot.addEventListener('input', onFieldEvent, true);
  appRoot.addEventListener('change', onFieldEvent, true);
  doc.addEventListener('scroll', onScroll, true);
  view.addEventListener('resize', onScroll);
  observer.observe(appRoot, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['aria-label', 'aria-labelledby', 'placeholder', 'title', 'id', 'for', 'type', 'aria-invalid', 'disabled'],
  });
  schedule(true);

  return () => {
    disposed = true;
    observer.disconnect();
    resizeObserver?.disconnect();
    appRoot.removeEventListener('focusin', onFieldEvent, true);
    appRoot.removeEventListener('focusout', onFieldEvent, true);
    appRoot.removeEventListener('input', onFieldEvent, true);
    appRoot.removeEventListener('change', onFieldEvent, true);
    doc.removeEventListener('scroll', onScroll, true);
    view.removeEventListener('resize', onScroll);
    for (const control of Array.from(fields.keys())) remove(control);
    layer.remove();
  };
}
