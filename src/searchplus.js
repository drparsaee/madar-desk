// Search only task metadata that is appropriate for every board reader.
// Never index finance records, project prices, task costs, receipts or profit.
const FIELD_NAMES = {
  title: 'title', name: 'title', 'عنوان': 'title',
  description: 'description', desc: 'description', 'توضیح': 'description', 'توضیحات': 'description',
  label: 'label', labels: 'label', tag: 'label', 'برچسب': 'label',
  checklist: 'checklist', step: 'checklist', 'چکلیست': 'checklist', 'مرحله': 'checklist',
  report: 'report', reports: 'report', 'گزارش': 'report',
  project: 'project', 'پروژه': 'project',
  member: 'member', assignee: 'member', user: 'member', 'عضو': 'member', 'مسئول': 'member',
  status: 'status', stage: 'status', 'وضعیت': 'status',
  priority: 'priority', 'اولویت': 'priority',
  due: 'due', 'موعد': 'due',
  created: 'created', 'ایجاد': 'created'
};
const DATE_FIELDS = new Set(['due', 'created']);
const PRIORITY_LABELS = {high: 'بالا زیاد فوری', medium: 'متوسط عادی', low: 'کم پایین'};
const STATUS_LABELS = {
  inbox: 'صندوق ورودی', planned: 'برنامه ریزی', active: 'در حال انجام',
  review: 'در انتظار بررسی', done: 'تکمیل شده انجام شده'
};
const MAX_QUERY_LENGTH = 2000;
const PERSIAN_DATES = new Intl.DateTimeFormat('en-US-u-ca-persian', {
  year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'UTC'
});

export function normalizeSearchText(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .replace(/[۰-۹]/g, c => String(c.charCodeAt(0) - 1776))
    .replace(/[٠-٩]/g, c => String(c.charCodeAt(0) - 1632))
    .replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').replace(/[ةۀ]/g, 'ه')
    .replace(/[\u064b-\u065f\u0670\u06d6-\u06ed\u0640]/g, '')
    .replace(/[\u200c\u200d\u200e\u200f\ufeff]/g, ' ')
    .toLocaleLowerCase('fa')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim().replace(/\s+/g, ' ');
}

function lex(query) {
  const parts = [];
  const source = String(query ?? '').slice(0, MAX_QUERY_LENGTH).replace(/[“”«»]/g, '"');
  let current = '';
  let quoted = false;
  for (const char of source) {
    if (char === '"') { quoted = !quoted; current += char; continue; }
    if (!quoted && (char === '|' || /\s/u.test(char))) {
      if (current) parts.push(current);
      current = '';
      if (char === '|') parts.push('|');
      continue;
    }
    current += char;
  }
  if (current) parts.push(current);
  return parts;
}

function validGregorian(year, month, day) {
  if (year < 1700 || year > 9999 || month < 1 || month > 12 || day < 1 || day > 31) return false;
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function parseDate(value) {
  const match = /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/.exec(value);
  if (!match) return null;
  const [year, month, day] = match.slice(1).map(Number);
  if (validGregorian(year, month, day)) {
    return {calendar: 'gregorian', key: year * 10000 + month * 100 + day};
  }
  if (year < 1250 || year > 1600 || month < 1 || month > 12 || day < 1 || day > (month <= 6 ? 31 : 30)) return null;
  // Persian dates are converted only while compiling a query, not per task.
  const key = year * 10000 + month * 100 + day;
  const start = Date.UTC(year + 621, 2, 18);
  // Binary search works because Persian calendar dates advance monotonically.
  let low = 0, high = 370;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    const candidate = new Date(start + middle * 86400000);
    const parts = PERSIAN_DATES.formatToParts(candidate);
    const fields = Object.fromEntries(parts.map(part => [part.type, part.value]));
    const actual = Number(fields.year) * 10000 + Number(fields.month) * 100 + Number(fields.day);
    if (actual === key) return {calendar: 'gregorian', key: Number(candidate.toISOString().slice(0, 10).replace(/-/g, ''))};
    if (actual < key) low = middle + 1;
    else high = middle - 1;
  }
  return null;
}

function parseDateCondition(field, op, value) {
  const raw = value.trim();
  if (!raw) return {field, invalid: true};
  if (op === ':' && raw.includes('..')) {
    const [from, to, ...rest] = raw.split('..');
    const start = from ? parseDate(from) : null;
    const end = to ? parseDate(to) : null;
    if (rest.length || (!start && !end) || (from && !start) || (to && !end) || (start && end && start.key > end.key)) return {field, invalid: true};
    return {field, start: start?.key ?? null, end: end?.key ?? null};
  }
  const parsed = parseDate(raw);
  if (!parsed) return {field, invalid: true};
  const key = parsed.key;
  if (op === '>') return {field, start: key + 1, end: null};
  if (op === '>=') return {field, start: key, end: null};
  if (op === '<') return {field, start: null, end: key - 1};
  if (op === '<=') return {field, start: null, end: key};
  return {field, start: key, end: key};
}

function parseAtom(source) {
  const excluded = source.startsWith('-') || source.startsWith('!');
  const body = excluded ? source.slice(1) : source;
  const matched = /^([^:<>!=]+)(:|>=|<=|>|<)(.*)$/u.exec(body);
  const canonicalField = matched && FIELD_NAMES[matched[1].toLocaleLowerCase('fa')];
  const field = canonicalField || 'any';
  const value = (canonicalField ? matched[3] : body).replace(/"/g, '');
  const expression = DATE_FIELDS.has(field)
    ? parseDateCondition(field, matched[2], value.replace(/[۰-۹٠-٩]/g, c => String(c.charCodeAt(0) - (c.charCodeAt(0) >= 1776 ? 1776 : 1632))))
    : {field, value: normalizeSearchText(value), invalid: !normalizeSearchText(value)};
  return {...expression, excluded};
}

// Space means AND, | or OR means OR, "..." keeps the phrase together.
// Negation is an adjacent -term or -field:value. All user input is literal.
export function parseTaskQuery(query) {
  const atoms = lex(query);
  const clauses = [[]];
  for (let index = 0; index < atoms.length; index++) {
    let atom = atoms[index];
    if (atom === '|' || atom.toLocaleLowerCase('en') === 'or' || atom === 'یا') {
      if (clauses[clauses.length - 1].length) clauses.push([]);
      continue;
    }
    if (/^[^:]+:$/.test(atom) && index + 1 < atoms.length && FIELD_NAMES[atom.slice(0, -1).toLocaleLowerCase('fa')]) {
      const next = atoms[index + 1];
      if (next !== '|' && next.toLocaleLowerCase('en') !== 'or') { atom += next; index++; }
    }
    const parsed = parseAtom(atom);
    if (parsed.invalid || parsed.value || parsed.start !== undefined) clauses[clauses.length - 1].push(parsed);
  }
  return clauses.filter(group => group.length);
}

function labelName(item) {
  return typeof item === 'string' ? item : (item?.name || item?.label || '');
}

function plainText(value) {
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return '';
}

function taskFields(task, context) {
  const project = (context.projects || []).find(item => item?.id === task.projectId);
  const statuses = [task.listId, task.status].filter(Boolean);
  const stageNames = (context.stages || []).filter(stage => statuses.includes(stage?.id)).map(stage => stage.label);
  const memberNames = (task.assignees || []).map(assignee => {
    const username = typeof assignee === 'string' ? assignee : assignee?.username;
    const member = (context.users || []).find(user => user?.username === username);
    return [username, member?.displayName].filter(Boolean).join(' ');
  });
  const checklist = [...(task.checklist || []), ...(task.checklists || []).flatMap(list => [list, ...(list?.items || [])])];
  const fields = {
    title: plainText(task.title),
    description: plainText(task.description),
    label: (task.labels || []).map(labelName).join(' '),
    checklist: checklist.map(item => [item?.text, item?.title, item?.name].filter(Boolean).join(' ')).join(' '),
    report: (task.reports || []).map(report => [report?.summary, report?.agent].filter(Boolean).join(' ')).join(' '),
    project: [project?.name, project?.id, task.projectId].filter(Boolean).join(' '),
    member: memberNames.join(' '),
    status: [...statuses, ...stageNames, ...statuses.map(status => STATUS_LABELS[status] || '')].join(' '),
    priority: [task.priority, PRIORITY_LABELS[task.priority] || ''].join(' ')
  };
  fields.any = Object.values(fields).join(' ');
  return Object.fromEntries(Object.entries(fields).map(([name, text]) => [name, normalizeSearchText(text)]));
}

function matchAtom(task, fields, atom) {
  if (atom.invalid) return false;
  let found;
  if (DATE_FIELDS.has(atom.field)) {
    const raw = atom.field === 'due' ? task.dueDate : task.createdAt;
    const iso = /^\d{4}-\d{2}-\d{2}/.exec(String(raw || ''))?.[0];
    const date = iso ? parseDate(iso) : null;
    found = Boolean(date && (atom.start === null || date.key >= atom.start) && (atom.end === null || date.key <= atom.end));
  } else {
    found = Boolean(fields[atom.field]?.includes(atom.value));
  }
  return atom.excluded ? !found : found;
}

export function filterTasks(tasks, {query = '', projects = [], users = [], stages = []} = {}) {
  if (!Array.isArray(tasks)) return [];
  const clauses = parseTaskQuery(query);
  if (!clauses.length) return tasks.slice();
  const context = {projects, users, stages};
  return tasks.filter(task => {
    if (!task || typeof task !== 'object') return false;
    const fields = taskFields(task, context);
    return clauses.some(group => group.every(atom => matchAtom(task, fields, atom)));
  });
}

export function matchesTaskSearch(task, query, context = {}) {
  return filterTasks([task], {query, ...context}).length === 1;
}
