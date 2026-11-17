'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const sourcePath=path.join(root,'src','ai_usage_admin.jsx');
const original=fs.readFileSync(sourcePath,'utf8');
const compiled=esbuild.buildSync({
  entryPoints:[sourcePath],bundle:true,platform:'node',format:'cjs',write:false,
  external:['react','react/jsx-runtime'],
}).outputFiles[0].text;

function load(react=React){
  const item=new Module(sourcePath,module);
  item.filename=sourcePath;
  item.paths=Module._nodeModulePaths(path.dirname(sourcePath));
  item.require=name=>name==='react'?react:Module.prototype.require.call(item,name);
  item._compile(compiled,sourcePath);
  return item.exports;
}
const api=load();
const users=[
  {username:'editor1',role:'editor',displayName:'Sensitive Real Name',
    password:'sk-test-should-not-leak',email:'private@example.com'},
  {username:'admin1',role:'admin'},
  {username:'viewer1',role:'viewer'},
];
const props={command:async()=>{throw Error('unexpected host call');},
  projectId:'project-one',isAdmin:true,users};
const consent={preverified:true,projectId:'project-one',provider:'openai',
  requestId:'a'.repeat(32),payloadDigest:'b'.repeat(64)};
const grant={user_id:'opaque-host-user',project_id:'opaque-host-project',
  provider:'openai',version:2,enabled:true,cloud_enabled:false,
  monthly_requests:12,monthly_tokens:5000,monthly_cost_micro:100000};
const respond=(action,result,grantScope={
  projectId:'project-one',userId:'editor1',
  provider:result?.provider??'openai',
})=>({
  schemaVersion:1,action,result,
  ...(['grant_get','grant_set'].includes(action)?{grantScope}:{}),
});
const ssr=(extra={})=>renderToStaticMarkup(
  React.createElement(api.AiUsageAdminPanel,{...props,...extra}));

// Pure React hook harness, using the repository's existing UI-test pattern.
// React SSR independently checks actual generated accessible markup.
function mount(initial){
  const slots=[];
  let cursor=0;
  const stub={
    ...React,
    useId(){
      const at=cursor++;
      if(!slots[at])slots[at]={value:'test-ui-'+at};
      return slots[at].value;
    },
    useState(value){
      const at=cursor++;
      if(!slots[at])slots[at]={
        value:typeof value==='function'?value():value,
      };
      return [slots[at].value,next=>{
        slots[at].value=typeof next==='function'?next(slots[at].value):next;
      }];
    },
    useRef(value){
      const at=cursor++;
      if(!slots[at])slots[at]={value:{current:value}};
      return slots[at].value;
    },
  };
  const {AiUsageAdminPanel}=load(stub);
  let currentProps={...props,...initial};
  const render=()=>{cursor=0;return AiUsageAdminPanel(currentProps);};
  return {render,setProps(next){currentProps={...currentProps,...next};}};
}
function findNodes(node,result=[]){
  if(node===null||node===undefined||typeof node==='boolean')return result;
  if(Array.isArray(node)){for(const element of node)findNodes(element,result);return result;}
  if(typeof node!=='object'||!node.props)return result;
  if(typeof node.type==='function')return findNodes(node.type(node.props),result);
  result.push(node);findNodes(node.props.children,result);
  return result;
}
function visibleText(node){
  if(node==null||typeof node==='boolean')return '';
  if(typeof node==='string'||typeof node==='number')return String(node);
  if(Array.isArray(node))return node.map(visibleText).join(' ');
  if(typeof node.type==='function')return visibleText(node.type(node.props));
  return node.props?visibleText(node.props.children):'';
}
function button(tree,text){
  const match=findNodes(tree).find(node=>node.type==='button'
    &&visibleText(node).includes(text));
  assert.ok(match,'Missing button: '+text);
  return match;
}
function input(tree,idFragment){
  const result=findNodes(tree).find(node=>['input','select'].includes(node.type)
    &&typeof node.props.id==='string'&&node.props.id.endsWith(idFragment));
  assert.ok(result,'Missing field: '+idFragment);
  return result;
}
function check(tree,text){
  const label=findNodes(tree).find(node=>node.type==='label'
    &&visibleText(node).includes(text));
  assert.ok(label,'Missing checkbox label: '+text);
  const result=findNodes(label).find(node=>node.type==='input'
    &&node.props.type==='checkbox');
  assert.ok(result,'Missing checkbox: '+text);
  return result;
}
const choose=(instance,user='editor1',provider='openai')=>{
  input(instance.render(),'-user').props.onChange({target:{value:user}});
  input(instance.render(),'-provider').props.onChange({target:{value:provider}});
};

test('numeric limits are whole unsigned canonical digits, without overflow',()=>{
  const parse=api.parseBudgetInteger;
  for(const [value,max,expected] of [
    ['0',100,0],['100',100,100],['100000',100000,100000],
    ['1000000000000',1000000000000,1000000000000],
  ])assert.equal(parse(value,max),expected);
  for(const value of [null,undefined,{},false,10,'',' ', '00','0001','01',
    '-1','1.5','1e5','+1','Infinity','NaN','100,000',
    '۱۰۰','١٠٠','10000000000000','9007199254740993']){
    assert.equal(parse(value,1000000000000),null,String(value));
  }
});

test('grant validation enforces cloud toggle and all three monthly caps',()=>{
  const candidate={enabled:true,cloudEnabled:true,
    monthlyRequests:'12',monthlyTokens:'5000',monthlyCostMicro:'100000'};
  assert.deepEqual(api.validateAiBudgetDraft(candidate,'openai'),{
    enabled:true,cloudEnabled:true,monthlyRequests:12,
    monthlyTokens:5000,monthlyCostMicro:100000,
  });
  assert.equal(api.validateAiBudgetDraft(candidate,'local_ollama'),null);
  assert.equal(api.validateAiBudgetDraft({...candidate,enabled:false},'openai'),null);
  for(const [field,value] of [['monthlyRequests','100001'],
    ['monthlyTokens','100000001'],['monthlyCostMicro','1000000000001'],
    ['monthlyRequests','-1'],['monthlyTokens','0.2']]){
    assert.equal(api.validateAiBudgetDraft({...candidate,[field]:value},'openai'),
      null,field);
  }
});

test('host grant snapshots must be versioned, bounded and provider-specific',()=>{
  assert.equal(api.normalizeAiGrant(null,'openai').version,0);
  assert.equal(api.normalizeAiGrant(grant,'openai').monthlyTokens,'5000');
  for(const corrupted of [
    undefined,{},[],{...grant,provider:'gemini'},
    {...grant,version:0},{...grant,version:'2'},
    {...grant,cloud_enabled:1},{...grant,monthly_requests:-1},
    {...grant,monthly_tokens:Infinity},{...grant,monthly_cost_micro:1e15},
  ])assert.equal(api.normalizeAiGrant(corrupted,'openai'),null);
  assert.equal(api.normalizeAiGrant({...grant,provider:'local_ollama',
    cloud_enabled:true},'local_ollama'),null);
});

test('only exact preverified cloud hint for current project is accepted',()=>{
  assert.deepEqual(api.validatePreverifiedCloudIntent(consent,'project-one'),{
    projectId:'project-one',provider:'openai',
    requestId:consent.requestId,payloadDigest:consent.payloadDigest,
  });
  for(const corrupt of [
    null,{},[],{...consent,preverified:1},
    {...consent,projectId:'project-two'},
    {...consent,provider:'local_ollama'},
    {...consent,requestId:'not-an-id'},
    {...consent,payloadDigest:'not-a-digest'},
    {...consent,promptText:'secret private content'},
  ])assert.equal(api.validatePreverifiedCloudIntent(corrupt,'project-one'),null);
});

test('SSR is accessible RTL, labels match inputs, no secrets or extra fields',()=>{
  const html=ssr({cloudConsent:consent});
  assert.match(html,/dir="rtl"/);
  assert.match(html,/aria-labelledby=/);
  assert.match(html,/:focus-visible/);
  assert.match(ssr({cloudConsent:null}),/role="status"/);
  assert.match(html,/aria-label="حدود مجاز مصرف"/);
  assert.match(html,/type="checkbox"/);
  assert.match(html,/autoComplete="off"|autoComplete=/i);
  assert.match(html,/CAS|کنترل نسخه/);
  assert.match(html,/disabled=""/);
  assert.doesNotMatch(html,/Sensitive Real Name|private@example.com/);
  assert.doesNotMatch(html,/sk-test-should-not-leak/);
  assert.doesNotMatch(html,/a{32}|b{64}/);
  assert.doesNotMatch(html,/آپلود|API Key|توکن دسترسی|ارسال پرامپت/);
  for(const field of ['user','provider','monthlyRequests','monthlyTokens',
    'monthlyCostMicro']){
    assert.match(html,new RegExp('id="[^"]+-'+field+'"'));
    assert.match(html,new RegExp('for="[^"]+-'+field+'"'));
  }
});

test('LTR support and nonadmin view omit all management controls',()=>{
  const html=ssr({dir:'ltr',isAdmin:false,users:[],cloudConsent:null});
  assert.match(html,/dir="ltr"/);
  assert.doesNotMatch(html,/خواندن مجوز|ذخیره مجوز|حدود مجاز مصرف/);
  assert.match(html,/درخواست ابری پیش‌بررسی‌شده/);
});

test('invalid project, missing command and malformed directory fail closed',()=>{
  for(const variation of [
    {projectId:'../secret'},{projectId:''},{command:undefined},
    {users:null},{users:[...users,{username:'editor1',role:'editor'}]},
    {users:[{username:'bad user',role:'admin'}]},
    {users:[{username:'demo',role:'unexpected'}]},
  ]){
    const html=ssr(variation);
    for(const label of ['خواندن مجوز','ذخیره مجوز با کنترل نسخه']){
      const tag=html.match(new RegExp('<button([^>]*)>'+label+'<\\/button>'));
      if(tag)assert.match(tag[1],/disabled=""/,label);
    }
    if(Object.prototype.hasOwnProperty.call(variation,'projectId')
      ||Object.prototype.hasOwnProperty.call(variation,'command'))
      assert.match(html,/عملیات غیرفعال است/);
  }
});

test('mount makes zero host calls and requires explicit grant read',()=>{
  const calls=[];
  const m=mount({command:async(...args)=>{calls.push(args);return respond('grant_get',null);}});
  assert.equal(calls.length,0);
  assert.equal(button(m.render(),'خواندن مجوز').props.disabled,true);
  choose(m);
  assert.equal(button(m.render(),'خواندن مجوز').props.disabled,false);
  assert.equal(button(m.render(),'ذخیره مجوز').props.disabled,true);
  assert.equal(calls.length,0);
});

test('explicit grant_get null initialises CAS v0 and save sends exact bounded values',async()=>{
  const calls=[];
  const m=mount({command:async(action,data,projectId)=>{
    calls.push({action,data,projectId});
    if(action==='grant_get')return respond(action,null);
    if(action==='grant_set')return respond(action,{
      ...grant,version:1,enabled:data.enabled,cloud_enabled:data.cloudEnabled,
      monthly_requests:data.monthlyRequests,monthly_tokens:data.monthlyTokens,
      monthly_cost_micro:data.monthlyCostMicro,
    });
    throw Error('unexpected');
  }});
  choose(m);
  await button(m.render(),'خواندن مجوز').props.onClick();
  assert.match(visibleText(m.render()),/CAS v\s*0/);
  check(m.render(),'فعال بودن مجوز').props.onChange({target:{checked:true}});
  check(m.render(),'اجازه استفاده ابری').props.onChange({target:{checked:true}});
  for(const [field,value] of [['monthlyRequests','3'],['monthlyTokens','420'],
    ['monthlyCostMicro','1000']])
    input(m.render(),'-'+field).props.onChange({target:{value}});
  assert.equal(button(m.render(),'ذخیره مجوز').props.disabled,false);
  await button(m.render(),'ذخیره مجوز').props.onClick();
  const save=calls.at(-1);
  assert.equal(save.action,'grant_set');
  assert.equal(save.projectId,'project-one');
  assert.equal(save.data.userId,'editor1');
  assert.equal(save.data.provider,'openai');
  assert.equal(save.data.enabled,true);
  assert.equal(save.data.cloudEnabled,true);
  assert.equal(save.data.monthlyRequests,3);
  assert.equal(save.data.monthlyTokens,420);
  assert.equal(save.data.monthlyCostMicro,1000);
  assert.equal(save.data.expectedVersion,0);
  assert.match(save.data.eventId,/^ai-ui-[0-9a-f-]+$/);
  assert.equal(Object.keys(save.data).length,9);
  assert.match(visibleText(m.render()),/CAS v\s*1/);
  assert.match(visibleText(m.render()),/مجوز با نسخه جدید ثبت شد/);
});

test('admin cloud enable is explicit and never auto enabled on provider switch',async()=>{
  const calls=[];
  const m=mount({command:async(action,data)=>{
    calls.push([action,data]);
    if(action==='grant_get')return respond('grant_get',null,{
      projectId:'project-one',userId:data.userId,provider:data.provider,
    });
    return respond('grant_set',{
      ...grant,provider:data.provider,version:1,
      enabled:data.enabled,cloud_enabled:data.cloudEnabled,
      monthly_requests:data.monthlyRequests,monthly_tokens:data.monthlyTokens,
      monthly_cost_micro:data.monthlyCostMicro,
    });
  }});
  choose(m);
  await button(m.render(),'خواندن مجوز').props.onClick();
  check(m.render(),'فعال بودن مجوز').props.onChange({target:{checked:true}});
  assert.equal(check(m.render(),'اجازه استفاده ابری').props.checked,false);
  input(m.render(),'-provider').props.onChange({target:{value:'local_ollama'}});
  assert.equal(button(m.render(),'ذخیره مجوز').props.disabled,true);
  await button(m.render(),'خواندن مجوز').props.onClick();
  assert.equal(check(m.render(),'فعال بودن مجوز').props.checked,false);
  assert.equal(findNodes(m.render()).filter(n=>n.type==='label'
    &&visibleText(n).includes('اجازه استفاده ابری')).length,0);
  assert.equal(calls.some(([action])=>action==='grant_set'),false);
});

test('invalid numeric input blocks save and no command is issued',async()=>{
  const calls=[];
  const m=mount({command:async(...args)=>{
    calls.push(args);return respond('grant_get',null);
  }});
  choose(m);
  await button(m.render(),'خواندن مجوز').props.onClick();
  for(const value of ['01','-10','1000000000001']){
    input(m.render(),'-monthlyCostMicro').props.onChange({target:{value}});
    assert.equal(button(m.render(),'ذخیره مجوز').props.disabled,true);
  }
  assert.equal(calls.length,1);
});

test('CAS host error is safe, never logs secret and retries same event',async()=>{
  const calls=[];
  const m=mount({command:async(action,data)=>{
    calls.push([action,data]);
    if(action==='grant_get')return respond(action,grant);
    const error=Error('secret-key=should-not-leak');
    error.code='version_conflict';
    throw error;
  }});
  choose(m);
  await button(m.render(),'خواندن مجوز').props.onClick();
  await button(m.render(),'ذخیره مجوز').props.onClick();
  assert.match(visibleText(m.render()),/نسخه مجوز تغییر کرده/);
  assert.doesNotMatch(visibleText(m.render()),/secret-key/);
  await button(m.render(),'ذخیره مجوز').props.onClick();
  assert.equal(calls[1][1].eventId,calls[2][1].eventId);
  assert.equal(calls[1][1].expectedVersion,2);
  assert.equal(calls[2][1].expectedVersion,2);
});

test('malformed host snapshots fail closed and never permit save',async()=>{
  for(const result of [
    {schemaVersion:2,action:'grant_get',result:grant},
    {schemaVersion:1,action:'wrong',result:grant},
    respond('grant_get',{...grant,version:-1}),
    respond('grant_get',{...grant,provider:'anthropic'}),
    undefined,
  ]){
    const m=mount({command:async()=>result});
    choose(m);
    await button(m.render(),'خواندن مجوز').props.onClick();
    assert.equal(button(m.render(),'ذخیره مجوز').props.disabled,true);
    assert.match(visibleText(m.render()),/عملیات تأیید نشد/);
  }
});

test('contradictory grant_set response is not treated as saved',async()=>{
  const calls=[];
  const m=mount({command:async(action,data)=>{
    calls.push([action,data]);
    if(action==='grant_get')return respond('grant_get',null);
    return respond('grant_set',{
      ...grant,version:1,enabled:true,cloud_enabled:true,
      monthly_requests:99,monthly_tokens:5000,monthly_cost_micro:100000,
    });
  }});
  choose(m);
  await button(m.render(),'خواندن مجوز').props.onClick();
  await button(m.render(),'ذخیره مجوز').props.onClick();
  assert.match(visibleText(m.render()),/عملیات تأیید نشد/);
  assert.match(visibleText(m.render()),/CAS v\s*0/);
  await button(m.render(),'ذخیره مجوز').props.onClick();
  assert.equal(calls[1][1].eventId,calls[2][1].eventId);
});

test('no stale grant response may populate another selected scope',async()=>{
  let finish;
  const delayed=new Promise(resolve=>{finish=resolve;});
  const calls=[];
  const m=mount({command:(action,data)=>{
    calls.push([action,data]);return delayed;
  }});
  choose(m,'editor1','openai');
  const pending=button(m.render(),'خواندن مجوز').props.onClick();
  // Simulates caller changing scope while an old RPC is in flight.
  input(m.render(),'-user').props.onChange({target:{value:'admin1'}});
  m.render();
  finish(respond('grant_get',grant));
  await pending;
  assert.equal(button(m.render(),'ذخیره مجوز').props.disabled,true);
  assert.doesNotMatch(visibleText(m.render()),/CAS v\s*2/);
  assert.equal(calls.length,1);
});

test('preverified consent only posts after explicit checkbox; never sends model',async()=>{
  const calls=[];
  const m=mount({isAdmin:false,cloudConsent:consent,command:async(...args)=>{
    calls.push(args);return respond('cloud_consent','recorded');
  }});
  assert.equal(calls.length,0);
  assert.equal(button(m.render(),'ثبت قصد رضایت').props.disabled,true);
  check(m.render(),'تأیید می‌کنم قصد ثبت رضایت').props.onChange({
    target:{checked:true},
  });
  assert.equal(button(m.render(),'ثبت قصد رضایت').props.disabled,false);
  await button(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(calls.length,1);
  assert.equal(calls[0][0],'cloud_consent');
  assert.deepEqual(Object.keys(calls[0][1]).sort(),
    ['eventId','payloadDigest','provider','requestId'].sort());
  assert.equal(calls[0][1].requestId,consent.requestId);
  assert.equal(calls[0][1].payloadDigest,consent.payloadDigest);
  assert.equal(calls[0][2],'project-one');
  assert.equal(button(m.render(),'ثبت قصد رضایت').props.disabled,true);
  assert.match(visibleText(m.render()),/هیچ متنی به ارائه‌دهنده ارسال نشد/);
  assert.equal(calls.some(([action])=>action==='reserve'||action==='generate'),false);
});

test('completed one-use consent stays disabled if hint changes away and returns',async()=>{
  const calls=[];
  const m=mount({isAdmin:false,cloudConsent:consent,
    command:async(...args)=>{calls.push(args);return respond('cloud_consent','recorded');}});
  check(m.render(),'تأیید می‌کنم قصد ثبت رضایت').props.onChange({target:{checked:true}});
  await button(m.render(),'ثبت قصد رضایت').props.onClick();
  m.setProps({cloudConsent:{...consent,requestId:'c'.repeat(32)}});
  assert.equal(button(m.render(),'ثبت قصد رضایت').props.disabled,true);
  m.setProps({cloudConsent:consent});
  assert.equal(button(m.render(),'ثبت قصد رضایت').props.disabled,true);
  assert.equal(calls.length,1);
});

test('in-flight consent never calls host twice from a repeated click',async()=>{
  const calls=[];
  let resolve;
  const deferred=new Promise(done=>{resolve=done;});
  const m=mount({isAdmin:false,cloudConsent:consent,
    command:(...args)=>{calls.push(args);return deferred;}});
  check(m.render(),'تأیید می‌کنم قصد ثبت رضایت').props.onChange({target:{checked:true}});
  const running=button(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(button(m.render(),'ثبت قصد رضایت').props.disabled,true);
  await button(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(calls.length,1);
  resolve(respond('cloud_consent','recorded'));
  await running;
  assert.equal(button(m.render(),'ثبت قصد رضایت').props.disabled,true);
});

test('cloud consent failure is safe and retry uses stable eventId',async()=>{
  const calls=[];
  const m=mount({cloudConsent:consent,command:async(action,data)=>{
    calls.push([action,data]);
    const err=new Error('Private prompt should not be shown');
    err.code='consent_required';
    throw err;
  }});
  check(m.render(),'تأیید می‌کنم قصد ثبت رضایت').props.onChange({
    target:{checked:true},
  });
  await button(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.match(visibleText(m.render()),/رضایت معتبر/);
  assert.doesNotMatch(visibleText(m.render()),/Private prompt/);
  await button(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(calls[0][1].eventId,calls[1][1].eventId);
});

test('invalid or cross-project intent makes consent unavailable',()=>{
  for(const cloudConsent of [
    {...consent,projectId:'project-other'},
    {...consent,requestId:'bad'},
    {...consent,preverified:false},
    {...consent,provider:'local_ollama'},
    {...consent,prompt:'secret'},
  ]){
    const m=mount({isAdmin:false,cloudConsent});
    const html=renderToStaticMarkup(React.createElement(
      api.AiUsageAdminPanel,{...props,isAdmin:false,cloudConsent}));
    assert.doesNotMatch(html,/ثبت قصد رضایت \(بدون ارسال\)/);
    assert.match(visibleText(m.render()),/پیش‌بررسی‌شده در دسترس نیست/);
  }
});

test('standalone source never accesses network, credentials or browser storage',()=>{
  assert.doesNotMatch(original,/\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b/);
  assert.doesNotMatch(original,/\b(localStorage|sessionStorage|indexedDB)\b/);
  assert.doesNotMatch(original,/\bconsole\.(log|warn|error|info)\s*\(/);
  assert.doesNotMatch(original,/\b(apiKey|password|promptText|uploadFile)\s*:/);
});
