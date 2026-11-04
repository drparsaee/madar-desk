const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
function load(entry){
 const bundled=esbuild.buildSync({entryPoints:[path.join(root,'src',entry)],bundle:true,
   platform:'node',format:'cjs',write:false,jsx:'automatic',
   external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
 const loader=new Module(path.join(root,entry+'.test.cjs'),module);
 loader.filename=path.join(root,entry+'.test.cjs');
 loader.paths=Module._nodeModulePaths(root);
 loader._compile(bundled,loader.filename);
 return loader.exports;
}
const {FILTER_LIMITS,validateFilterTree,matchFilterTree}=load('advanced_filter_engine.js');
const {matchAdvanced}=load('boardplus.jsx');
const card={id:'1',title:'چاپ برچسب',boardId:'b',listId:'active',status:'legacy',
 priority:'high',assignees:['nima'],labels:[{name:'فوری',color:'#567890'}],
 dueDate:'2026-11-02',attachments:[],fileLinks:[]};
const leaf=(field,value,comparison='is')=>({field,value,comparison});
const group=(op,...children)=>({op,children});

test('AND/OR trees evaluate independently and compose with legacy AND filters',()=>{
 const rules=group('and',leaf('priority','high'),group('or',
   leaf('member','sara'),leaf('label','فوری')));
 assert.equal(validateFilterTree(rules).valid,true);
 assert.equal(matchFilterTree(card,rules,'b'),true);
 assert.equal(matchFilterTree({...card,labels:[]},rules,'b'),false);
 assert.equal(matchFilterTree({...card,priority:'low'},rules,'b'),false);
 assert.equal(matchAdvanced(card,{priority:'low',due:'all',rules},'b'),false);
 assert.equal(matchAdvanced(card,{priority:'high',due:'all',rules},'b'),true);
});

test('nested groups and per-field comparisons cover title, attachments, status and due',()=>{
 const rules=group('or',group('and',
   leaf('title','برچسب','contains'),leaf('status','active'),leaf('attachments','no')),
   group('and',leaf('member','nima'),leaf('due','overdue')));
 assert(matchFilterTree(card,rules,'b','2026-11-03'));
 assert(!matchFilterTree({...card,title:'متفاوت',assignees:[],fileLinks:[{name:'x'}]},rules,'b','2026-11-03'));
 assert(matchFilterTree({...card,title:'متفاوت'},group('and',leaf('due','today','isNot'),
   leaf('title','آگهی','notContains')),'b','2026-11-03'));
 assert(matchFilterTree(card,group('and',leaf('attachments','yes','isNot'),leaf('status','active')),'b'));
 assert(!matchFilterTree(card,group('and',leaf('status','active')),'other'));
 assert(matchFilterTree(card,group('or',leaf('due','unset','isNot')),'b'));
});
test('nested overdue predicate agrees with explicit completion without moving the card',()=>{
 const filter=group('and',leaf('due','overdue'));
 const completed={...card,dueDate:'2020-01-01',completed:true,status:'legacy',listId:'active'};
 assert.equal(matchFilterTree(completed,filter,'b','2026-11-04'),false);
 assert.equal(matchFilterTree({...completed,completed:false},filter,'b','2026-11-04'),true);
 assert.equal(matchFilterTree({...completed,completed:false,status:'done'},filter,'b','2026-11-04'),true);
 assert.equal(matchFilterTree({...completed,completed:undefined,status:'done'},filter,'b','2026-11-04'),false);
 assert.equal(matchFilterTree(completed,group('and',leaf('due','overdue','isNot')),'b','2026-11-04'),true);
 assert.equal(completed.status,'legacy');
 assert.equal(completed.listId,'active');
});

test('empty root remains neutral, malformed rules fail closed, and removal of rules preserves legacy filters',()=>{
 assert(matchFilterTree(card,null,'b'));
 assert(matchFilterTree(card,group('and'),'b'));
 assert(matchAdvanced(card,{priority:'high',due:'all'},'b'));
 assert(!matchAdvanced(card,{priority:'high',due:'all',rules:{op:'or',children:[leaf('priority','high'),{oops:1}]}},'b'));
 assert(!matchAdvanced(card,{priority:'high',due:'tomorrow'},'b'));
 assert(!matchAdvanced(card,{due:'all',attachments:'false'},'b'));
 assert(matchFilterTree(card,group('or'),'b')); // empty root is neutral
 assert(!matchFilterTree(card,group('and',leaf('title','', 'contains')),'b'));
 assert.equal(validateFilterTree(group('and',leaf('title','','contains'))).valid,false);
 assert.equal(validateFilterTree(group('and',leaf('title','','contains')),{allowEmptyText:true}).valid,true);
});

test('depth, size, children, cyclic trees, unsupported fields and operators are rejected',()=>{
 const tooDeep=group('and',group('or',group('and',group('or',leaf('priority','high')))));
 assert.equal(validateFilterTree(tooDeep).valid,false);
 const tooMany=group('or',...Array.from({length:FILTER_LIMITS.children+1},()=>leaf('priority','high')));
 assert.equal(validateFilterTree(tooMany).valid,false);
 const width=group('and',...Array.from({length:8},()=>group('or',
   ...Array.from({length:4},()=>leaf('priority','high')))));
 assert.equal(validateFilterTree(width).valid,false);
 const cyclic=group('and');cyclic.children.push(cyclic);
 assert.equal(validateFilterTree(cyclic).valid,false);
 for(const rule of [leaf('role','admin'),leaf('priority','high','exec'),leaf('due','tomorrow'),
   leaf('attachments','truthy'),{...leaf('priority','high'),untrusted:true}]){
   assert.equal(validateFilterTree(group('and',rule)).valid,false);
   assert(!matchFilterTree(card,group('and',rule),'b'));
 }
});

test('filters never introduce a new task outside a pre-authorized candidate set',()=>{
 const restricted=[card];
 const privateCard={...card,id:'private',projectId:'forbidden',priority:'low'};
 const rules=group('or',leaf('priority','high'),leaf('priority','low'));
 const visible=restricted.filter(item=>matchAdvanced(item,{due:'all',rules},'b'));
 assert.deepEqual(visible.map(x=>x.id),['1']);
 assert(matchAdvanced(privateCard,{due:'all',rules},'b'),
   'this pure predicate does not implement authorization; the caller must scope candidates');
});
