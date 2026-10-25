// Planner stores personal, device-local information. It never edits shared board tasks.
export const PLANNER_VERSION = 1;
const PREFIX = 'madar-planner-private-v1:';
const FREQUENCIES = new Set(['none', 'daily', 'weekly', 'monthly']);
const DAY_MS = 86400000;
const dateFields = new Intl.DateTimeFormat('en-US-u-ca-persian', {
  year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC'
});

export function validISO(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + 'T12:00:00Z');
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

export function isoToday(now = new Date()) {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return year + '-' + month + '-' + day;
}

export function shiftISO(value, days) {
  if (!validISO(value) || !Number.isInteger(days) || Math.abs(days) > 50000) throw Error('تاریخ نامعتبر است.');
  const date = new Date(value + 'T12:00:00Z');
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function normalizeRepeat(input) {
  const frequency = typeof input === 'string' ? input : input?.frequency || 'none';
  const interval = typeof input === 'object' && input !== null ? input.interval ?? 1 : 1;
  const calendar = typeof input === 'object' && input !== null ? input.calendar ?? 'gregorian' : 'gregorian';
  if (!FREQUENCIES.has(frequency) || !Number.isInteger(interval) || interval < 1 || interval > 12 ||
    !['gregorian', 'jalali'].includes(calendar)) {
    throw Error('الگوی تکرار نامعتبر است.');
  }
  return {frequency, interval, calendar};
}

export function nextRecurringDate(anchor, repeat, after = anchor) {
  const rule = normalizeRepeat(repeat);
  if (!validISO(anchor) || !validISO(after)) throw Error('تاریخ تکرار نامعتبر است.');
  if (rule.frequency === 'none') return null;
  const base = new Date(anchor + 'T12:00:00Z');
  const elapsed = Math.max(0, Math.floor((Date.parse(after + 'T12:00:00Z') - base.getTime()) / DAY_MS));
  if (rule.frequency === 'daily' || rule.frequency === 'weekly') {
    const step = rule.interval * (rule.frequency === 'weekly' ? 7 : 1);
    return shiftISO(anchor, (Math.floor(elapsed / step) + 1) * step);
  }
  if (rule.calendar === 'jalali') {
    const baseP = persianParts(anchor);
    const afterP = persianParts(after);
    const difference = (afterP.year - baseP.year) * 12 + afterP.month - baseP.month;
    let n = Math.max(1, Math.floor(difference / rule.interval));
    const at = index => {
      const targetMonthNumber = baseP.month - 1 + index * rule.interval;
      const year = baseP.year + Math.floor(targetMonthNumber / 12);
      const month = ((targetMonthNumber % 12) + 12) % 12 + 1;
      const nextYear = month === 12 ? year + 1 : year;
      const nextMonth = month === 12 ? 1 : month + 1;
      const first = isoPersian(year, month, 1);
      const end = isoPersian(nextYear, nextMonth, 1);
      const length = Math.round((Date.parse(end + 'T12:00:00Z') - Date.parse(first + 'T12:00:00Z')) / DAY_MS);
      return shiftISO(first, Math.min(baseP.day, length) - 1);
    };
    while (at(n) <= after) n++;
    return at(n);
  }
  const afterDate = new Date(after + 'T12:00:00Z');
  const monthDifference = (afterDate.getUTCFullYear() - base.getUTCFullYear()) * 12
    + afterDate.getUTCMonth() - base.getUTCMonth();
  let n = Math.max(1, Math.floor(monthDifference / rule.interval));
  // Keep the original day-of-month anchor, including after short February.
  const at = index => {
    const year = base.getUTCFullYear();
    const month = base.getUTCMonth() + index * rule.interval;
    const monthStart = new Date(Date.UTC(year, month, 1, 12));
    const monthEnd = new Date(Date.UTC(monthStart.getUTCFullYear(), monthStart.getUTCMonth() + 1, 0, 12));
    const day = Math.min(base.getUTCDate(), monthEnd.getUTCDate());
    return new Date(Date.UTC(monthStart.getUTCFullYear(), monthStart.getUTCMonth(), day, 12)).toISOString().slice(0, 10);
  };
  while (at(n) <= after) n++;
  return at(n);
}

const safeText = (value, size = 240) => typeof value === 'string' ? value.trim().slice(0, size) : '';
const safeId = value => typeof value === 'string' && /^[\w.:-]{1,120}$/.test(value);
const validTime = time => typeof time === 'string' && (/^([01]\d|2[0-3]):[0-5]\d$/.test(time) || time === '');

export function emptyPlanner() {
  return {version: PLANNER_VERSION, inbox: [], entries: []};
}

export function storageKey(accountId) {
  if (typeof accountId !== 'string' || !accountId.trim() || accountId.length > 120) {
    throw Error('شناسه حساب محلی مشخص نیست.');
  }
  return PREFIX + encodeURIComponent(accountId.trim());
}

// Strict validation: do not silently overwrite corrupt or future-version data.
export function normalizePlanner(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || value.version !== PLANNER_VERSION ||
      !Array.isArray(value.inbox) || !Array.isArray(value.entries) ||
      value.inbox.length > 5000 || value.entries.length > 15000) {
    throw Error('اطلاعات شخصی Planner ناسازگار یا آسیب‌دیده است.');
  }
  const inboxIds = new Set();
  const entryIds = new Set();
  const inbox = value.inbox.map(raw => {
    if (!raw || typeof raw !== 'object' || !safeId(raw.id) || inboxIds.has(raw.id) ||
        !safeText(raw.title) || !validISO(raw.createdDate) ||
        (raw.dueDate !== '' && !validISO(raw.dueDate)) ||
        (raw.doneAt !== '' && !validISO(raw.doneAt)) ||
        ((raw.repeatAnchor ?? '') !== '' && !validISO(raw.repeatAnchor)) ||
        !validTime(raw.remindTime ?? '') ||
        ((raw.dismissedFor ?? '') !== '' && !validISO(raw.dismissedFor))) {
      throw Error('رکورد صندوق شخصی نامعتبر است.');
    }
    const repeat = normalizeRepeat(raw.repeat);
    if (repeat.frequency !== 'none' && !validISO(raw.dueDate)) {
      throw Error('کار تکرارشونده باید تاریخ داشته باشد.');
    }
    if (raw.remindTime && !validISO(raw.dueDate)) {
      throw Error('یادآوری باید تاریخ داشته باشد.');
    }
    inboxIds.add(raw.id);
    return {
      id: raw.id, title: safeText(raw.title), notes: safeText(raw.notes, 3000),
      createdDate: raw.createdDate, dueDate: raw.dueDate, doneAt: raw.doneAt,
      repeatAnchor: raw.repeatAnchor ?? raw.dueDate,
      remindTime: raw.remindTime ?? '', dismissedFor: raw.dismissedFor ?? '', repeat
    };
  });
  const entries = value.entries.map(raw => {
    if (!raw || typeof raw !== 'object' || !safeId(raw.id) || entryIds.has(raw.id) ||
        !['personal', 'task'].includes(raw.source) || !safeId(raw.refId) || !validISO(raw.date)) {
      throw Error('برنامه روزانه نامعتبر است.');
    }
    entryIds.add(raw.id);
    return {id: raw.id, source: raw.source, refId: raw.refId, date: raw.date};
  });
  return {version: PLANNER_VERSION, inbox, entries};
}

export function readPlanner(storage, accountId) {
  const raw = storage.getItem(storageKey(accountId));
  if (raw === null) return emptyPlanner();
  try { return normalizePlanner(JSON.parse(raw)); }
  catch { throw Error('ذخیره شخصی قابل خواندن نیست؛ اطلاعات قبلی حفظ شد.'); }
}

export function writePlanner(storage, accountId, value) {
  const normalized = normalizePlanner(value);
  storage.setItem(storageKey(accountId), JSON.stringify(normalized));
  return normalized;
}

export function addInboxItem(state, {id, title, notes = '', createdDate, dueDate = '', repeat = 'none', remindTime = ''}) {
  const checked = normalizePlanner(state);
  const item = {id, title, notes, createdDate, dueDate, repeatAnchor: dueDate,
    doneAt: '', remindTime, dismissedFor: '', repeat: normalizeRepeat(repeat)};
  const parsed = normalizePlanner({...checked, inbox: [...checked.inbox, item]});
  return parsed;
}

export function editInboxItem(state, id, {title, notes = '', dueDate = '', repeat = 'none', remindTime = ''}) {
  const data = normalizePlanner(state);
  if (!data.inbox.some(item => item.id === id)) throw Error('کار شخصی پیدا نشد.');
  return normalizePlanner({...data, inbox: data.inbox.map(item => item.id === id ? {
    ...item, title, notes, dueDate, remindTime, repeat: normalizeRepeat(repeat),
    repeatAnchor: dueDate, dismissedFor: ''
  } : item)});
}

export function completeInboxItem(state, id, date) {
  const data = normalizePlanner(state);
  if (!validISO(date)) throw Error('تاریخ تکمیل نامعتبر است.');
  if (!data.inbox.some(i => i.id === id)) throw Error('کار شخصی پیدا نشد.');
  return normalizePlanner({...data, inbox: data.inbox.map(item => {
    if (item.id !== id || item.doneAt) return item;
    const next = item.repeat.frequency === 'none' ? null :
      nextRecurringDate(item.repeatAnchor || item.dueDate, item.repeat, date > item.dueDate ? date : item.dueDate);
    return {...item, dueDate: next || item.dueDate, doneAt: next ? '' : date, dismissedFor: ''};
  }), entries: data.entries.filter(e =>
    !(e.source === 'personal' && e.refId === id && e.date <= date))});
}

// Visible in the open app only. No browser/OS notifications or background scheduler.
export function dueReminders(state, now = new Date()) {
  const day = isoToday(now);
  const time = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
  return normalizePlanner(state).inbox.filter(item => !item.doneAt && item.remindTime &&
    item.dueDate && item.dueDate <= day && item.dismissedFor !== item.dueDate &&
    (item.dueDate < day || item.remindTime <= time));
}

export function dismissReminder(state, id) {
  const data = normalizePlanner(state);
  return normalizePlanner({...data, inbox: data.inbox.map(item =>
    item.id === id ? {...item, dismissedFor: item.dueDate} : item)});
}

export function planEntry(state, {id, source, refId, date}) {
  const data = normalizePlanner(state);
  if (source === 'personal' && !data.inbox.some(item => item.id === refId)) {
    throw Error('کار خصوصی پیدا نشد.');
  }
  if (data.entries.some(e => e.source === source && e.refId === refId && e.date === date)) return data;
  return normalizePlanner({...data, entries: [...data.entries, {id, source, refId, date}]});
}

export function unplanEntry(state, id) {
  const data = normalizePlanner(state);
  return {...data, entries: data.entries.filter(entry => entry.id !== id)};
}

export function removeInboxItem(state, id) {
  const data = normalizePlanner(state);
  return {...data, inbox: data.inbox.filter(item => item.id !== id),
    entries: data.entries.filter(entry => !(entry.source === 'personal' && entry.refId === id))};
}

export function agendaForDate(state, tasks, date) {
  if (!validISO(date)) throw Error('تاریخ روز نامعتبر است.');
  const data = normalizePlanner(state);
  const taskIndex = new Map((Array.isArray(tasks) ? tasks : []).filter(t => t && !t.archived).map(t => [t.id, t]));
  const personalIndex = new Map(data.inbox.map(i => [i.id, i]));
  const result = [];
  const seen = new Set();
  const push = (source, record, planned = false, entryId = '') => {
    if (!record || (source === 'personal' && record.doneAt)) return;
    const key = source + ':' + record.id;
    if (seen.has(key)) return;
    seen.add(key);
    result.push({source, record, planned, entryId});
  };
  for (const entry of data.entries) {
    if (entry.date === date) push(entry.source,
      entry.source === 'personal' ? personalIndex.get(entry.refId) : taskIndex.get(entry.refId), true, entry.id);
  }
  for (const item of data.inbox) if (item.dueDate === date) push('personal', item);
  for (const task of taskIndex.values()) if (task.dueDate === date) push('task', task);
  return result;
}

function persianParts(iso) {
  return Object.fromEntries(dateFields.formatToParts(new Date(iso + 'T12:00:00Z')).map(p => [p.type, Number(p.value)]));
}

function isoPersian(year, month, day) {
  if (!Number.isInteger(year) || year < 1250 || year > 1601 || month < 1 || month > 12) {
    throw Error('تاریخ تکرار شمسی خارج از محدوده است.');
  }
  const start = Date.UTC(year + 621, 2, 18, 12);
  let low = 0;
  let high = 370;
  const key = year * 10000 + month * 100 + day;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const candidate = new Date(start + middle * DAY_MS);
    const actual = persianParts(candidate.toISOString().slice(0, 10));
    const actualKey = actual.year * 10000 + actual.month * 100 + actual.day;
    if (actualKey === key) return candidate.toISOString().slice(0, 10);
    if (actualKey < key) low = middle + 1;
    else high = middle - 1;
  }
  throw Error('تاریخ تکرار شمسی نامعتبر است.');
}

export function calendarDays(anchor, mode = 'month', calendar = 'jalali') {
  if (!validISO(anchor) || !['month', 'week', 'day'].includes(mode)) throw Error('نمای تقویم نامعتبر است.');
  if (mode === 'day') return [anchor];
  const weekStart = calendar === 'jalali' ? 6 : 1;
  const startWeek = iso => {
    const weekday = new Date(iso + 'T12:00:00Z').getUTCDay();
    return shiftISO(iso, -((weekday - weekStart + 7) % 7));
  };
  if (mode === 'week') return Array.from({length: 7}, (_, i) => shiftISO(startWeek(anchor), i));
  let first;
  let length;
  if (calendar === 'jalali') {
    const parts = persianParts(anchor);
    first = shiftISO(anchor, 1 - parts.day);
    let next = first;
    length = 0;
    while (length < 32 && persianParts(next).month === parts.month &&
      persianParts(next).year === parts.year) { length++; next = shiftISO(next, 1); }
  } else {
    const date = new Date(anchor + 'T12:00:00Z');
    first = date.getUTCFullYear() + '-' + String(date.getUTCMonth() + 1).padStart(2, '0') + '-01';
    length = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0, 12)).getUTCDate();
  }
  const start = startWeek(first);
  const weekOffset = Math.round((Date.parse(first + 'T12:00:00Z') - Date.parse(start + 'T12:00:00Z')) / DAY_MS);
  const count = Math.ceil((weekOffset + length) / 7) * 7;
  return Array.from({length: count}, (_, i) => shiftISO(start, i));
}
