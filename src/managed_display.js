import {INTERFACE_FEATURE_TIERS, isInterfaceFeatureVisible, isValidInterfaceMode} from './interface_mode.js';

// A display role controls presentation only. The host remains the sole
// authority for admin/editor/viewer, finance grants and project scopes.
export const LEGACY_DISPLAY_ROLES = Object.freeze({
  admin: Object.freeze({id:'superadmin',label:'مدیرکل',mode:'finance'}),
  editor: Object.freeze({id:'middle',label:'مدیر میانی',mode:'operations'}),
  viewer: Object.freeze({id:'employee',label:'کارمند',mode:'basic'}),
});
const BUILTIN_LABELS=Object.freeze({superadmin:'مدیرکل',senior:'مدیر ارشد',middle:'مدیر میانی',unit:'مدیر واحد',employee:'کارمند'});

const ESSENTIAL = new Set([
  'syncStatus','backupRestore','networkStatus','settings','profile',
  'notifications','workspaceSwitch','projects','boards','cards',
  'search','boardView','listView',
]);

/** Host-assigned settings take precedence over old account-local dropdowns. */
export function resolvedDisplayScope(status) {
  const account=status?.user;
  if (!account || !['solo','server','client'].includes(status.mode))
    return {id:'unknown',label:'نمای محدود',mode:'basic',features:[],managed:false};
  const base=LEGACY_DISPLAY_ROLES[account.role]||LEGACY_DISPLAY_ROLES.viewer;
  // A first-run personal owner sees the full interface. Network accounts,
  // including administrators, honor the display grants set by the host.
  const owner=status.mode==='solo';
  const allowed=Array.isArray(account.displayFeatures)
    ? Array.from(new Set(account.displayFeatures.filter(key=>Object.prototype.hasOwnProperty.call(INTERFACE_FEATURE_TIERS,key))))
    : null;
  return {
    id: owner?'superadmin':(typeof account.displayRole==='string'&&account.displayRole?account.displayRole:base.id),
    label: owner?'مدیرکل':(typeof account.displayRoleLabel==='string'&&account.displayRoleLabel?account.displayRoleLabel:
      BUILTIN_LABELS[account.displayRole]||base.label),
    mode: owner?'finance':(isValidInterfaceMode(account.displayMode)?account.displayMode:base.mode),
    features: owner?null:allowed,
    managed: account.displayRole!=null,
  };
}

export function isManagedFeatureVisible(scope,feature,permissions) {
  if (!isInterfaceFeatureVisible(scope?.mode,feature,permissions)) return false;
  if (ESSENTIAL.has(feature)) return true;
  return scope?.features===null || scope?.features===undefined || scope.features.includes(feature);
}
