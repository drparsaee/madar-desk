const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'..');
function load(name,externals=[]){
  const output=esbuild.buildSync({entryPoints:[path.join(root,'src',name)],
    bundle:true,format:'cjs',platform:'node',write:false,jsx:'automatic',
    loader:{'.css':'empty'},external:externals}).outputFiles[0].text;
  const mod=new Module(path.join(root,'__priorities_test__.cjs'),module);
  mod.filename=path.join(root,'__priorities_test__.cjs');
  mod.paths=Module._nodeModulePaths(root);
  mod._compile(output,mod.filename);
  return mod.exports;
}
const {DEFAULT_PRIORITIES,priorityDefs,priorityById,reorderStageArray,PRIORITY_EFFECTS}=load('priorities.js');
const {PrioritySettings}=load('priorities.jsx',['react','react/jsx-runtime','lucide-react']);
test('builtins have stable IDs and six distinct default motion choices',()=>{
  assert.deepEqual(priorityDefs({}).map(p=>p.id),['low','medium','high']);
  assert.deepEqual(PRIORITY_EFFECTS.map(x=>x[0]),['none','neon','shimmer','pulse','glow','solid']);
  assert.deepEqual(priorityDefs({priorityDefinitions:DEFAULT_PRIORITIES}),DEFAULT_PRIORITIES);
});
test('custom priority color/effect preserved; invalid external data ignored safely',()=>{
  const custom={id:'p-critical',label:'ویژه تیم',color:'#ff2255',effect:'neon'};
  const all=priorityDefs({priorityDefinitions:[...DEFAULT_PRIORITIES,custom]});
  assert.deepEqual(priorityById(all,'p-critical'),custom);
  assert.equal(priorityById(all,'missing').id,'medium');
  const bad=priorityDefs({priorityDefinitions:[custom,custom,{id:'untrusted;code',label:'X',color:'red',effect:'evil'}]});
  assert.equal(bad.filter(item=>item.id==='p-critical').length,1);
  assert.deepEqual(bad.slice(0,3).map(p=>p.id).sort(),['high','low','medium']);
});
test('legacy بحرانی label displays فوری without changing saved data or priority identity',()=>{
  const legacy={id:'p-critical',label:'بحرانی',color:'#ff2255',effect:'neon'};
  const custom={id:'p-special',label:'بسیار مهم',color:'#112233',effect:'solid'};
  const settings={priorityDefinitions:[...DEFAULT_PRIORITIES,legacy,custom]};
  const before=JSON.stringify(settings);
  const definitions=priorityDefs(settings);
  assert.deepEqual(definitions.map(p=>p.id),['low','medium','high','p-critical','p-special']);
  assert.deepEqual(priorityById(definitions,'p-critical'),{...legacy,label:'فوری'});
  assert.deepEqual(priorityById(definitions,'p-special'),custom);
  assert.equal(priorityById(definitions,'missing').id,'medium');
  assert.equal(JSON.stringify(settings),before,'reading the legacy label must not mutate persisted state');
  const html=renderToStaticMarkup(React.createElement(PrioritySettings,{
    settings,usedIds:['p-critical'],onChange:()=>{},canManage:false}));
  assert.match(html,/نام اولویت فوری/);
  assert.doesNotMatch(html,/بحرانی/);
  assert.match(html,/بسیار مهم/);
  assert.match(html,/disabled="" aria-label="حذف اولویت فوری"/,
    'read-only view must disable editing a custom priority');
  assert.doesNotMatch(html,/نام اولویت جدید/,'read-only view must hide creation');
});
test('legacy rename applies to edited builtins but leaves other custom overrides intact',()=>{
  const original=[
    {...DEFAULT_PRIORITIES[0],label:'کم‌اهمیت'},
    DEFAULT_PRIORITIES[1],
    {...DEFAULT_PRIORITIES[2],label:'  بحرانی  ',color:'#123456',effect:'pulse'},
    {id:'p-team',label:'بحرانی‌تر',color:'#abcdef',effect:'glow'}
  ];
  const definitions=priorityDefs({priorityDefinitions:original});
  assert.deepEqual(definitions.map(p=>p.label),['کم‌اهمیت','متوسط','فوری','بحرانی‌تر']);
  assert.deepEqual(definitions[2],{id:'high',label:'فوری',color:'#123456',effect:'pulse'});
  assert.deepEqual(definitions[3],original[3]);
  assert.equal(DEFAULT_PRIORITIES[2].label,'بالا','global defaults must remain unchanged');
  assert.equal(original[2].label,'  بحرانی  ','persisted custom definition must not be mutated');
});
test('reordering stages does not mutate input or change stage identities and colors',()=>{
  const stages=[{id:'a',color:'#112233'},{id:'b',color:'#998877'},{id:'c',color:'#aabbcc'}];
  const result=reorderStageArray(stages,'a','c');
  assert.deepEqual(result.map(s=>s.id),['b','c','a']);
  assert.equal(result[2],stages[0]);
  assert.deepEqual(stages.map(s=>s.id),['a','b','c']);
  assert.equal(reorderStageArray(stages,'bad','a'),stages);
});
test('priority settings renderer exposes editable colors and animation presets',()=>{
  const html=renderToStaticMarkup(React.createElement(PrioritySettings,{
    settings:{priorityDefinitions:[...DEFAULT_PRIORITIES,{id:'p-special',label:'فوری',color:'#ee1199',effect:'neon'}]},
    usedIds:[],onChange:()=>{},canManage:true}));
  assert.match(html,/تعریف و شخصی‌سازی اولویت‌ها/);
  assert.equal((html.match(/type="color"/g)||[]).length,4);
  assert.match(html,/نئون متحرک/);
  assert.match(html,/priority-effect-neon/);
  assert.match(html,/حذف اولویت فوری/);
  assert.match(html,/نام اولویت جدید، مثلاً فوری/);
  assert.doesNotMatch(html,/بحرانی/);
});
