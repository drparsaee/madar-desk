import React, {useEffect, useId, useMemo, useRef, useState} from 'react';
import {
  AlarmClock, CalendarDays, Check, ChevronLeft, ChevronRight, Circle, Clock3,
  Inbox, ListTodo, Pause, Play, Plus, RotateCcw, Trash2, X
} from 'lucide-react';
import {displayDate} from './productivity.jsx';
import {
  addInboxItem, agendaForDate, calendarDays, completeInboxItem, dismissReminder, editInboxItem,
  dueReminders, isoToday, normalizePlanner, planEntry, readPlanner,
  removeInboxItem, shiftISO, storageKey, unplanEntry, writePlanner
} from './planner.js';
import './planner.css';

const MODES = [
  {id: 'month', name: 'ماه'},
  {id: 'week', name: 'هفته'},
  {id: 'day', name: 'روز'}
];
const REPEATS = [
  {id: 'none', name: 'بدون تکرار'},
  {id: 'daily', name: 'روزانه'},
  {id: 'weekly', name: 'هفتگی'},
  {id: 'monthly', name: 'ماهانه'}
];
const WEEK_JALALI = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];
const WEEK_GREGORIAN = ['د', 'س', 'چ', 'پ', 'ج', 'ش', 'ی'];
const monthsFormatter = calendar => new Intl.DateTimeFormat(
  calendar === 'jalali' ? 'fa-IR-u-ca-persian' : 'fa-IR-u-ca-gregory',
  {year: 'numeric', month: 'long', timeZone: 'UTC'}
);
const pickerDate = iso => new Date(iso + 'T12:00:00Z');
const pickerDaysFormatter = calendar => new Intl.DateTimeFormat(
  calendar === 'jalali' ? 'fa-IR-u-ca-persian' : 'fa-IR-u-ca-gregory',
  {day: 'numeric', timeZone: 'UTC'}
);
const TIME_HOURS = Array.from({length: 24}, (_, i) => String(i).padStart(2, '0'));
const TIME_MINUTES = Array.from({length: 60}, (_, i) => String(i).padStart(2, '0'));

// Personal inbox dates remain ISO in storage; only the displayed calendar changes.
export function PlannerDatePicker({calendar = 'jalali', value = '', onChange, label = 'تاریخ انجام'}) {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState(value || isoToday());
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const popupId = useId();
  const labelId = useId();
  const valueId = useId();
  const monthFormat = useMemo(() => monthsFormatter(calendar), [calendar]);
  const dayFormat = useMemo(() => pickerDaysFormatter(calendar), [calendar]);
  const dates = useMemo(() => calendarDays(anchor, 'month', calendar), [anchor, calendar]);
  const month = monthFormat.format(pickerDate(anchor));
  const monthDates = dates.filter(date => monthFormat.format(pickerDate(date)) === month);

  useEffect(() => {
    if (!open) return;
    const onOutsideClick = event => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener('pointerdown', onOutsideClick);
    return () => document.removeEventListener('pointerdown', onOutsideClick);
  }, [open]);

  const changeMonth = direction => {
    setAnchor(shiftISO(direction < 0 ? monthDates[0] : monthDates[monthDates.length - 1], direction));
  };
  const choose = date => {
    onChange(date);
    setAnchor(date);
    setOpen(false);
    triggerRef.current?.focus();
  };
  const keyboardDay = (event, date) => {
    const offsets = {ArrowLeft: 1, ArrowRight: -1, ArrowDown: 7, ArrowUp: -7};
    if (!(event.key in offsets)) return;
    event.preventDefault();
    const target = shiftISO(date, offsets[event.key]);
    if (monthFormat.format(pickerDate(target)) !== month) setAnchor(target);
    // Focus follows the selected navigation day after React updates its grid.
    requestAnimationFrame(() => rootRef.current?.querySelector(`[data-date="${target}"]`)?.focus());
  };
  const openPicker = () => {
    setAnchor(value || isoToday());
    setOpen(current => !current);
  };
  return <div className="planner-date-picker" ref={rootRef}>
    <span className="planner-field-label" id={labelId}>{label} <small>{calendar === 'jalali' ? 'شمسی' : 'میلادی'}</small></span>
    <div className="planner-date-controls">
      <button type="button" ref={triggerRef} className="planner-date-trigger"
        aria-labelledby={`${labelId} ${valueId}`} aria-haspopup="dialog" aria-expanded={open}
        aria-controls={open ? popupId : undefined}
        onClick={openPicker}><CalendarDays size={16}/><span id={valueId}>{value ? displayDate(value, calendar, true) : 'انتخاب تاریخ از تقویم'}</span></button>
      {value && <button type="button" className="planner-date-clear" aria-label={'پاک کردن ' + label}
        title={'پاک کردن ' + label} onClick={() => {onChange(''); setOpen(false);}}><X size={16}/></button>}
    </div>
    {open && <div id={popupId} className="planner-date-popup" role="dialog" aria-modal="false" aria-label={'تقویم ' + label}
      onKeyDown={event => {
        if (event.key === 'Escape') {event.preventDefault(); setOpen(false); triggerRef.current?.focus();}
      }}>
      <div className="planner-date-nav">
        <button type="button" aria-label="ماه قبل" onClick={() => changeMonth(-1)}><ChevronRight size={17}/></button>
        <strong aria-live="polite">{month}</strong>
        <button type="button" aria-label="ماه بعد" onClick={() => changeMonth(1)}><ChevronLeft size={17}/></button>
        <button type="button" className="planner-date-today" onClick={() => choose(isoToday())}>امروز</button>
      </div>
      <div className="planner-date-weekdays">{(calendar === 'jalali' ? WEEK_JALALI : WEEK_GREGORIAN).map((text, i) => <span key={i}>{text}</span>)}</div>
      <div className="planner-date-grid">{dates.map(date => <button type="button" key={date} data-date={date}
        className={(date === value ? 'chosen ' : '') + (date === isoToday() ? 'today ' : '') +
          (monthFormat.format(pickerDate(date)) !== month ? 'outside' : '')}
        aria-label={displayDate(date, calendar, true)} aria-pressed={date === value}
        onKeyDown={event => keyboardDay(event, date)} onClick={() => choose(date)}>
        {dayFormat.format(pickerDate(date))}</button>)}</div>
    </div>}
  </div>;
}

export function PlannerTimePicker({value = '', onChange, disabled = false}) {
  const hour = value ? value.slice(0, 2) : '';
  const minute = value ? value.slice(3, 5) : '00';
  return <fieldset className="planner-time-picker" disabled={disabled}>
    <legend>ساعت یادآوری</legend>
    <div className="planner-time-controls">
      <select dir="ltr" aria-label="انتخاب ساعت یادآوری" value={hour}
        onChange={event => onChange(event.target.value ? `${event.target.value}:${minute}` : '')}>
        <option value="">بدون یادآوری</option>
        {TIME_HOURS.map(value => <option key={value} value={value}>{value}</option>)}
      </select>
      <span aria-hidden="true">:</span>
      <select dir="ltr" aria-label="انتخاب دقیقه یادآوری" value={minute} disabled={disabled || !hour}
        onChange={event => onChange(`${hour}:${event.target.value}`)}>
        {TIME_MINUTES.map(value => <option key={value} value={value}>{value}</option>)}
      </select>
    </div>
  </fieldset>;
}
const createId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2);
};

// Task references are read-only; they never enter private inbox records or shared task state.
function AgendaItem({item, onOpenTask, onFinish, onUnplan, projects}) {
  const {record, source, planned, entryId} = item;
  const name = projects.find(project => project.id === record.projectId)?.name;
  return <div className="planner-agenda-item">
    <span className={'planner-agenda-icon ' + source}>{source === 'personal' ? <Inbox size={16}/> : <ListTodo size={16}/>}</span>
    <div className="planner-agenda-name">
      {source === 'task'
        ? <button type="button" onClick={() => onOpenTask?.(record.id)}>{record.title}</button>
        : <strong>{record.title}</strong>}
      <small>{source === 'personal' ? 'شخصی، فقط این دستگاه' : (name || 'کارت برد')}
        {record.repeat?.frequency !== 'none' && source === 'personal' ? ' · تکرارشونده' : ''}
      </small>
    </div>
    {source === 'personal' && <button className="planner-icon-btn" type="button"
      title="انجام شد" aria-label={'تکمیل ' + record.title}
      onClick={() => onFinish(record.id)}><Check size={16}/></button>}
    {planned && <button type="button" className="planner-icon-btn" title="حذف از برنامه روز"
      aria-label={'حذف از برنامه ' + record.title} onClick={() => onUnplan(entryId)}><X size={15}/></button>}
  </div>;
}

export function PlannerPanel({tasks = [], projects = [], calendar = 'jalali', onClose, onOpenTask, accountId}) {
  const today = isoToday();
  const [identity, setIdentity] = useState(() =>
    typeof window !== 'undefined' && !window.madar ? 'solo' : '');
  const scope = typeof accountId === 'string' && accountId.trim() ? accountId.trim() : identity;
  const [loaded, setLoaded] = useState(null);
  const [error, setError] = useState('');
  const [day, setDay] = useState(today);
  const [mode, setMode] = useState('month');
  const [newTitle, setNewTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [remindTime, setRemindTime] = useState('');
  const [frequency, setFrequency] = useState('none');
  const [editing, setEditing] = useState(null);
  const [taskToPlan, setTaskToPlan] = useState('');
  const [includeDone, setIncludeDone] = useState(false);
  const [focusLength, setFocusLength] = useState(25);
  const [remaining, setRemaining] = useState(25 * 60);
  const [running, setRunning] = useState(false);
  const [currentTime, setCurrentTime] = useState(() => new Date());
  const deadline = useRef(null);

  useEffect(() => {
    if (typeof accountId === 'string' && accountId.trim()) return;
    if (typeof window === 'undefined' || !window.madar?.lanStatus) {setIdentity('solo'); return;}
    let active = true;
    setIdentity('');
    Promise.resolve().then(() => window.madar.lanStatus())
      .then(status => {
        const username = status?.user?.username;
        if (active) {
          if (typeof username === 'string' && username.trim()) setIdentity(username.trim());
          else setError('برای بازکردن فضای شخصی، شناسایی حساب ضروری است.');
        }
      })
      .catch(() => {if (active) setError('شناسایی حساب محلی امکان‌پذیر نشد.');});
    return () => {active = false;};
  }, [accountId]);

  useEffect(() => {
    setLoaded(null);
    if (!scope) return;
    try {
      storageKey(scope);
      setLoaded({scope, value: readPlanner(window.localStorage, scope)});
      setError('');
    } catch (exception) {
      setError(exception?.message || 'دسترسی به ذخیره شخصی ممکن نیست.');
    }
  }, [scope]);

  const state = loaded?.scope === scope ? loaded.value : null;
  const taskArray = Array.isArray(tasks) ? tasks : [];
  const projectArray = Array.isArray(projects) ? projects : [];
  const visibleTasks = useMemo(() => taskArray.filter(task => task?.id && !task.archived),
    [taskArray]);
  const selectedAgenda = useMemo(() => state ? agendaForDate(state, visibleTasks, day) : [],
    [state, visibleTasks, day]);
  const days = useMemo(() => calendarDays(day, mode, calendar), [day, mode, calendar]);
  const dayCounts = useMemo(() => {
    if (!state) return {};
    return Object.fromEntries(days.map(date => [date, agendaForDate(state, visibleTasks, date).length]));
  }, [state, visibleTasks, days]);
  const reminders = useMemo(() => state ? dueReminders(state, currentTime) : [],
    [state, currentTime]);
  const listedItems = state ? state.inbox.filter(item => includeDone || !item.doneAt) : [];
  const availableTasks = visibleTasks.filter(task => !selectedAgenda.some(
    item => item.source === 'task' && item.record.id === task.id));
  const periodTitle = monthsFormatter(calendar).format(new Date(day + 'T12:00:00Z'));

  const change = mutate => {
    if (!state) return false;
    try {
      const next = normalizePlanner(mutate(state));
      writePlanner(window.localStorage, scope, next);
      setLoaded({scope, value: next});
      setError('');
      return true;
    } catch (exception) {
      setError(exception?.message || 'ذخیره اطلاعات شخصی ناموفق بود.');
      return false;
    }
  };
  const addItem = event => {
    event.preventDefault();
    if (!newTitle.trim()) return;
    const saved = change(state => addInboxItem(state, {
      id: createId(), title: newTitle, notes,
      createdDate: isoToday(), dueDate,
      repeat: {frequency, interval: 1, calendar}, remindTime
    }));
    if (saved) {
      setNewTitle(''); setNotes(''); setDueDate(''); setFrequency('none'); setRemindTime('');
    }
  };
  const finish = id => change(state => completeInboxItem(state, id, day));
  const planPersonal = id => change(state => planEntry(state,
    {id: createId(), source: 'personal', refId: id, date: day}));
  const planTask = () => {
    if (!taskToPlan || !visibleTasks.some(task => task.id === taskToPlan)) return;
    change(state => planEntry(state, {id: createId(), source: 'task', refId: taskToPlan, date: day}));
    setTaskToPlan('');
  };
  const saveEdit = event => {
    event.preventDefault();
    if (!editing) return;
    if (change(state => editInboxItem(state, editing.id, {
      title: editing.title, notes: editing.notes, dueDate: editing.dueDate,
      repeat: editing.repeat, remindTime: editing.remindTime
    }))) setEditing(null);
  };
  const navigate = direction => {
    if (mode === 'day') {setDay(value => shiftISO(value, direction)); return;}
    if (mode === 'week') {setDay(value => shiftISO(value, 7 * direction)); return;}
    const currentDays = calendarDays(day, 'month', calendar);
    const middle = currentDays[Math.floor(currentDays.length / 2)];
    const fmt = monthsFormatter(calendar);
    const title = fmt.format(new Date(middle + 'T12:00:00Z'));
    const monthDays = currentDays.filter(date => fmt.format(new Date(date + 'T12:00:00Z')) === title);
    setDay(direction < 0 ? shiftISO(monthDays[0], -1) : shiftISO(monthDays[monthDays.length - 1], 1));
  };
  useEffect(() => {
    const interval = setInterval(() => setCurrentTime(new Date()), 30000);
    return () => clearInterval(interval);
  }, []);
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(() => {
      const left = Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000));
      setRemaining(left);
      if (!left) setRunning(false);
    }, 250);
    return () => clearInterval(interval);
  }, [running]);
  const toggleFocus = () => {
    if (running) {
      setRemaining(Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000)));
      setRunning(false);
    } else if (remaining > 0) {
      deadline.current = Date.now() + remaining * 1000;
      setRunning(true);
    }
  };
  const chooseFocus = minutes => {
    setRunning(false);
    setFocusLength(minutes);
    setRemaining(minutes * 60);
  };
  const fmtTime = seconds => String(Math.floor(seconds / 60)).padStart(2, '0') + ':' +
    String(seconds % 60).padStart(2, '0');

  return <div className="planner-overlay" role="presentation" onMouseDown={event => {
    if (event.target === event.currentTarget) onClose?.();
  }}>
    <section className="planner-panel" role="dialog" aria-modal="true" aria-label="برنامه‌ریز شخصی" dir="rtl">
      <header className="planner-head">
        <div><span className="planner-eyebrow"><CalendarDays size={15}/> فضای شخصی مدار</span>
          <h2>برنامه‌ریز من</h2>
          <small>صندوق شخصی، تقویم و برنامه امروز</small>
        </div>
        <button type="button" className="planner-close" onClick={onClose} aria-label="بستن"><X size={20}/></button>
      </header>
      <div className="planner-privacy">اطلاعات صندوق و برنامه روزانه فقط در حافظه همین برنامه روی این دستگاه ثبت می‌شود.
        این حافظه رمزنگاری‌شده نیست و کاربران دارای دسترسی به همین پروفایل ویندوز یا مرورگر می‌توانند آن را بخوانند.
      </div>
      {error && <p className="planner-error" role="alert">{error}</p>}
      {!state ? <div className="planner-empty">ذخیره شخصی در دسترس نیست. اطلاعات موجود بازنویسی نمی‌شود.</div> :
        <div className="planner-columns">
          <div className="planner-main">
            {!!reminders.length && <div className="planner-reminders" role="status">
              <strong><AlarmClock size={17}/> یادآوری‌های موعدرسیده</strong>
              {reminders.map(item => <div key={item.id}>
                <span>{item.title} · {displayDate(item.dueDate, calendar, true)}، {item.remindTime}</span>
                <button type="button" onClick={() => change(state => dismissReminder(state, item.id))}>متوجه شدم</button>
              </div>)}
            </div>}
            <div className="planner-calendar-header">
              <div className="planner-navigation">
                <button type="button" onClick={() => navigate(-1)} aria-label="دوره قبل"><ChevronRight size={18}/></button>
                <strong>{periodTitle}</strong>
                <button type="button" onClick={() => navigate(1)} aria-label="دوره بعد"><ChevronLeft size={18}/></button>
                <button type="button" className="planner-today" onClick={() => setDay(isoToday())}>امروز</button>
              </div>
              <div className="planner-view-modes">{MODES.map(value =>
                <button type="button" key={value.id} className={mode === value.id ? 'active' : ''}
                  onClick={() => setMode(value.id)}>{value.name}</button>)}</div>
            </div>
            {mode !== 'day' && <div className="planner-weeknames">
              {(calendar === 'jalali' ? WEEK_JALALI : WEEK_GREGORIAN).map((dayName, i) =>
                <span key={i}>{dayName}</span>)}
            </div>}
            <div className={'planner-days ' + (mode === 'day' ? 'single' : '')}>
              {days.map(date => <button type="button" key={date} className={
                (date === day ? 'selected ' : '') + (date === today ? 'today ' : '')}
                onClick={() => setDay(date)} title={displayDate(date, calendar, true)}
                aria-label={displayDate(date, calendar, true)} aria-pressed={date === day}>
                <span>{new Intl.DateTimeFormat(calendar === 'jalali' ? 'fa-IR-u-ca-persian' : 'fa-IR',
                  {day: 'numeric'}).format(new Date(date + 'T12:00:00Z'))}</span>
                {!!dayCounts[date] && <small>{dayCounts[date].toLocaleString('fa-IR')} کار</small>}
              </button>)}
            </div>
            <div className="planner-today-agenda">
              <div className="planner-section-title">
                <h3><ListTodo size={18}/> برنامه {displayDate(day, calendar, true)}</h3>
                <small>{selectedAgenda.length.toLocaleString('fa-IR')} مورد</small>
              </div>
              {selectedAgenda.map(item => <AgendaItem key={item.source + item.record.id}
                item={item} projects={projectArray} onOpenTask={onOpenTask}
                onFinish={finish}
                onUnplan={id => change(value => unplanEntry(value, id))}/>)}
              {!selectedAgenda.length && <p className="planner-empty">هنوز کاری برای این روز برنامه‌ریزی نشده است.</p>}
              <div className="planner-add-task">
                <select aria-label="انتخاب کارت از برد" value={taskToPlan}
                  onChange={event => setTaskToPlan(event.target.value)}>
                  <option value="">افزودن کارت موجود به برنامه این روز</option>
                  {availableTasks.map(task => <option key={task.id} value={task.id}>{task.title}</option>)}
                </select>
                <button type="button" disabled={!taskToPlan} onClick={planTask}><Plus size={16}/> افزودن</button>
              </div>
              <small className="planner-note">کارت‌ها فقط به برنامه شخصی پیوند داده می‌شوند؛ وضعیت برد تغییر نمی‌کند.</small>
            </div>
            <div className="planner-focus">
              <div><h3><Clock3 size={18}/> زمان تمرکز</h3><small>تایمر تا زمانی که این صفحه باز است کار می‌کند.</small></div>
              <div className="planner-focus-controls">
                <div className="planner-focus-length">{[15, 25, 45].map(minutes =>
                  <button type="button" key={minutes} className={focusLength === minutes ? 'active' : ''}
                    onClick={() => chooseFocus(minutes)}>{minutes.toLocaleString('fa-IR')} دقیقه</button>)}</div>
                <strong dir="ltr" aria-live="off">{fmtTime(remaining)}</strong>
                <button type="button" className="planner-primary" onClick={toggleFocus}
                  disabled={remaining === 0}>{running ? <Pause size={16}/> : <Play size={16}/>}
                  {running ? 'توقف' : 'شروع'}</button>
                <button type="button" className="planner-icon-btn" title="تنظیم مجدد"
                  onClick={() => chooseFocus(focusLength)}><RotateCcw size={16}/></button>
              </div>
            </div>
          </div>
          <aside className="planner-inbox">
            <div className="planner-section-title"><h3><Inbox size={18}/> صندوق شخصی</h3>
              <small>{state.inbox.filter(item => !item.doneAt).length.toLocaleString('fa-IR')} باز</small>
            </div>
            <p className="planner-note">این صندوق مستقل از ستون «صندوق ورودی» بردهای مشترک است.</p>
            <form onSubmit={addItem} className="planner-create">
              <label>عنوان<input maxLength={240} required value={newTitle}
                onChange={event => setNewTitle(event.target.value)}
                placeholder="یادداشت یا کار شخصی..."/></label>
              <label>توضیح اختیاری<textarea maxLength={3000} rows={2} value={notes}
                onChange={event => setNotes(event.target.value)} placeholder="جزئیات خصوصی"/></label>
              <PlannerDatePicker calendar={calendar} value={dueDate} onChange={value => {
                setDueDate(value); if (!value) setRemindTime('');
              }} label="تاریخ انجام"/>
              <PlannerTimePicker value={remindTime} onChange={setRemindTime} disabled={!dueDate}/>
              <label>تکرار<select value={frequency} onChange={event => setFrequency(event.target.value)}>
                {REPEATS.map(repeat => <option key={repeat.id} value={repeat.id}>{repeat.name}</option>)}
              </select></label>
              <button className="planner-primary" disabled={!newTitle.trim() || (frequency !== 'none' && !dueDate) || (!!remindTime && !dueDate)}
                type="submit"><Plus size={17}/> افزودن به صندوق شخصی</button>
            </form>
            <div className="planner-inbox-heading">
              <h4>موارد ثبت‌شده</h4>
              <label><input type="checkbox" checked={includeDone} onChange={event => setIncludeDone(event.target.checked)}/>نمایش تکمیل‌شده‌ها</label>
            </div>
            <div className="planner-inbox-list">
              {listedItems.map(item => <div className={'planner-inbox-item ' + (item.doneAt ? 'done' : '')} key={item.id}>
                {editing?.id === item.id ? <form className="planner-create" onSubmit={saveEdit}>
                  <label>عنوان<input required maxLength={240} value={editing.title}
                    onChange={event => setEditing({...editing, title: event.target.value})}/></label>
                  <label>توضیح<textarea rows={2} maxLength={3000} value={editing.notes}
                    onChange={event => setEditing({...editing, notes: event.target.value})}/></label>
                  <PlannerDatePicker calendar={calendar} value={editing.dueDate}
                    onChange={value => setEditing(current => ({...current, dueDate: value,
                      remindTime: value ? current.remindTime : ''}))} label="تاریخ انجام"/>
                  <PlannerTimePicker value={editing.remindTime} disabled={!editing.dueDate}
                    onChange={value => setEditing(current => ({...current, remindTime: value}))}/>
                  <label>تکرار<select value={editing.repeat.frequency}
                    onChange={event => setEditing({...editing,
                      repeat: {...editing.repeat, frequency: event.target.value, calendar}})}>
                    {REPEATS.map(rule => <option key={rule.id} value={rule.id}>{rule.name}</option>)}
                  </select></label>
                  <div className="planner-item-actions">
                    <button type="button" onClick={() => setEditing(null)}>انصراف</button>
                    <button type="submit" disabled={!editing.title.trim() ||
                      (editing.repeat.frequency !== 'none' && !editing.dueDate) ||
                      (!!editing.remindTime && !editing.dueDate)}>ذخیره</button>
                  </div>
                </form> : <>
                <div className="planner-inbox-title"><span>{item.doneAt ? <Check size={16}/> : <Circle size={16}/>}</span>
                  <strong>{item.title}</strong></div>
                {!!item.notes && <p>{item.notes}</p>}
                {!!item.dueDate && <small><AlarmClock size={13}/>{displayDate(item.dueDate, calendar, true)}</small>}
                {item.repeat.frequency !== 'none' && <small>تکرار: {REPEATS.find(rule => rule.id === item.repeat.frequency)?.name}</small>}
                <div className="planner-item-actions">
                  {!item.doneAt && <button type="button" onClick={() => planPersonal(item.id)}>برنامه {displayDate(day, calendar)}</button>}
                  {!item.doneAt && <button type="button" onClick={() => setEditing({
                    id: item.id, title: item.title, notes: item.notes, dueDate: item.dueDate,
                    repeat: item.repeat, remindTime: item.remindTime
                  })}>ویرایش</button>}
                  {!item.doneAt && <button type="button" title="تکمیل" onClick={() => finish(item.id)}><Check size={16}/></button>}
                  <button type="button" title="حذف" aria-label={'حذف ' + item.title} onClick={() => {
                    if (window.confirm('این یادداشت شخصی حذف شود؟')) change(state => removeInboxItem(state, item.id));
                  }}><Trash2 size={15}/></button>
                </div></>}
              </div>)}
              {!listedItems.length && <p className="planner-empty">صندوق شخصی خالی است.</p>}
            </div>
          </aside>
        </div>}
    </section>
  </div>;
}

export default PlannerPanel;
