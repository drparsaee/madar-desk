const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
function load(entry, external = []) {
  const content = esbuild.buildSync({
    entryPoints: [path.join(root, entry)], bundle: true, platform: 'node',
    format: 'cjs', write: false, jsx: 'automatic',
    loader: {'.css': 'empty'}, external
  }).outputFiles[0].text;
  const loader = new Module(path.join(root, '__task_search_test__.cjs'), module);
  loader.filename = path.join(root, '__task_search_test__.cjs');
  loader.paths = Module._nodeModulePaths(root);
  loader._compile(content, loader.filename);
  return loader.exports;
}
const {searchTaskLocations, sortTaskSearchResults} = load('src/task_search_results.js');
const {SearchResultsPanel} = load('src/task_search_results.jsx',
  ['react', 'react/jsx-runtime', 'lucide-react']);

const sample = () => ({
  projects: [
    {id: 'p1', name: 'بسته‌بندی'},
    {id: 'p2', name: 'وب‌سایت'},
    {id: 'secret', name: 'محرمانه'}
  ],
  workspaces: [
    {id: 'w1', name: 'شرکت'},
    {id: 'w2', name: 'بخش دوم'},
    {id: 'w3', name: 'فضای بایگانی', archived: true}
  ],
  boards: [
    {id: 'b1', projectId: 'p1', workspaceId: 'w1', name: 'سفارشات',
      stages: [{id: 'todo', label: 'شروع'}, {id: 'done', label: 'تحویل'}]},
    {id: 'b2', projectId: 'p2', workspaceId: 'w2', name: 'سایت',
      stages: [{id: 'todo', label: 'برنامه‌ریزی'}]},
    {id: 'ba', projectId: 'p1', workspaceId: 'w1', name: 'برد قدیمی', archived: true,
      stages: [{id: 'todo', label: 'انجام‌نشده'}]},
    {id: 'bl', projectId: 'p1', workspaceId: 'w1', name: 'برد فهرست',
      stages: [{id: 'old', label: 'فهرست قدیم', archived: true}]},
    {id: 'bw', projectId: 'p1', workspaceId: 'w3', name: 'برد فضای بسته',
      stages: [{id: 'todo', label: 'آماده'}]},
    {id: 'bs', projectId: 'secret', workspaceId: 'w2', name: 'برد محرمانه',
      stages: [{id: 'todo', label: 'حساس'}]}
  ],
  stages: [{id: 'inbox', label: 'صندوق ورودی'}],
  tasks: [
    {id:'active1', projectId:'p1', boardId:'b1', listId:'todo',
      title:'طراحی جعبه‌ی فارسی', labels:[{name:'فوری', color:'#ff0000'}],
      updatedAt:'2026-10-12T10:00:00Z', cardOrder:4, cost:123456},
    {id:'active2', projectId:'p1', boardId:'b1', listId:'todo',
      title:'طراحی لیبل', labels:['چاپ'], createdAt:'2026-10-14',
      cardOrder:1},
    {id:'archived', projectId:'p1', boardId:'b1', listId:'done',
      title:'طراحی آرشیو', labels:['فوری'], archived:true,
      updatedAt:'2026-11-01'},
    {id:'trash', projectId:'p1', boardId:'b1', listId:'todo',
      title:'طراحی حذف شده', deleted:true, createdAt:'2026-10-30',
      fileLinks:[{url:'private'}]},
    {id:'boardArchive', projectId:'p1', boardId:'ba', listId:'todo',
      title:'طراحی برد قدیمی', archived:true, archivedByBoard:true,
      updatedAt:'2026-09-01'},
    {id:'listArchive', projectId:'p1', boardId:'bl', listId:'old',
      title:'طراحی فهرست بسته', updatedAt:'2026-10-22'},
    {id:'workspaceArchive', projectId:'p1', boardId:'bw', listId:'todo',
      title:'طراحی فضای بسته', updatedAt:'2026-10-25'},
    {id:'otherProject', projectId:'p2', boardId:'b2', listId:'todo',
      title:'طراحی سایت', updatedAt:'2026-10-20'},
    {id:'private', projectId:'secret', boardId:'bs', listId:'todo',
      title:'طراحی مخفی', labels:['محرمانه'], updatedAt:'2026-11-02', cost:987654321},
    {id:'orphan', projectId:'p1', boardId:'absent', listId:'todo',
      title:'طراحی گم شده'},
    {id:'crossProject', projectId:'p1', boardId:'bs', listId:'todo',
      title:'طراحی ناسازگار'}
  ]
});
const run = (state, query='طراحي', options={}) =>
  searchTaskLocations(state,{query,permittedProjectIds:['p1'],...options});

test('active, individual archive, board/list/workspace archive and trash are distinct', () => {
  const results = run(sample());
  const types = Object.fromEntries(results.map(item =>
    [item.id, [item.status, item.archiveScope]]));
  assert.deepEqual(types.active1, ['active', null]);
  assert.deepEqual(types.active2, ['active', null]);
  assert.deepEqual(types.archived, ['archived', 'card']);
  assert.deepEqual(types.boardArchive, ['archived', 'board']);
  assert.deepEqual(types.listArchive, ['archived', 'list']);
  assert.deepEqual(types.workspaceArchive, ['archived', 'workspace']);
  assert.deepEqual(types.trash, ['trash', null]);
  assert(!types.private && !types.orphan && !types.crossProject && !types.otherProject);
});

test('location identifies the exact board/list/project; repeated list ids use local label', () => {
  const results = run(sample(), 'title:طراحي', {permittedProjectIds:['p1','p2']});
  assert.equal(results.find(item=>item.id==='active1').listName, 'شروع');
  assert.equal(results.find(item=>item.id==='otherProject').listName, 'برنامه‌ریزی');
  assert.equal(results.find(item=>item.id==='listArchive').boardName, 'برد فهرست');
  assert.equal(results.find(item=>item.id==='workspaceArchive').workspaceName, 'فضای بایگانی');
  assert.deepEqual(run(sample(), 'status:برنامه‌ریزی').map(item=>item.id), []);
  assert.deepEqual(run(sample(), 'status:شروع').map(item=>item.id),
    ['trash', 'active2', 'active1']);
  assert.deepEqual(run(sample(), 'status:برنامه‌ریزی', {permittedProjectIds:['p2']})
    .map(item=>item.id), ['otherProject']);
});

test('project grants are mandatory, cannot be widened by foreign IDs or task metadata', () => {
  const state = sample();
  assert.throws(() => searchTaskLocations(state,{query:'طراحی'}), /permittedProjectIds/);
  assert.deepEqual(searchTaskLocations(state,{query:'طراحی',permittedProjectIds:[]}), []);
  assert.deepEqual(run(state,'مخفی'), []);
  assert.deepEqual(run(state,'project:محرمانه'), []);
  assert.deepEqual(run(state,'987654321'), []);
  assert.deepEqual(run(state,'title:طراحی',{projectId:'secret'}), []);
  assert.deepEqual(run(state,'title:طراحی',{workspaceId:'w2'}), []);
  assert.deepEqual(run(state,'title:طراحی',{workspaceId:'w3'}).map(x=>x.id), ['workspaceArchive']);
});

test('search accepts partial Persian title, Arabic variants, labels and complex qualifiers', () => {
  const state = sample();
  assert.deepEqual(run(state,'عنوان:جعبه').map(x=>x.id), ['active1']);
  assert.deepEqual(run(state,'label:فوری').map(x=>x.id), ['archived','active1']);
  assert.deepEqual(run(state,'title:"طراحی حذف"').map(x=>x.id), ['trash']);
  assert.deepEqual(run(state,'طراحي -عنوان:آرشیو').some(x=>x.id==='archived'), false);
  assert.deepEqual(run(state,'title:nomatch'), []);
  assert.deepEqual(run(state,'   '), []);
});

test('date sorting (recent first) and card order sorting preserve stable list ranking', () => {
  const state = sample();
  const dated = run(state).map(x=>x.id);
  assert.deepEqual(dated.slice(0,4), ['archived','trash','workspaceArchive','listArchive']);
  const ordered = run(state,'title:طراحی',{sortBy:'cardOrder'});
  assert(ordered.findIndex(x=>x.id==='active2') < ordered.findIndex(x=>x.id==='active1'));
  const reversed = sortTaskSearchResults(ordered,'date').map(x=>x.id);
  assert.deepEqual(reversed, dated);
  assert.throws(()=>run(state,'title:طراحی',{sortBy:'unsupported'}), /sortBy/);
});

test('results are display-only and do not mutate source, finances or attachments', () => {
  const state = sample();
  const before = JSON.stringify(state);
  const result = run(state,'عنوان:جعبه')[0];
  assert.equal(result.labels[0].name,'فوری');
  assert.equal(result.labels[0].color,'#ff0000');
  for (const hidden of ['cost','profit','fileLinks','task','price']) {
    assert.equal(Object.hasOwn(result,hidden),false);
  }
  result.labels[0].name = 'تغییر آزمایشی';
  assert.equal(state.tasks[0].labels[0].name,'فوری');
  assert.equal(JSON.stringify(state),before);
});

test('legacy boardless cards remain discoverable only when state contains no boards', () => {
  const state = {projects:[{id:'p1',name:'قدیمی'}], boards:[],workspaces:[],
    stages:[{id:'inbox',label:'ورودی'}],
    tasks:[{id:'legacy',projectId:'p1',status:'inbox',title:'کارت قدیمی',archived:true}]};
  const result=run(state,'کارت');
  assert.equal(result.length,1);
  assert.equal(result[0].listName,'ورودی');
  assert.equal(result[0].boardId,null);
  assert.equal(result[0].status,'archived');
});

test('malformed flags and duplicate accessible identities reject without exposing partial matches', () => {
  const state = sample();
  state.tasks[0].deleted = 'false';
  assert.throws(()=>run(state),/task.deleted/);
  delete state.tasks[0].deleted;
  state.boards[0].stages[0].archived = 'yes';
  assert.throws(()=>run(state),/archived flag/);
  delete state.boards[0].stages[0].archived;
  state.tasks[0].cardOrder = -1;
  assert.throws(()=>run(state),/Invalid cardOrder/);
  state.tasks[0].cardOrder = 4;
  state.tasks.push({...state.tasks[0],title:'duplicate'});
  assert.throws(()=>run(state),/Duplicate authorized task id/);
});

test('dedicated RTL panel shows scoped locations, labels, status tabs and permitted actions', () => {
  const results = run(sample());
  const html = renderToStaticMarkup(React.createElement(SearchResultsPanel,{
    query:'طراحی',results, onQueryChange:()=>{}, onOpenTask:()=>{},
    onRestoreArchived:()=>{},onRestoreTrashed:()=>{},onGoToLocation:()=>{},
    onClose:()=>{},canEdit:true
  }));
  assert.match(html,/dir="rtl"/);
  assert.match(html,/جست‌وجوی همه کارت‌ها/);
  assert.match(html,/زباله‌دان/);
  assert.match(html,/برد قدیمی/);
  assert.match(html,/فهرست قدیم/);
  assert.match(html,/مرتب‌سازی نتایج/);
  assert.match(html,/بازیابی کارت/);
  assert.match(html,/فوری/);
  assert.doesNotMatch(html,/123456|987654321|private/);
  const readOnly = renderToStaticMarkup(React.createElement(SearchResultsPanel,{
    query:'طراحی', results, canEdit:false
  }));
  assert.doesNotMatch(readOnly, /بازیابی کارت/);
});
