'use strict';

/**
 * E6 opt-in unmounted inbox UI: genuine bundled JSX + React SSR and real
 * component event handlers with a tiny deterministic React hook harness.
 * No HTTP, browser, host/service, real profile, filesystem write or provider.
 */
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const React=require('react');
const esbuild=require('esbuild');
const {renderToStaticMarkup}=require('react-dom/server');

const src=path.resolve(__dirname,'..','src','mtr_internal_notice_panel.jsx');
const bundled=esbuild.buildSync({
  entryPoints:[src],bundle:true,platform:'node',format:'cjs',
  write:false,external:['react','react/jsx-runtime'],
}).outputFiles[0].text;

function compiledExports(react=React){
  const wrapped=new Module(src,module);
  wrapped.filename=src;
  wrapped.paths=Module._nodeModulePaths(path.dirname(src));
  wrapped.require=id=>id==='react'?react:Module.prototype.require.call(wrapped,id);
  wrapped._compile(bundled,src);
  return wrapped.exports;
}
const panel=compiledExports();
const project='proj-1';
const makeNote=(id,overrides={})=>({
  notice_id:id,organization_id:'org-internal-hidden',project_id:project,
  channel:'internal_only',recipient_id:'recipient-hidden',
  original_request_id:'finance-secret-raw-701',
  event_key:'event-key-raw-internal',event_kind:'request_status_changed',
  stored_at:'2026-11-10T00:00:00Z',
  read_at:null,is_read:false,status:'AWAITING_RECEIPT',
  actor_id:'actor-hidden',amendment_id:'amendment-secret-raw',
  deficiency_summary:'private-financial-summary',
  receipt_reference:'sensitive-receipt-123',finance_doc:'secret-finance-raw',
  ...overrides,
});
const listed=rows=>({schemaVersion:1,result:rows});
const ack=(id,already=false)=>({
  schemaVersion:1,
  result:{notice_id:id,marked_read:!already,already_read:already},
});
const deferred=()=>{
  let resolve,reject;
  const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});
  return {promise,resolve,reject};
};
const flush=()=>new Promise(resolve=>setImmediate(resolve));

function mount(props={}){
  const hooks=[];
  let cursor=0;
  const fake={
    ...React,
    useId(){
      const n=cursor++;
      if(!hooks[n])hooks[n]={value:'e6-heading-'+n};
      return hooks[n].value;
    },
    useState(initial){
      const n=cursor++;
      if(!hooks[n])hooks[n]={value:typeof initial==='function'?initial():initial};
      return [hooks[n].value,update=>{
        hooks[n].value=typeof update==='function'?update(hooks[n].value):update;
      }];
    },
    useRef(initial){
      const n=cursor++;
      if(!hooks[n])hooks[n]={value:{current:initial}};
      return hooks[n].value;
    },
  };
  const {MtrInternalNoticePanel}=compiledExports(fake);
  let current={
    projectId:project,command:async()=>{throw Error('Unexpected host call');},
    ...props,
  };
  return {
    render(){cursor=0;return MtrInternalNoticePanel(current);},
    setProps(next){current={...current,...next};},
  };
}

function nodes(node,acc=[]){
  if(node==null||typeof node==='boolean')return acc;
  if(Array.isArray(node)){node.forEach(part=>nodes(part,acc));return acc;}
  if(typeof node!=='object'||!node.props)return acc;
  if(typeof node.type==='function')return nodes(node.type(node.props),acc);
  acc.push(node);
  nodes(node.props.children,acc);
  return acc;
}
function textOf(node){
  if(node===null||node===undefined||typeof node==='boolean')return '';
  if(Array.isArray(node))return node.map(textOf).join(' ');
  if(typeof node==='string'||typeof node==='number')return String(node);
  if(typeof node.type==='function')return textOf(node.type(node.props));
  return node.props?textOf(node.props.children):'';
}
function button(tree,label){
  const found=nodes(tree).find(node=>node.type==='button'
    &&textOf(node).includes(label));
  assert.ok(found,'button missing: '+label);
  return found;
}
function articles(tree){return nodes(tree).filter(node=>node.type==='article');}

test('SSR renders accessible RTL opt-in panel with no command invocation on mount',()=>{
  let calls=0;
  const html=renderToStaticMarkup(React.createElement(
    panel.MtrInternalNoticePanel,{projectId:project,
      command:async()=>{calls++;return listed([]);}},
  ));
  assert.equal(calls,0);
  assert.match(html,/dir="rtl"/);
  assert.match(html,/aria-labelledby="[^"]+"/);
  assert.match(html,/دریافت اعلان‌ها/);
  assert.match(html,/دستی/);
  assert.doesNotMatch(html,/email|SMS|receipt_reference|finance_doc/i);
  const instance=mount({command:async()=>{calls++;return listed([]);}});
  assert.equal(button(instance.render(),'دریافت اعلان‌ها').props.disabled,false);
  assert.equal(calls,0);
  assert.equal(articles(instance.render()).length,0);
});

test('invalid project/bounds/missing trusted command block operations',async()=>{
  for(const props of [
    {projectId:'../other'},{projectId:'x'.repeat(181)},{projectId:''},
    {projectId:null},{limit:0},{limit:101},{limit:'50'},{pageSize:21},
    {pageSize:0},{limit:5,pageSize:6},{command:null},
  ]){
    let calls=0;
    const instance=mount({...props,command:props.command===null?null:async()=>{
      calls++;return listed([]);
    }});
    const load=button(instance.render(),'دریافت اعلان‌ها');
    assert.equal(load.props.disabled,true,JSON.stringify(props));
    await load.props.onClick();
    assert.equal(calls,0);
    assert.ok(nodes(instance.render()).some(node=>node.props.role==='alert'));
  }
});

test('explicit list uses only exact authenticated host envelope, project and cap',async()=>{
  const traffic=[];
  const instance=mount({projectId:project,limit:3,pageSize:2,
    command:async envelope=>{traffic.push(envelope);return listed([makeNote(11)]);}});
  assert.equal(traffic.length,0);
  await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
  assert.deepEqual(traffic,[{
    schemaVersion:1,action:'list',params:{projectId:project,limit:3},
  }]);
  assert.equal(articles(instance.render()).length,1);
  assert.equal(textOf(articles(instance.render())[0]).includes('تغییر وضعیت درخواست'),true);
});

test('display keeps only safe allowlisted text; never leaks finance, recipient or actor',async()=>{
  const secret='financial-raw-should-not-render';
  const row=makeNote(2,{
    status:secret,deficiency_summary:secret,
    actor_id:secret,recipient_id:secret,
    original_request_id:secret,receipt_reference:secret,
    document_id:secret,url:'https://fake.invalid/?token='+secret,
  });
  const instance=mount({command:async()=>listed([row])});
  await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
  const tree=instance.render();
  const visible=textOf(tree);
  assert.match(visible,/تغییر وضعیت درخواست/);
  assert.match(visible,/خوانده‌نشده/);
  assert.doesNotMatch(visible,new RegExp(secret));
  assert.doesNotMatch(visible,/Madar|finance-secret|amendment-secret/i);
  const elements=nodes(tree);
  assert.equal(elements.some(node=>node.type==='a'),false);
  assert.equal(elements.some(node=>node.type==='input'),false);
});

test('foreign project row, duplicate ID, oversize and forged status fail closed',async()=>{
  for(const bad of [
    [makeNote(1,{project_id:'foreign-project'})],
    [makeNote(1),makeNote(1)],
    [makeNote(1,{channel:'email'})],
    [makeNote(1,{notice_id:'1'})],
    [makeNote(1,{event_kind:'__proto__'})],
    [makeNote(1,{read_at:'2026-01',is_read:false})],
    [makeNote(1),makeNote(2)],
  ]){
    const instance=mount({limit:1,
      command:async()=>listed(bad)});
    await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
    assert.equal(articles(instance.render()).length,0);
    assert.ok(nodes(instance.render()).some(node=>node.props.role==='alert'));
    assert.doesNotMatch(textOf(instance.render()),/foreign-project/);
  }
  for(const raw of [
    {schemaVersion:2,result:[]},
    {schemaVersion:1,result:[],action:'list'},
    {schemaVersion:1,result:{notices:[]}},
    {schemaVersion:1,error:'foreign-host-error-secret'},
  ]){
    const instance=mount({command:async()=>raw});
    await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
    assert.equal(articles(instance.render()).length,0);
    assert.ok(nodes(instance.render()).some(node=>node.props.role==='alert'));
    assert.doesNotMatch(textOf(instance.render()),/foreign-host-error-secret/);
  }
});

test('bounded local pages never send extra host requests or expose older history',async()=>{
  const traffic=[];
  const instance=mount({limit:5,pageSize:2,
    command:async body=>{
      traffic.push(body);
      return listed([1,2,3,4,5].map(id=>makeNote(id)));
    }});
  await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
  assert.equal(articles(instance.render()).length,2);
  assert.equal(button(instance.render(),'صفحه قبل').props.disabled,true);
  button(instance.render(),'صفحه بعد').props.onClick();
  assert.equal(articles(instance.render()).length,2);
  button(instance.render(),'صفحه بعد').props.onClick();
  assert.equal(articles(instance.render()).length,1);
  assert.equal(button(instance.render(),'صفحه بعد').props.disabled,true);
  assert.equal(traffic.length,1);
  assert.equal(traffic[0].params.limit,5);
  assert.match(textOf(instance.render()),/endpoint صفحه‌های قدیمی‌تر/);
});

test('double-click list and mark cannot issue duplicate concurrent requests',async()=>{
  const readAwait=deferred();
  const ackAwait=deferred();
  const traffic=[];
  const instance=mount({command:envelope=>{
    traffic.push(envelope);
    if(envelope.action==='list')return readAwait.promise;
    return ackAwait.promise;
  }});
  const load=button(instance.render(),'دریافت اعلان‌ها');
  const first=load.props.onClick();
  const second=load.props.onClick();
  assert.equal(traffic.length,1);
  assert.equal(button(instance.render(),'دریافت اعلان‌ها').props.disabled,true);
  readAwait.resolve(listed([makeNote(7)]));
  await Promise.all([first,second]);await flush();
  const mark=button(instance.render(),'خوانده شد');
  const pending=mark.props.onClick();
  await mark.props.onClick();
  assert.equal(traffic.length,2);
  assert.deepEqual(traffic[1],{
    schemaVersion:1,action:'mark-read',
    params:{noticeId:7,manualAction:true},
  });
  assert.equal(button(instance.render(),'خوانده شد').props.disabled,true);
  ackAwait.resolve(ack(7));
  await pending;await flush();
  assert.equal(articles(instance.render()).length,1);
  assert.equal(textOf(articles(instance.render())[0]).includes('خوانده‌شده'),true);
  assert.equal(nodes(articles(instance.render())[0]).some(node=>node.type==='button'),false);
  await mark.props.onClick(); // stale handler after success is also a no-op.
  assert.equal(traffic.length,2);
});

test('already-read host acknowledgment is accepted but wrong/missing ack is not',async()=>{
  const accepted=mount({command:async body=>body.action==='list'
    ?listed([makeNote(11)]):ack(11,true)});
  await button(accepted.render(),'دریافت اعلان‌ها').props.onClick();
  await button(accepted.render(),'خوانده شد').props.onClick();
  assert.match(textOf(accepted.render()),/خوانده‌شده/);
  for(const response of [
    ack(99),{schemaVersion:1,result:{notice_id:11,marked_read:true}},
    {schemaVersion:1,result:{notice_id:11,marked_read:true,already_read:true}},
    {schemaVersion:2,result:{notice_id:11,marked_read:true,already_read:false}},
  ]){
    const instance=mount({command:async body=>body.action==='list'
      ?listed([makeNote(11)]):response});
    await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
    await button(instance.render(),'خوانده شد').props.onClick();
    assert.match(textOf(instance.render()),/خوانده‌نشده/);
    assert.ok(nodes(instance.render()).some(node=>node.props.role==='alert'));
    assert.ok(button(instance.render(),'خوانده شد'));
  }
});

test('mark uncertain failure never auto-retries; explicit re-list required',async()=>{
  const traffic=[];
  const instance=mount({command:async body=>{
    traffic.push(body.action);
    if(body.action==='list')return listed([makeNote(4)]);
    throw Error('RAW_PRIVATE_TARAZ_RECEIPT_NOT_FOR_UI');
  }});
  await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
  await button(instance.render(),'خوانده شد').props.onClick();
  await flush();await flush();
  assert.deepEqual(traffic,['list','mark-read']);
  assert.match(textOf(instance.render()),/فهرست را دوباره دریافت کنید/);
  assert.doesNotMatch(textOf(instance.render()),/RAW_PRIVATE/);
});

test('stale foreign-project response ignored after project switch and return',async()=>{
  const read=deferred();
  const traffic=[];
  const command=envelope=>{
    traffic.push(envelope);
    return envelope.params.projectId==='proj-1'?read.promise:Promise.resolve(
      listed([makeNote(9,{project_id:'proj-2'})]));
  };
  const instance=mount({command,projectId:'proj-1'});
  const first=button(instance.render(),'دریافت اعلان‌ها').props.onClick();
  instance.setProps({projectId:'proj-2'});
  assert.equal(articles(instance.render()).length,0);
  read.resolve(listed([makeNote(1)]));
  await first;
  instance.setProps({projectId:'proj-1'});
  assert.equal(articles(instance.render()).length,0,
    'stale in-flight project response must not reappear after returning');
  assert.equal(traffic.length,1);
});

test('project/host callback switch invalidates loaded rows and previous actions',async()=>{
  const sent=[];
  const hostA=async envelope=>{
    sent.push(envelope);
    return listed([makeNote(1)]);
  };
  const hostB=async envelope=>{
    sent.push(envelope);
    return listed([makeNote(3)]);
  };
  const instance=mount({command:hostA});
  await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
  const oldMark=button(instance.render(),'خوانده شد');
  assert.equal(articles(instance.render()).length,1);
  instance.setProps({command:hostB});
  assert.equal(articles(instance.render()).length,0);
  await oldMark.props.onClick();
  assert.equal(sent.length,1);
  instance.setProps({command:hostA});
  assert.equal(articles(instance.render()).length,0);
});

test('late mark-read acknowledgment cannot restore prior project data',async()=>{
  const pending=deferred();
  const traffic=[];
  const instance=mount({command:async envelope=>{
    traffic.push(envelope.action);
    if(envelope.action==='list')return listed([makeNote(8)]);
    return pending.promise;
  }});
  await button(instance.render(),'دریافت اعلان‌ها').props.onClick();
  const original=button(instance.render(),'خوانده شد').props.onClick();
  instance.setProps({projectId:'proj-foreign'});
  assert.equal(articles(instance.render()).length,0);
  pending.resolve(ack(8));
  await original;
  instance.setProps({projectId:'proj-1'});
  assert.equal(articles(instance.render()).length,0);
  assert.deepEqual(traffic,['list','mark-read']);
});
