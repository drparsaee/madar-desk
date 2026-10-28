'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const source=path.join(root,'src/automation_buttons.jsx');
const compiled=esbuild.buildSync({entryPoints:[source],bundle:true,platform:'node',format:'cjs',write:false,
  loader:{'.css':'empty'},external:['react','react-dom','lucide-react']}).outputFiles[0].text;

function load(react=React){
  const instance=new Module(source,module);
  instance.filename=source;
  instance.paths=Module._nodeModulePaths(path.dirname(source));
  instance.require=id=>id==='react'?react:Module.prototype.require.call(instance,id);
  instance._compile(compiled,source);
  return instance.exports;
}

function mount(componentName,props){
  const slots=[];
  const effects=[];
  let cursor=0;
  const eq=(a,b)=>a&&b&&a.length===b.length&&a.every((value,i)=>Object.is(value,b[i]));
  const react={
    ...React,
    useState(initial){
      const i=cursor++;
      if(!slots[i])slots[i]={value:typeof initial==='function'?initial():initial};
      return [slots[i].value,value=>{slots[i].value=typeof value==='function'?value(slots[i].value):value;}];
    },
    useRef(initial){
      const i=cursor++;
      if(!slots[i])slots[i]={value:{current:initial}};
      return slots[i].value;
    },
    useCallback(fn,deps){
      const i=cursor++;
      if(!slots[i]||!eq(slots[i].deps,deps))slots[i]={value:fn,deps};
      return slots[i].value;
    },
    useEffect(fn,deps){
      const i=cursor++;
      if(!slots[i]||!eq(slots[i].deps,deps)){
        slots[i]={deps};effects.push(fn);
      }
    },
  };
  const module=load(react);
  const render=()=>{cursor=0;return module[componentName](props);};
  const flush=async()=>{
    const queued=effects.splice(0);
    for(const fn of queued)fn();
    await Promise.resolve();await Promise.resolve();await new Promise(resolve=>setImmediate(resolve));
  };
  return {render,flush,module};
}

function nodes(node,found=[]){
  if(Array.isArray(node)){node.forEach(item=>nodes(item,found));return found;}
  if(node==null||typeof node!=='object'||!node.props)return found;
  if(typeof node.type==='function'){
    // ActionEditor has no hooks and can be expanded for interaction assertions.
    return nodes(node.type(node.props),found);
  }
  found.push(node);
  nodes(node.props.children,found);
  return found;
}
function words(node){
  if(node==null||typeof node==='boolean')return '';
  if(Array.isArray(node))return node.map(words).join(' ');
  if(typeof node==='string'||typeof node==='number')return String(node);
  if(typeof node.type==='function')return words(node.type(node.props));
  return node.props?words(node.props.children):'';
}
function button(tree,search){
  const item=nodes(tree).find(node=>node.type==='button'&&(
    (node.props['aria-label']||'')===search||words(node).includes(search)));
  assert.ok(item,'Button missing: '+search);
  return item;
}
function click(tree,search){
  const item=button(tree,search);
  assert.notEqual(item.props.disabled,true,'Disabled button: '+search);
  return item.props.onClick();
}
const account={username:'bob',displayName:'بابک'};
const base={projectId:'p1',boardId:'b1',users:[account]};
const draft={scope:'card',title:' گزارش  ',icon:'star',enabled:true,closeAfterAction:true,
  actions:[{type:'notify',users:['bob'],message:' ثبت شد '},{type:'comment',text:' انجام شد '}]};

test('payload maps to backend contract and strips untrusted input without inventing actions',()=>{
  const {validateAutomationButton}=load();
  assert.deepEqual(validateAutomationButton(draft,base),{
    projectId:'p1',boardId:'b1',scope:'card',title:'گزارش',icon:'star',enabled:true,closeAfterAction:true,
    actions:[{type:'notify',users:['bob'],message:'ثبت شد'},{type:'comment',text:'انجام شد'}],
  });
  const board=validateAutomationButton({...draft,id:'b-12',scope:'board',enabled:false},base);
  assert.equal(board.closeAfterAction,false);
  assert.equal(board.enabled,false);
  assert.equal(board.id,'b-12');
});

test('validation rejects unsupported actions, invalid member and overlong fields',()=>{
  const {validateAutomationButton:validate}=load();
  for(const invalid of [
    {...draft,title:' '},{...draft,icon:'arbitrary'},{...draft,actions:[]},
    {...draft,actions:[{type:'move',listId:'l2'}]},
    {...draft,actions:[{type:'notify',users:['ghost'],message:'hello'}]},
    {...draft,actions:[{type:'comment',text:'   '}]},
    {...draft,actions:[{type:'comment',text:'a'.repeat(4001)}]},
    {...draft,actions:Array.from({length:6},()=>({type:'comment',text:'ok'}))},
  ])assert.throws(()=>validate(invalid,base));
  assert.throws(()=>validate(draft,{...base,boardId:''}),/برد/);
});

test('SSR panel has semantic modal and missing host visibly blocks fake operations',()=>{
  const {AutomationButtonsPanel,AutomationButtonsLauncher,AutomationButtonStrip}=load();
  const html=renderToStaticMarkup(React.createElement(AutomationButtonsPanel,{
    api:{},project:{id:'p1',name:'آزمایشی'},boardId:'b1',onClose:()=>{},users:[account],
  }));
  assert.match(html,/role="dialog" aria-modal="true"/);
  assert.match(html,/dir="rtl"/);
  assert.match(html,/دکمه‌های کارت/);
  assert.match(html,/دکمه‌های برد/);
  assert.match(html,/میزبان این قابلیت را ارائه نمی‌کند/);
  assert.match(html,/disabled=""/);
  assert.match(renderToStaticMarkup(React.createElement(AutomationButtonsLauncher,{onClick:()=>{}})),/دکمه‌های کارت/);
  assert.match(renderToStaticMarkup(React.createElement(AutomationButtonStrip,{api:{},projectId:'p1',boardId:'b1'})),/role="group"/);
  const css=fs.readFileSync(path.join(root,'src/automation_buttons.css'),'utf8');
  assert.match(css,/:root\[data-theme="dark"\] \.ab-panel/);
  assert.match(css,/@media\(max-width:650px\)/);
  assert.match(css, /:focus-visible/);
});

test('full UI flow: add action, icon picker, toggle close, save and reload verified backend data',async()=>{
  let stored=[];
  const saves=[];
  const api={
    automationButtonsList:async()=>stored,
    automationButtonsSave:async def=>{
      saves.push(def);
      const saved={...def,id:'btn-1'};
      stored=[saved];return saved;
    },
    automationButtonsDelete:async()=>({buttonId:'btn-1'}),
    automationButtonRun:async request=>({...request,ok:true}),
  };
  const harness=mount('AutomationButtonsPanel',{...base,api,scope:'card',onClose:()=>{}});
  let tree=harness.render();await harness.flush();
  tree=harness.render();
  click(tree,'ساخت دکمه');
  tree=harness.render();
  assert.match(words(tree),/پس از اجرای موفق، کارت بسته شود/);
  const title=nodes(tree).find(node=>node.type==='input'&&node.props.type==='text');
  assert.ok(title);title.props.onChange({target:{value:'خودکار'}});
  click(harness.render(),'انتخاب نماد دکمه');
  tree=harness.render();click(tree,'نماد پرچم');
  tree=harness.render();assert.equal(nodes(tree).find(node=>node.props['aria-label']==='انتخاب نماد دکمه').props['aria-expanded'],false);
  click(tree,'افزودن عمل');
  click(harness.render(),'ثبت نظر');
  tree=harness.render();
  const textarea=nodes(tree).find(node=>node.type==='textarea');
  assert.ok(textarea);textarea.props.onChange({target:{value:'تکمیل شد'}});
  const checkbox=nodes(tree).filter(node=>node.type==='input'&&node.props.type==='checkbox');
  assert.equal(checkbox.length,2);
  checkbox[1].props.onChange({target:{checked:true}});
  const form=nodes(harness.render()).find(node=>node.type==='form');
  await form.props.onSubmit({preventDefault(){}});
  assert.equal(saves.length,1);
  assert.equal(saves[0].icon,'flag');
  assert.equal(saves[0].title,'خودکار');
  assert.equal(saves[0].closeAfterAction,true);
  assert.deepEqual(saves[0].actions,[{type:'comment',text:'تکمیل شد'}]);
  tree=harness.render();
  assert.match(words(tree),/دکمه در برد ذخیره شد/);
  assert.match(words(tree),/خودکار/);
});

test('save errors remain visible and do not close editor or claim success',async()=>{
  const api={automationButtonsList:async()=>[],automationButtonsSave:async()=>{throw Error('permission denied');}};
  const harness=mount('AutomationButtonsPanel',{...base,api});
  harness.render();await harness.flush();
  click(harness.render(),'ساخت دکمه');
  let tree=harness.render();
  nodes(tree).find(node=>node.type==='input'&&node.props.type==='text').props.onChange({target:{value:'خطادار'}});
  click(harness.render(),'افزودن عمل');click(harness.render(),'ثبت نظر');
  nodes(harness.render()).find(node=>node.type==='textarea').props.onChange({target:{value:'تست'}});
  await nodes(harness.render()).find(node=>node.type==='form').props.onSubmit({preventDefault(){}});
  tree=harness.render();
  assert.match(words(tree),/permission denied/);
  assert.ok(nodes(tree).find(node=>node.type==='form'));
  assert.doesNotMatch(words(tree),/دکمه در برد ذخیره شد/);
});

test('board run needs explicit chosen card and never performs implicit fanout',async()=>{
  let requested=[];
  const api={
    automationButtonsList:async()=>[{...draft,id:'btn-2',title:'گزارش',scope:'board',closeAfterAction:false}],
    automationButtonRun:async params=>{requested.push(params);return {...params,ok:true};},
  };
  const harness=mount('AutomationButtonsPanel',{...base,api,scope:'board',cardOptions:[{id:'c1',title:'کارت یک'}]});
  harness.render();await harness.flush();
  let tree=harness.render();
  assert.equal(button(tree,'اجرای گزارش').props.disabled,true);
  const destination=nodes(tree).find(node=>node.type==='select'&&node.props['aria-label']==='کارت مقصد اجرای دکمه');
  assert.ok(destination);
  destination.props.onChange({target:{value:'c1'}});
  await click(harness.render(),'اجرای گزارش');
  assert.deepEqual(requested,[{buttonId:'btn-2',cardId:'c1'}]);
});

test('strip executes only enabled buttons with a cardId, closes card only on successful card action',async()=>{
  const actions=[];let closed=0;let ran=0;
  const api={
    automationButtonsList:async()=>[
      {...draft,id:'btn-1',title:'آگاه‌سازی'},
      {...draft,id:'btn-2',title:'غیرفعال',enabled:false},
    ],
    automationButtonRun:async input=>{actions.push(input);return {...input,ok:true};},
  };
  const harness=mount('AutomationButtonStrip',{api,projectId:'p1',boardId:'b1',scope:'card',cardId:'c99',onRan:()=>ran++,onCloseCard:()=>closed++});
  harness.render();await harness.flush();
  let tree=harness.render();
  assert.match(words(tree),/آگاه‌سازی/);
  assert.doesNotMatch(words(tree),/غیرفعال/);
  await click(tree,'آگاه‌سازی');
  assert.deepEqual(actions,[{buttonId:'btn-1',cardId:'c99'}]);
  assert.equal(closed,1);assert.equal(ran,1);
  tree=harness.render();assert.match(words(tree),/اجرا شد/);

  const blocked=mount('AutomationButtonStrip',{api,projectId:'p1',boardId:'b1',scope:'card'});
  blocked.render();await blocked.flush();
  const blockedTree=blocked.render();
  assert.equal(button(blockedTree,'آگاه‌سازی').props.disabled,true);
  assert.match(words(blockedTree),/کارت مقصد انتخاب شود/);
});
