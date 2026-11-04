const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path'),Module=require('node:module'),esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const result=esbuild.buildSync({entryPoints:[path.join(root,'src/boardplus.jsx')],
 bundle:true,platform:'node',format:'cjs',write:false,jsx:'automatic',
 external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const loader=new Module(path.join(root,'src','boardplus-test.cjs'),module);
loader.filename=path.join(root,'src','boardplus-test.cjs');
loader.paths=Module._nodeModulePaths(root);
loader._compile(result,loader.filename);
const {labelColor,labelText,matchAdvanced,savedFilterStorageKey}=loader.exports;
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const markdownBundle=esbuild.buildSync({entryPoints:[path.join(root,'src/markdown.jsx')],
 bundle:true,platform:'node',format:'cjs',write:false,jsx:'automatic',
 external:['react','react/jsx-runtime']}).outputFiles[0].text;
const markdownLoader=new Module(path.join(root,'src','markdown-test.cjs'),module);
markdownLoader.filename=path.join(root,'src','markdown-test.cjs');
markdownLoader.paths=Module._nodeModulePaths(root);
markdownLoader._compile(markdownBundle,markdownLoader.filename);
const {safeMarkdownUrl,MarkdownPreview}=markdownLoader.exports;
const featuresBundle=esbuild.buildSync({entryPoints:[path.join(root,'src/features.jsx')],
 bundle:true,platform:'node',format:'cjs',write:false,jsx:'automatic',
 loader:{'.css':'empty'},
 external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const featuresLoader=new Module(path.join(root,'src','features-test.cjs'),module);
featuresLoader.filename=path.join(root,'src','features-test.cjs');
featuresLoader.paths=Module._nodeModulePaths(root);
featuresLoader._compile(featuresBundle,featuresLoader.filename);
const {LanPanel,validLanFingerprint,normalizeLanFingerprint}=featuresLoader.exports;
const base={title:'قالب',priority:'high',status:'doing',labels:['ضروری','مشتری'],
 assignees:['designer'],dueDate:'',fileLinks:[]};
test('label color stable for text and explicit color for defined label',()=>{
 assert.equal(labelColor('ضروری'),labelColor('ضروری'));
 assert.equal(labelColor({name:'مشتری',color:'#123456'}),'#123456');
 assert.equal(labelText({name:'مشتری',color:'#123456'}),'مشتری');
});
test('filters member, priority, label, status independently and together',()=>{
 assert(matchAdvanced(base,{priority:'high',member:'designer',label:'ضروری',status:'doing',
   due:'all',attachments:false}));
 assert(!matchAdvanced(base,{priority:'low',member:'designer',label:'ضروری',status:'doing',
   due:'all',attachments:false}));
 assert(!matchAdvanced(base,{priority:'high',member:'other',label:'ضروری',status:'doing',
   due:'all',attachments:false}));
 assert(!matchAdvanced(base,{priority:'high',member:'designer',label:'missing',status:'doing',
   due:'all',attachments:false}));
});
test('board stage filter reads board listId instead of fallback legacy status',()=>{
 const card={...base,boardId:'board-a',listId:'board-only',status:'inbox'};
 const filter={priority:'all',member:'all',label:'all',status:'board-only',due:'all',attachments:false};
 assert(matchAdvanced(card,filter,'board-a'));
 assert(!matchAdvanced(card,filter,'board-b'));
});
test('attachment and due-date filters do not invent files or dates',()=>{
 const f={priority:'all',member:'all',label:'all',status:'all',due:'unset',attachments:false};
 assert(matchAdvanced(base,f));
 assert(!matchAdvanced(base,{...f,attachments:true}));
 assert(matchAdvanced({...base,fileLinks:[{name:'sample',path:'\\\\host\\share\\x'}]},
   {...f,attachments:true}));
 assert(!matchAdvanced({...base,dueDate:'2027-01-01'},f));
});
test('completed cards are not overdue even when still in the original board lane',()=>{
 const late={...base,dueDate:'2020-01-01',completed:true,status:'doing',listId:'in-progress'};
 const due={priority:'all',member:'all',label:'all',status:'all',due:'overdue',attachments:false};
 assert.equal(matchAdvanced(late,due),false,
   'marking card completed must not require a stage move or financial posting');
 assert.equal(matchAdvanced({...late,completed:false},due),true);
 assert.equal(matchAdvanced({...late,completed:false,status:'done'},due),true);
 assert.equal(matchAdvanced({...late,completed:undefined,status:'done'},due),false);
 assert.equal(late.status,'doing');
 assert.equal(late.listId,'in-progress');
});
test('saved-filter keys preserve complete user identities and refuse ambiguous scopes',()=>{
 const shared='https://same-host.test/'+('x'.repeat(240));
 const alice=savedFilterStorageKey(shared+'alice','board-1');
 const bob=savedFilterStorageKey(shared+'bob','board-1');
 assert.notEqual(alice,bob,'Long host prefixes must not merge users');
 assert.notEqual(alice,savedFilterStorageKey(shared+'alice','board-2'));
 assert.equal(savedFilterStorageKey(null,'board-1'),'');
 assert.equal(savedFilterStorageKey('user',''),'');
 assert.equal(savedFilterStorageKey('u'.repeat(1025),'board-1'),'');
});
test('Markdown preview renders headings, lists, emphasis, links, and fenced code',()=>{
 const html=renderToStaticMarkup(React.createElement(MarkdownPreview,{value:'# عنوان\n\n**پررنگ** و *مورب*\n\n- الف\n- ب\n\n[رفتن](https://example.com)\n\n```js\nconst x=1;\n```'}));
 assert.match(html,/<h3>عنوان<\/h3>/);
 assert.match(html,/<strong>پررنگ<\/strong>/);
 assert.match(html,/<em>مورب<\/em>/);
 assert.match(html,/<ul><li>الف<\/li><li>ب<\/li><\/ul>/);
 assert.match(html,/href="https:\/\/example.com"/);
 assert.match(html,/<pre><code data-language="js">const x=1;<\/code><\/pre>/);
});
test('Markdown preview safely escapes HTML and refuses unsafe links',()=>{
 const html=renderToStaticMarkup(React.createElement(MarkdownPreview,{value:'<img src=x onerror=alert(1)>\n\n[click](javascript:alert)\n\n[ok](mailto:test@example.com)'}));
 assert(!html.includes('<img'));
 assert(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
 assert(!html.includes('href="javascript:'));
 assert(html.includes('[click](javascript:alert)'));
 assert.match(html,/href="mailto:test@example.com"/);
 assert.equal(safeMarkdownUrl('data:text/html,test'),null);
 assert.equal(safeMarkdownUrl('https://example.com\njavascript:evil'),null);
 assert.equal(safeMarkdownUrl('//example.com'),null);
});
test('LAN HTTPS fingerprint input requires a full SHA-256 certificate pin',()=>{
 const hex='ab'.repeat(32);
 assert.equal(validLanFingerprint(hex),true);
 assert.equal(validLanFingerprint(Array(32).fill('ab').join(':')),true);
 assert.equal(normalizeLanFingerprint(Array(32).fill('ab').join(':')),hex);
 assert.equal(validLanFingerprint(hex.slice(0,-1)),false);
 assert.equal(validLanFingerprint(''),false);
 assert.equal(validLanFingerprint('sha256/'+hex),false);
 const solo=renderToStaticMarkup(React.createElement(LanPanel,{
   api:{},projects:[],status:{mode:'solo'},onClose:()=>{},onRefresh:()=>{},onConnected:()=>{}}));
 assert(solo.includes('HTTPS برای میزبانی روی شبکه الزامی است.'));
 assert(solo.includes('راه‌اندازی میزبان HTTPS'));
 assert(!solo.includes('راه‌اندازی میزبان HTTP قدیمی'));
 const host=renderToStaticMarkup(React.createElement(LanPanel,{
   api:{},projects:[],status:{mode:'server',port:48370,transport:'https',fingerprint:hex,user:{role:'admin'}},
   onClose:()=>{},onRefresh:()=>{},onConnected:()=>{}}));
 assert(host.includes(hex));
 assert(host.includes('اتصال HTTPS'));
});
