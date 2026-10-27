/**
 * Native button tooltips only on pointer hover or keyboard focus. Reuses each
 * button's accessible name instead of rendering extra labels on the page.
 * Delegation covers buttons mounted later by dialogs and card drawers.
 */
export function briefButtonHint(button) {
  if (!button || button.tagName !== 'BUTTON') return '';
  const label = button.getAttribute('data-tooltip') ||
    button.getAttribute('aria-label') || button.getAttribute('title') ||
    button.innerText || button.textContent || '';
  const cleaned = String(label).replace(/\s+/g,' ').trim();
  if (!cleaned) return '';
  const common = [
    [/^تازه‌سازی(?: دستی| اتصال| و دریافت).*$/,'تازه‌سازی'],
    [/^بازکردن فهرست.*$/,'فهرست'],
    [/^نمایش منوی کامل.*$/,'منو'],
    [/^نمایش پروفایل.*$/,'پروفایل'],
    [/^جست‌وجوی پیشرفته.*$/,'جست‌وجو'],
    [/^راهنمای جست‌وجوی پیشرفته.*$/,'راهنمای جست‌وجو'],
    [/^بازگشت به نمای کلی.*$/,'نمای کلی'],
    [/^انتقال ستون (.*) به مرحله (.*)$/,'جابجایی ستون'],
  ];
  for (const [pattern,replacement] of common) if(pattern.test(cleaned)) return replacement;
  return cleaned.length>39?cleaned.slice(0,36).trimEnd()+'…':cleaned;
}

export function installButtonHints(doc = document) {
  const onEnter = event => {
    const target = event.target;
    const button = target?.closest?.('button');
    if (!button || button.disabled || button.closest?.('[inert]')) return;
    const hint=briefButtonHint(button);
    if(hint && button.getAttribute('title')!==hint) button.setAttribute('title',hint);
  };
  doc.addEventListener('pointerover',onEnter,true);
  doc.addEventListener('focusin',onEnter,true);
  return () => {
    doc.removeEventListener('pointerover',onEnter,true);
    doc.removeEventListener('focusin',onEnter,true);
  };
}
