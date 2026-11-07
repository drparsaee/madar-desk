import {plannerIdentity} from './planner_identity.js';

/** Presentation preferences only. Never use these checks as authorization. */
export const DEFAULT_INTERFACE_MODE = 'basic';
export const INTERFACE_MODES = Object.freeze(['basic', 'operations', 'finance']);
export const INTERFACE_MODE_OPTIONS = Object.freeze([
  Object.freeze({id:'basic', label:'ساده', description:'برد، فهرست، کارت، موعد، جست‌وجو و اعلان'}),
  Object.freeze({id:'operations', label:'تیم و عملیات', description:'همه ابزارهای ساده، همراه گزارش، برنامه‌ریزی، زمان‌بندی و گردش کار'}),
  Object.freeze({id:'finance', label:'پیشرفته', description:'همه ابزارهای تیمی و گردش کار پیشرفته؛ حسابداری در برنامه جداگانه تراز است'}),
]);

export const INTERFACE_MODE_STORAGE_PREFIX = 'madar:interface-mode:v1:';
const MODE_RANK = Object.freeze({basic:0, operations:1, finance:2});

// Explicit allowlist: an unrecognized feature is never made visible implicitly.
// These keys correspond to existing App.jsx UI controls or documented future slots.
export const INTERFACE_FEATURE_TIERS = Object.freeze({
  workspaceSwitch:'basic', projects:'basic', boards:'basic', cards:'basic',
  createTask:'basic', createProject:'basic', createBoard:'basic',
  assignees:'basic', dueDate:'basic', reminder:'basic', priority:'basic',
  search:'basic', quickFilters:'basic', taskTrash:'basic', projectFiles:'basic',
  cardChecklist:'basic', cardAttachments:'basic', boardView:'basic', listView:'basic',
  // Essential access and recovery controls remain available in every mode.
  syncStatus:'basic', backupRestore:'basic', networkStatus:'basic',
  settings:'basic', profile:'basic', notifications:'basic',
  // Operations tools appear progressively after Basic.
  workspaceManagement:'operations', boardAdministration:'operations',
  projectAdministration:'operations', advancedFilters:'operations',
  activity:'operations', reporting:'operations', planner:'operations',
  timeDashboard:'operations', timelineView:'operations', taskTime:'operations',
  cardComments:'operations', customFields:'operations', boardFieldEditor:'operations',
  automationRules:'operations', trelloImport:'operations', calendarInterop:'operations',
  secureApiKeys:'operations', lanUserManagement:'operations',
  aiAgent:'finance',
});

const ADMIN_ONLY_FEATURES = new Set([
  'createProject','createBoard','boardAdministration','projectAdministration',
  'boardFieldEditor','automationRules','trelloImport','calendarInterop',
  'secureApiKeys','lanUserManagement', 'financeHub','projectFinance',
  'profitPeek','taskCostControls','checklistCostControls','projectPricing','aiAgent',
]);
const EDIT_ONLY_FEATURES = new Set(['createTask']);

export function isValidInterfaceMode(value) {
  return typeof value === 'string' && Object.prototype.hasOwnProperty.call(MODE_RANK, value);
}

export function normalizeInterfaceMode(value) {
  return isValidInterfaceMode(value) ? value : DEFAULT_INTERFACE_MODE;
}

/**
 * Visibility is deliberately narrower than authorization. The host, API and
 * existing canManage/canEdit paths must authorize every operation independently.
 * No financial feature is displayed without an explicit canManage=true.
 */
export function isInterfaceFeatureVisible(mode, feature, permissions={}) {
  if (!isValidInterfaceMode(mode)) return false;
  if (typeof feature !== 'string' || !Object.prototype.hasOwnProperty.call(INTERFACE_FEATURE_TIERS, feature)) return false;
  if (MODE_RANK[mode] < MODE_RANK[INTERFACE_FEATURE_TIERS[feature]]) return false;
  if (ADMIN_ONLY_FEATURES.has(feature) && permissions?.canManage !== true) return false;
  if (EDIT_ONLY_FEATURES.has(feature) && permissions?.canEdit !== true) return false;
  // Exposing a future AI entry point requires the host to declare it available.
  // Showing the entry point never authorizes AI execution or approval.
  if (feature === 'aiAgent' && permissions?.aiAvailable !== true) return false;
  return true;
}

/** A stable per-account setting; unknown remote identity must not share a key. */
export function interfaceModeStorageKey(status) {
  if (!status || !['solo','server','client'].includes(status.mode)) return null;
  if (status.mode !== 'solo' &&
      (typeof status?.user?.username !== 'string' || !status.user.username.trim())) return null;
  const accountId = plannerIdentity(status);
  if (typeof accountId !== 'string' || !accountId || accountId.length > 4096) return null;
  return INTERFACE_MODE_STORAGE_PREFIX + accountId;
}

/** Read failures, legacy values, unknown versions, and corrupt JSON all use Basic. */
export function readInterfaceMode(storage, status) {
  const key = interfaceModeStorageKey(status);
  if (!key || !storage || typeof storage.getItem !== 'function') return DEFAULT_INTERFACE_MODE;
  try {
    const raw = storage.getItem(key);
    if (raw === null || typeof raw !== 'string' || raw.length > 256) return DEFAULT_INTERFACE_MODE;
    const record = JSON.parse(raw);
    if (!record || typeof record !== 'object' || Array.isArray(record)) return DEFAULT_INTERFACE_MODE;
    const keys = Object.keys(record);
    if (keys.length !== 2 || !keys.includes('version') || !keys.includes('mode')) return DEFAULT_INTERFACE_MODE;
    if (record.version !== 1 || !isValidInterfaceMode(record.mode)) return DEFAULT_INTERFACE_MODE;
    return record.mode;
  } catch {
    return DEFAULT_INTERFACE_MODE;
  }
}

/** Invalid choices and unknown identities do not write anything. */
export function writeInterfaceMode(storage, status, mode) {
  const key = interfaceModeStorageKey(status);
  if (!key || !isValidInterfaceMode(mode) || !storage || typeof storage.setItem !== 'function') return false;
  try {
    storage.setItem(key, JSON.stringify({version:1, mode}));
    return true;
  } catch {
    return false;
  }
}
