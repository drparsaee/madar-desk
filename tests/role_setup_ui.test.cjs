const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const bundle=esbuild.buildSync({entryPoints:[path.join(root,'src/features.jsx')],
  bundle:true,platform:'node',format:'cjs',write:false,jsx:'automatic',
  loader:{'.css':'empty'},external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const loaded=new Module(path.join(root,'src','role-setup-ui-test.cjs'),module);
loaded.filename=path.join(root,'src','role-setup-ui-test.cjs');
loaded.paths=Module._nodeModulePaths(root);
loaded._compile(bundle,loaded.filename);
const {
  LAN_BUILTIN_DISPLAY_ROLES,lanCanAssignDisplayRole,lanDefaultDisplayRoleForUser,
  lanDisplayRolePayload,lanAvailableUserFeatures,SettingsPanel,
}=loaded.exports;

test('five display templates align with host IDs and never substitute for technical ACL',()=>{
  assert.deepEqual(LAN_BUILTIN_DISPLAY_ROLES.map(item=>item.id),
    ['superadmin','senior','middle','unit','employee']);
  assert.equal(lanDefaultDisplayRoleForUser({role:'admin'}),'superadmin');
  assert.equal(lanDefaultDisplayRoleForUser({role:'editor'}),'middle');
  assert.equal(lanDefaultDisplayRoleForUser({role:'viewer'}),'employee');
  assert.equal(lanDefaultDisplayRoleForUser({role:'editor',displayRole:'custom_a'}),'custom_a');
  assert.equal(lanCanAssignDisplayRole(LAN_BUILTIN_DISPLAY_ROLES,'superadmin','viewer'),false);
  assert.equal(lanCanAssignDisplayRole(LAN_BUILTIN_DISPLAY_ROLES,'superadmin','admin'),true);
  assert.equal(lanCanAssignDisplayRole(LAN_BUILTIN_DISPLAY_ROLES,'middle','admin'),false);
  assert.equal(lanCanAssignDisplayRole(LAN_BUILTIN_DISPLAY_ROLES,'middle','viewer'),true);
  assert.equal(lanCanAssignDisplayRole(LAN_BUILTIN_DISPLAY_ROLES,'employee','editor'),true);
  assert.equal(lanCanAssignDisplayRole(LAN_BUILTIN_DISPLAY_ROLES,'missing','admin'),false);
});

test('changing a display template never silently changes technical ACL or project scope',()=>{
  const source=fs.readFileSync(path.join(root,'src/features.jsx'),'utf8');
  const handler=source.match(/const changeDisplayRole=id=>\{([\s\S]*?)\n \};/);
  assert(handler,'displayRole selection handler must exist');
  assert(!handler[1].includes('setRole('),'presentation choice must not change technical role');
  assert(!handler[1].includes('setScope('),'presentation choice must not change project access');
  assert.match(source,/const \[role,setRole\]=useState\('viewer'\)/);
  assert.match(source,/const resetUserForm=\(\)=>\{[^\n]*setRole\('viewer'\)/);
  assert.match(source,/select value=\{role\} onChange=\{e=>\{setRole\(e\.target\.value\)/);
  assert.match(source,/disabled=\{busy\|\|invalidDisplayRole\|\|!name\.trim\(\)/);
});

test('custom role payload matches required LAN API contract and cannot extend its display tier',()=>{
  const all=lanDisplayRolePayload({id:'custom_1',label:' مسئول واحد ',displayMode:'operations',
    limited:false,features:[]});
  assert.deepEqual(Object.keys(all),['id','label','displayMode','features']);
  assert.equal(all.label,'مسئول واحد');
  assert(all.features.includes('planner'));
  assert(!all.features.includes('financeHub'));
  const reduced=lanDisplayRolePayload({id:'custom_1',label:'محدود',displayMode:'basic',
    limited:true,features:['cards','profile','financeHub','unknown','cards']});
  assert.deepEqual(reduced.features,['cards','profile']);
});

test('per-user feature restriction is bounded to assigned template and selected mode',()=>{
  const unit={id:'unit',displayMode:'operations',features:['cards','planner','financeHub','search']};
  assert.deepEqual(lanAvailableUserFeatures(unit,'basic'),['cards','search']);
  assert.deepEqual(lanAvailableUserFeatures(unit,'operations'),['cards','planner','search']);
  assert(!lanAvailableUserFeatures(unit,'basic').includes('planner'));
});

test('widget personalization appears in global settings independent of manager permission',()=>{
  const html=renderToStaticMarkup(React.createElement(SettingsPanel,{
    data:{stages:[],tasks:[],projects:[],settings:{}},onChange:()=>{},onClose:()=>{},
    onCalendarChange:()=>{},canManage:false,widgetSettings:{mode:'both'},onWidgetSettingsChange:()=>{},
  }));
  assert(html.includes('شخصی‌سازی ساعت و تاریخ'));
  assert(html.includes('پوسته'));
  assert(html.includes('محل قرارگیری'));
});
