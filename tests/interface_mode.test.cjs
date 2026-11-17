const {test} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

function loadSource(name) {
  const source = path.resolve(__dirname, '../src/' + name);
  const compiled = esbuild.buildSync({
    entryPoints:[source], bundle:true, platform:'node', format:'cjs',
    external:['react','react-dom'], loader:{'.css':'empty'}, write:false,
  }).outputFiles[0].text;
  const filename = source.replace(/\.(js|jsx)$/, '.cjs');
  const moduleInstance = new Module(filename, module);
  moduleInstance.filename = filename;
  moduleInstance.paths = Module._nodeModulePaths(path.dirname(filename));
  moduleInstance._compile(compiled, filename);
  return moduleInstance.exports;
}

const m = loadSource('interface_mode.js');
const ui = loadSource('interface_mode.jsx');
const status = (username, mode='solo', url='')=>({mode,user:{username,role:'admin'},url});
const createStore=()=>{
  const records=new Map();
  const calls=[];
  return {
    records,calls,
    getItem:key=>records.has(key)?records.get(key):null,
    setItem:(key,value)=>{calls.push([key,value]);records.set(key,value);},
  };
};

test('the mode policy starts Basic, strictly rejects invalid identifiers, and uses an explicit allowlist',()=>{
  assert.deepEqual(m.INTERFACE_MODES,['basic','operations','finance']);
  for(const invalid of [null,undefined,{},0,'FINANCE','__proto__','constructor','finance-ai','operations ']){
    assert.equal(m.isValidInterfaceMode(invalid),false);
    assert.equal(m.normalizeInterfaceMode(invalid),'basic');
    assert.equal(m.isInterfaceFeatureVisible(invalid,'boards'),false);
  }
  assert.equal(m.isInterfaceFeatureVisible('finance','notAnActualFeature',{canManage:true}),false);
  assert.equal(m.isInterfaceFeatureVisible('basic','cards'),true);
  assert.equal(m.isInterfaceFeatureVisible('basic','reporting'),false);
  assert.equal(m.isInterfaceFeatureVisible('operations','reporting'),true);
  assert.equal(m.isInterfaceFeatureVisible('finance','reporting'),true);
});

test('each account and remote host has an independent versioned preference',()=>{
  const storage=createStore();
  const a=status('admin');
  const b=status('other');
  const clientA=status('admin','client','https://host-a.example:8420');
  const clientB=status('admin','client','https://host-b.example:8420');
  assert.equal(m.readInterfaceMode(storage,a),'basic');
  assert.equal(m.writeInterfaceMode(storage,a,'finance'),true);
  assert.equal(m.writeInterfaceMode(storage,b,'operations'),true);
  assert.equal(m.writeInterfaceMode(storage,clientA,'finance'),true);
  assert.equal(m.readInterfaceMode(storage,a),'finance');
  assert.equal(m.readInterfaceMode(storage,b),'operations');
  assert.equal(m.readInterfaceMode(storage,clientA),'finance');
  assert.equal(m.readInterfaceMode(storage,clientB),'basic');
  assert.equal(m.readInterfaceMode(storage,status('admin','server')),'basic');
  assert.equal(storage.records.size,3);
  for(const [key,value] of storage.records){
    assert.ok(key.startsWith(m.INTERFACE_MODE_STORAGE_PREFIX));
    assert.equal(JSON.parse(value).version,1);
  }
});

test('unknown identity never reads or writes a shared account key',()=>{
  const storage=createStore();
  const cases=[undefined,{}, {mode:'server',user:{}},
    {mode:'client',user:{username:'alex'}},
    {mode:'client',url:'not-a-url',user:{username:'alex'}},
    {mode:'bogus',user:{username:'alex'}}];
  for(const identity of cases){
    assert.equal(m.interfaceModeStorageKey(identity),null);
    assert.equal(m.readInterfaceMode(storage,identity),'basic');
    assert.equal(m.writeInterfaceMode(storage,identity,'finance'),false);
  }
  assert.equal(storage.calls.length,0);
});

test('corrupted and future schema preferences return Basic, never elevate visibility',()=>{
  const storage=createStore();
  const user=status('admin');
  const key=m.interfaceModeStorageKey(user);
  for(const raw of [
    'finance', '{', 'null', '[]', '"finance"',
    '{"version":1,"mode":"__proto__"}',
    '{"version":0,"mode":"finance"}',
    '{"version":2,"mode":"finance"}',
    '{"version":1,"mode":"finance","permissions":"admin"}',
    '{"version":1,"mode":false}', 'x'.repeat(257),
  ]){
    storage.records.set(key,raw);
    assert.equal(m.readInterfaceMode(storage,user),'basic',raw.slice(0,40));
  }
  assert.equal(m.writeInterfaceMode(storage,user,'toString'),false);
  assert.equal(m.writeInterfaceMode(storage,user,{}),false);
  assert.equal(storage.calls.length,0);
});

test('storage errors fail closed on load and report unsuccessful writes',()=>{
  const errors={getItem(){throw Error('private mode');},setItem(){throw Error('quota');}};
  assert.equal(m.readInterfaceMode(errors,status('alice')),'basic');
  assert.equal(m.writeInterfaceMode(errors,status('alice'),'finance'),false);
  assert.equal(m.readInterfaceMode(null,status('alice')),'basic');
  assert.equal(m.writeInterfaceMode(null,status('alice'),'finance'),false);
});

test('finance and privileged tool visibility never bypasses the existing permissions',()=>{
  const restricted=['financeHub','projectFinance','profitPeek','taskCostControls',
    'checklistCostControls','projectPricing','boardAdministration',
    'automationRules','secureApiKeys','aiAgent'];
  for(const feature of restricted){
    assert.equal(m.isInterfaceFeatureVisible('finance',feature,{canEdit:true,aiAvailable:true}),false,feature);
  }
  // These historical standalone-finance entry points are intentionally not
  // in the Madar UI allowlist after Taraz became the finance authority.
  for(const feature of ['financeHub','projectFinance','profitPeek',
    'taskCostControls','checklistCostControls','projectPricing',
    'accountingDashboard']){
    for(const mode of m.INTERFACE_MODES){
      assert.equal(m.isInterfaceFeatureVisible(mode,feature,{canManage:true}),false,
        `${feature}: ${mode} must not resurrect standalone finance`);
    }
  }
  assert.equal(m.isInterfaceFeatureVisible('operations','financeHub',{canManage:true}),false);
  assert.equal(m.isInterfaceFeatureVisible('basic','financeHub',{canManage:true}),false);
  assert.equal(m.isInterfaceFeatureVisible('finance','aiAgent',{canManage:true}),false);
  assert.equal(m.isInterfaceFeatureVisible('finance','aiAgent',{canManage:true,aiAvailable:true}),true);
  assert.equal(m.isInterfaceFeatureVisible('basic','backupRestore',{}),true);
  assert.equal(m.isInterfaceFeatureVisible('basic','networkStatus',{}),true);
  assert.equal(m.isInterfaceFeatureVisible('basic','settings',{}),true);
  assert.equal(m.isInterfaceFeatureVisible('basic','createTask',{canEdit:false}),false);
  assert.equal(m.isInterfaceFeatureVisible('basic','createTask',{canEdit:true}),true);
});

test('preference switch never mutates task, finance, or project data',()=>{
  const state={tasks:[{id:'t1',title:'کار',cost:2500,checklist:[{cost:100}]}],
    finance:{invoices:[{id:'inv1',amount:6000}]},
    projects:[{id:'p1',price:25000}],users:[{role:'editor'}]};
  const before=JSON.stringify(state);
  const storage=createStore();
  assert.equal(m.writeInterfaceMode(storage,status('admin'),'finance'),true);
  assert.equal(m.writeInterfaceMode(storage,status('admin'),'basic'),true);
  assert.equal(m.readInterfaceMode(storage,status('admin')),'basic');
  assert.equal(JSON.stringify(state),before);
  assert.equal(storage.records.size,1);
});

test('SSR emits an accessible, Persian controlled selector with all choices',()=>{
  const html=renderToStaticMarkup(React.createElement(ui.InterfaceModeSelector,{mode:'operations',id:'simple-mode'}));
  assert.match(html,/for="simple-mode"/);
  assert.match(html,/id="simple-mode"/);
  assert.match(html,/aria-describedby="simple-mode-description"/);
  assert.match(html,/id="simple-mode-description"/);
  assert.match(html,/dir="rtl"/);
  assert.match(html,/value="basic"/);
  assert.match(html,/value="operations" selected=""/);
  assert.match(html,/value="finance"/);
  assert.match(html,/تیم و عملیات/);
  assert.match(html,/report|گزارش/);
  const bad=renderToStaticMarkup(React.createElement(ui.InterfaceModeSelector,{mode:'invalid'}));
  assert.match(bad,/value="basic" selected=""/);
});

test('selector only emits valid changed values, respects disabled, and does not write storage',()=>{
  const seen=[];
  const component=ui.InterfaceModeSelector({mode:'basic',onChange:next=>seen.push(next)});
  const select=component.props.children[1];
  select.props.onChange({target:{value:'finance'}});
  select.props.onChange({target:{value:'not-mode'}});
  select.props.onChange({target:{value:'basic'}});
  assert.deepEqual(seen,['finance']);
  const locked=ui.InterfaceModeSelector({mode:'finance',disabled:true,onChange:next=>seen.push(next)});
  locked.props.children[1].props.onChange({target:{value:'operations'}});
  assert.deepEqual(seen,['finance']);
  assert.equal(locked.props.children[1].props.disabled,true);
});

test('SSR hook uses safe Basic before any account preference is loaded',()=>{
  function Probe(){
    const state=ui.useInterfaceModePreference({mode:'server',user:{}},null);
    return React.createElement('div',{'data-mode':state.mode,'data-ready':state.accountReady});
  }
  const html=renderToStaticMarkup(React.createElement(Probe));
  assert.match(html,/data-mode="basic"/);
  assert.match(html,/data-ready="false"/);
});
