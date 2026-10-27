import React, {useEffect, useId, useLayoutEffect, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Check, Clock3, Grip, RotateCcw, Settings2} from 'lucide-react';
import {CLOCK_WIDGET_CHOICES, normalizeClockWidget} from './clock_widget.js';
import {
  DEFAULT_WIDGET_SETTINGS, normalizeWidgetSettings, nudgeWidgetPosition,
  widgetPositionToPixels, widgetPixelsToPosition,
} from './widget_preferences.js';
import './clock_widget.css';

const THEME_CHOICES = [
  {id: 'light', label: 'شیشه روشن'},
  {id: 'dark', label: 'شیشه تیره'},
  {id: 'aurora', label: 'شفق رنگی'},
];
const SIZE_CHOICES = [
  {id: 'compact', label: 'کوچک'},
  {id: 'regular', label: 'معمولی'},
  {id: 'large', label: 'بزرگ'},
];
const PLACEMENT_CHOICES = [
  {id: 'topbar', label: 'نوار بالا'},
  {id: 'floating', label: 'شناور و قابل جابه‌جایی'},
  {id: 'top-right', label: 'بالا راست'},
  {id: 'top-left', label: 'بالا چپ'},
  {id: 'bottom-right', label: 'پایین راست'},
  {id: 'bottom-left', label: 'پایین چپ'},
];

const POPOVER_GAP = 8;
const POPOVER_INSET = 8;

/** Clamp a portal popup to the visible viewport, preferring the roomier side. */
export function clockPopoverPosition(anchor, menu, viewport, alignRight = true) {
  const width = Math.max(0, Number(viewport?.width) || 0);
  const height = Math.max(0, Number(viewport?.height) || 0);
  const originX = Number(viewport?.left) || 0;
  const originY = Number(viewport?.top) || 0;
  const menuWidth = Math.min(Math.max(0, Number(menu?.width) || 0), Math.max(0, width - POPOVER_INSET * 2));
  const menuHeight = Math.min(Math.max(0, Number(menu?.height) || 0), Math.max(0, height - POPOVER_INSET * 2));
  const clamp = (value, low, high) => Math.min(Math.max(value, low), Math.max(low, high));
  const left = clamp(alignRight ? anchor.right - menuWidth : anchor.left,
    originX + POPOVER_INSET, originX + width - menuWidth - POPOVER_INSET);
  const below = originY + height - anchor.bottom - POPOVER_GAP - POPOVER_INSET;
  const above = anchor.top - originY - POPOVER_GAP - POPOVER_INSET;
  const showAbove = below < menuHeight && above > below;
  const top = clamp(showAbove ? anchor.top - menuHeight - POPOVER_GAP : anchor.bottom + POPOVER_GAP,
    originY + POPOVER_INSET, originY + height - menuHeight - POPOVER_INSET);
  return {left: Math.round(left), top: Math.round(top)};
}

function SettingChoices({label, value, items, onChange, disabled}) {
  return <fieldset className="widget-settings__group" disabled={disabled}>
    <legend>{label}</legend>
    <div className="widget-settings__choices">
      {items.map(item => <button key={item.id} type="button"
        className={value === item.id ? 'is-active' : ''} aria-pressed={value === item.id}
        disabled={disabled} onClick={() => onChange(item.id)}>
        {item.label}{value === item.id && <Check size={13} aria-hidden="true"/>}
      </button>)}
    </div>
  </fieldset>;
}

/** Reusable settings for the global SettingsPanel and the widget's own popover.
 * onChange receives a complete, normalized, JSON-serializable settings object.
 * Persistence is owned by the parent, never by this component.
 */
export function WidgetSettings({settings, onChange, disabled = false, embedded = false}) {
  const value = normalizeWidgetSettings(settings);
  const update = patch => onChange?.(normalizeWidgetSettings({...value, ...patch}));
  const move = direction => update({position: nudgeWidgetPosition(value.position, direction, 0.06)});
  return <div className={'widget-settings' + (embedded ? '' : ' widget-settings--panel')}
    dir="rtl" role="group" aria-label="شخصی‌سازی ساعت و تاریخ">
    {!embedded && <><h3><Clock3 size={17}/> ویجت ساعت و تاریخ</h3>
      <p className="widget-settings__intro">قالب و جای ویجت شخصی است و روی تاریخ واقعی کارها تأثیری ندارد.</p></>}
    <SettingChoices label="نمایش" items={CLOCK_WIDGET_CHOICES} value={value.mode} disabled={disabled}
      onChange={mode => update({mode})}/>
    <SettingChoices label="پوسته" items={THEME_CHOICES} value={value.theme} disabled={disabled}
      onChange={theme => update({theme})}/>
    <SettingChoices label="اندازه" items={SIZE_CHOICES} value={value.size} disabled={disabled}
      onChange={size => update({size})}/>
    <SettingChoices label="قالب ساعت" items={[{id:'24',label:'۲۴ ساعته'},{id:'12',label:'۱۲ ساعته'}]}
      value={value.hourFormat} disabled={disabled} onChange={hourFormat => update({hourFormat})}/>
    <SettingChoices label="نمایش تاریخ" items={[{id:'full',label:'کامل'},{id:'compact',label:'خلاصه'}]}
      value={value.dateFormat} disabled={disabled} onChange={dateFormat => update({dateFormat})}/>
    <SettingChoices label="محل قرارگیری" items={PLACEMENT_CHOICES} value={value.placement}
      disabled={disabled} onChange={placement => update({placement})}/>
    {value.placement === 'floating' && <div className="widget-settings__position">
      <span>موقعیت روی صفحه</span>
      <div className="widget-settings__position-actions" role="group" aria-label="تنظیم موقعیت ویجت">
        {[
          {direction:'ArrowRight', icon:ArrowRight, label:'حرکت به راست'},
          {direction:'ArrowLeft', icon:ArrowLeft, label:'حرکت به چپ'},
          {direction:'ArrowUp', icon:ArrowUp, label:'حرکت به بالا'},
          {direction:'ArrowDown', icon:ArrowDown, label:'حرکت به پایین'},
        ].map(({direction, icon:Icon, label}) => <button type="button" key={direction}
          onClick={() => move(direction)} aria-label={label} title={label} disabled={disabled}><Icon size={16}/></button>)}
        <button type="button" disabled={disabled} title="بازگرداندن جای اولیه" aria-label="بازگرداندن جای اولیه"
          onClick={() => update({position: {...DEFAULT_WIDGET_SETTINGS.position}})}><RotateCcw size={16}/></button>
      </div>
      <small>ویجت را از دستگیره‌اش بکشید؛ با کلیدهای جهت‌دار هم جابه‌جا می‌شود. Shift حرکت را سریع‌تر می‌کند.</small>
    </div>}
  </div>;
}

/** ClockWidget accepts {settings,onChange} or the legacy {mode,onChange(mode)}.
 * onOpenSettings optionally opens the existing SettingsPanel for full controls.
 */
export function ClockWidget({calendar = 'jalali', settings, mode = 'both', onChange, onOpenSettings, disabled = false}) {
  const value = normalizeWidgetSettings(settings === undefined ? normalizeClockWidget(mode) : settings);
  const [now, setNow] = useState(() => new Date());
  const [open, setOpen] = useState(false);
  const [viewport, setViewport] = useState(() => ({width: typeof window === 'undefined' ? 1024 : window.innerWidth,
    height: typeof window === 'undefined' ? 768 : window.innerHeight}));
  const [widgetSize, setWidgetSize] = useState({width: 230, height: 110});
  const [dragPreview, setDragPreview] = useState(null);
  const [menuPosition, setMenuPosition] = useState(null);
  const holder = useRef(null);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const menuId = useId();
  const drag = useRef(null);
  const placement = value.mode === 'hidden' ? 'topbar' : value.placement;
  const isFloating = placement === 'floating';
  const position = dragPreview || value.position;

  const commit = next => {
    const normalized = normalizeWidgetSettings(next);
    onChange?.(settings === undefined ? normalized.mode : normalized);
  };

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    const resize = () => setViewport({width: window.innerWidth, height: window.innerHeight});
    window.addEventListener('resize', resize);
    return () => window.removeEventListener('resize', resize);
  }, []);
  useEffect(() => {
    if (!isFloating || !holder.current) return;
    const measure = () => {
      const bounds = holder.current?.getBoundingClientRect();
      if (bounds) setWidgetSize(previous => previous.width === bounds.width && previous.height === bounds.height
        ? previous : {width: bounds.width, height: bounds.height});
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(holder.current);
    return () => observer.disconnect();
  }, [isFloating, value.size, value.mode, value.dateFormat, open]);
  useEffect(() => {
    if (!open) return;
    const close = event => {
      if (event.type === 'keydown' && event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        triggerRef.current?.focus();
      } else if ((event.type === 'pointerdown' || event.type === 'focusin') &&
          !holder.current?.contains(event.target) && !menuRef.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', close);
    document.addEventListener('pointerdown', close);
    document.addEventListener('focusin', close);
    return () => {
      document.removeEventListener('keydown', close);
      document.removeEventListener('pointerdown', close);
      document.removeEventListener('focusin', close);
    };
  }, [open]);
  useLayoutEffect(() => {
    if (!open || !triggerRef.current || !menuRef.current) return;
    let frame = 0;
    const reposition = () => {
      const anchor = triggerRef.current?.getBoundingClientRect();
      const menu = menuRef.current?.getBoundingClientRect();
      if (!anchor || !menu) return;
      const visual = window.visualViewport;
      const viewport = {left: visual?.offsetLeft || 0, top: visual?.offsetTop || 0,
        width: visual?.width || window.innerWidth, height: visual?.height || window.innerHeight};
      const next = clockPopoverPosition(anchor, menu, viewport,
        !isFloating || value.position.x > 0.5);
      setMenuPosition(previous => previous?.left === next.left && previous?.top === next.top ? previous : next);
    };
    const schedule = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {frame = 0; reposition();});
    };
    reposition();
    window.addEventListener('resize', schedule);
    document.addEventListener('scroll', schedule, true);
    window.visualViewport?.addEventListener('resize', schedule);
    window.visualViewport?.addEventListener('scroll', schedule);
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(schedule) : null;
    if (observer) {
      observer.observe(menuRef.current);
      observer.observe(triggerRef.current);
    }
    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener('resize', schedule);
      document.removeEventListener('scroll', schedule, true);
      window.visualViewport?.removeEventListener('resize', schedule);
      window.visualViewport?.removeEventListener('scroll', schedule);
      observer?.disconnect();
    };
  }, [open, value.placement, value.mode, isFloating, value.position.x]);
  useEffect(() => {setDragPreview(null);}, [value.position.x, value.position.y, value.placement]);

  const onDragStart = event => {
    if (disabled || !isFloating || event.button !== 0) return;
    const rect = holder.current?.getBoundingClientRect();
    if (!rect) return;
    event.preventDefault();
    event.stopPropagation();
    setOpen(false);
    drag.current = {id: event.pointerId, x: event.clientX, y: event.clientY,
      left: rect.left, top: rect.top, width: rect.width, height: rect.height,
      position: value.position, moved: false};
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };
  const onDragMove = event => {
    const current = drag.current;
    if (!current || current.id !== event.pointerId) return;
    const dx = event.clientX - current.x;
    const dy = event.clientY - current.y;
    if (Math.abs(dx) + Math.abs(dy) < 2 && !current.moved) return;
    current.moved = true;
    current.position = widgetPixelsToPosition({left: current.left + dx, top: current.top + dy},
      viewport, {width: current.width, height: current.height});
    setDragPreview(current.position);
  };
  const onDragEnd = event => {
    const current = drag.current;
    if (!current || current.id !== event.pointerId) return;
    drag.current = null;
    if (event.type !== 'pointercancel' && current.moved) commit({...value, position: current.position});
    setDragPreview(null);
  };
  const onHandleKey = event => {
    if (disabled || !isFloating) return;
    if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    event.stopPropagation();
    commit({...value, position: nudgeWidgetPosition(value.position, event.key, event.shiftKey ? 0.1 : 0.03)});
  };

  const locale = calendar === 'jalali' ? 'fa-IR-u-ca-persian' : 'fa-IR-u-ca-gregory';
  const date = new Intl.DateTimeFormat(locale, value.dateFormat === 'compact'
    ? {year: '2-digit', month: '2-digit', day: '2-digit'}
    : {weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'}).format(now);
  const hour = new Intl.DateTimeFormat('fa-IR', {hour: '2-digit', minute: '2-digit',
    ...(value.size !== 'compact' ? {second: '2-digit'} : {}), hour12: value.hourFormat === '12'}).format(now);
  const coordinates = isFloating ? widgetPositionToPixels(position, viewport, widgetSize) : null;

  return <div ref={holder} dir="rtl" data-widget-theme={value.theme} data-widget-size={value.size}
    className={'clock-widget clock-widget--' + placement + (dragPreview ? ' clock-widget--dragging' : '')}
    style={coordinates ? {left: coordinates.left, top: coordinates.top} : undefined}>
    {value.mode !== 'hidden' && <div className={'live-clock clock-widget__display clock-widget__display--' + value.mode}
      role="timer" aria-live="off" aria-label={value.mode === 'both' ? 'ساعت و تاریخ دستگاه' : value.mode === 'date' ? 'تاریخ دستگاه' : 'ساعت دستگاه'}>
      {value.mode !== 'date' && <strong dir="ltr">{hour}</strong>}
      {value.mode !== 'clock' && <span><bdi>{date}</bdi></span>}
    </div>}
    {isFloating && <button type="button" className="clock-widget__handle"
      aria-label="جابجایی ساعت و تاریخ؛ با کلیدهای جهت‌دار حرکت دهید، Shift برای حرکت سریع"
      title="بکشید یا از کلیدهای جهت‌دار استفاده کنید" disabled={disabled}
      onPointerDown={onDragStart} onPointerMove={onDragMove}
      onPointerUp={onDragEnd} onPointerCancel={onDragEnd} onKeyDown={onHandleKey}>
      <Grip size={16} aria-hidden="true"/>
    </button>}
    <button ref={triggerRef} type="button" className="top-icon clock-widget__trigger"
      title="تنظیم ویجت ساعت و تاریخ" aria-label="تنظیم ویجت ساعت و تاریخ"
      aria-haspopup="dialog" aria-controls={open ? menuId : undefined} aria-expanded={open}
      onClick={() => {setMenuPosition(null);setOpen(previous => !previous);}}>
      <Clock3 size={17}/><Settings2 size={10}/>
    </button>
    {open && typeof document !== 'undefined' && createPortal(<div ref={menuRef} id={menuId}
      className="clock-widget clock-widget__menu" dir="rtl" data-widget-theme={value.theme}
      role="dialog" aria-label="تنظیم سریع ویجت ساعت و تاریخ"
      style={{...(menuPosition || {left: POPOVER_INSET, top: POPOVER_INSET}),
        visibility: menuPosition ? 'visible' : 'hidden'}}>
      <div className="clock-widget__menu-header"><strong>ساعت و تاریخ</strong>
        <button type="button" onClick={() => setOpen(false)} aria-label="بستن تنظیمات">×</button></div>
      <div className="clock-widget__quick">
        <SettingChoices label="نمایش" items={CLOCK_WIDGET_CHOICES} value={value.mode} disabled={disabled}
          onChange={nextMode => commit({...value, mode: nextMode})}/>
        {settings !== undefined && <label className="clock-widget__placement">
          <span>محل قرارگیری</span>
          <select value={value.placement} disabled={disabled}
            onChange={event => commit({...value, placement: event.target.value})}>
            {PLACEMENT_CHOICES.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>}
      </div>
      {settings !== undefined && (onOpenSettings
        ? <button className="clock-widget__more-button" type="button" onClick={() => {
            setOpen(false);onOpenSettings();
          }}>تنظیمات کامل <Settings2 size={14} aria-hidden="true"/></button>
        : <details className="clock-widget__more">
            <summary>تنظیمات پیشرفته</summary>
            <WidgetSettings settings={value} onChange={commit} disabled={disabled} embedded/>
          </details>)}
    </div>, document.body)}
  </div>;
}
