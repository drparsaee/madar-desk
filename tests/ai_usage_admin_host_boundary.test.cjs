'use strict';
/**
 * Synthetic, read-only E1 UI/host boundary characterisation.
 * Owns no production code, profiles, fixtures, network access or dispatch.
 * Tests marked "OBSERVED GAP" deliberately report current exposure rather
 * than weakening an assertion to claim an absent security control.
 */
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const Module=require('node:module');
const {spawnSync}=require('node:child_process');
const React=require('react');
const esbuild=require('esbuild');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const source=path.join(root,'src','ai_usage_admin.jsx');
const js=esbuild.buildSync({entryPoints:[source],bundle:true,platform:'node',
  format:'cjs',write:false,external:['react','react/jsx-runtime']}).outputFiles[0].text;
function getComponent(react=React){
  const moduleCopy=new Module(source,module);
  moduleCopy.filename=source;
  moduleCopy.paths=Module._nodeModulePaths(path.dirname(source));
  moduleCopy.require=name=>name==='react'?react:Module.prototype.require.call(moduleCopy,name);
  moduleCopy._compile(js,source);
  return moduleCopy.exports.AiUsageAdminPanel;
}
const AiUsageAdminPanel=getComponent();
const users=[
  {username:'editor-one',role:'editor',displayName:'PRIVATE SHOULD NOT RENDER',
    email:'private@example.invalid',apiKey:'synthetic-key'},
  {username:'admin-one',role:'admin'},
  {username:'viewer-one',role:'viewer'},
];
const grant={user_id:'pseudonym-A',project_id:'pseudonym-project-A',
  provider:'openai',version:7,enabled:true,cloud_enabled:false,
  monthly_requests:10,monthly_tokens:1000,monthly_cost_micro:300};
const consent={preverified:true,projectId:'project-one',provider:'openai',
  requestId:'a'.repeat(32),payloadDigest:'b'.repeat(64)};
const reply=(action,result,grantScope={
  projectId:'project-one',userId:'editor-one',
  provider:result?.provider??'openai',
})=>({
  schemaVersion:1,action,result,
  ...(['grant_get','grant_set'].includes(action)?{grantScope}:{}),
});
const base={isAdmin:true,projectId:'project-one',users,
  command:async()=>{throw Error('no implicit command allowed');}};

function harness(extra={}){
  const slots=[];
  let index=0;
  const fakeReact={
    ...React,
    useId(){
      const at=index++;
      if(!slots[at])slots[at]={value:'boundary-'+at};
      return slots[at].value;
    },
    useState(initial){
      const at=index++;
      if(!slots[at])slots[at]={value:typeof initial==='function'?initial():initial};
      return [slots[at].value,next=>{
        slots[at].value=typeof next==='function'?next(slots[at].value):next;
      }];
    },
    useRef(initial){
      const at=index++;
      if(!slots[at])slots[at]={value:{current:initial}};
      return slots[at].value;
    },
  };
  const Component=getComponent(fakeReact);
  let props={...base,...extra};
  return {
    render(){index=0;return Component(props);},
    setProps(next){props={...props,...next};},
  };
}
function visit(node,out=[]){
  if(node===null||node===undefined||typeof node==='boolean')return out;
  if(Array.isArray(node)){for(const child of node)visit(child,out);return out;}
  if(typeof node!=='object'||!node.props)return out;
  if(typeof node.type==='function')return visit(node.type(node.props),out);
  out.push(node);visit(node.props.children,out);
  return out;
}
function words(node){
  if(node===null||node===undefined||typeof node==='boolean')return '';
  if(Array.isArray(node))return node.map(words).join(' ');
  if(typeof node==='string'||typeof node==='number')return String(node);
  if(typeof node.type==='function')return words(node.type(node.props));
  return node.props?words(node.props.children):'';
}
function btn(tree,needle){
  const found=visit(tree).find(node=>node.type==='button'
    &&words(node).includes(needle));
  assert.ok(found,'Missing button '+needle);
  return found;
}
function field(tree,suffix){
  const found=visit(tree).find(node=>['input','select'].includes(node.type)
    &&typeof node.props.id==='string'&&node.props.id.endsWith(suffix));
  assert.ok(found,'Missing field '+suffix);
  return found;
}
function checkbox(tree,needle){
  const label=visit(tree).find(node=>node.type==='label'
    &&words(node).includes(needle));
  assert.ok(label,'Missing label '+needle);
  const found=visit(label).find(node=>node.type==='input'&&node.props.type==='checkbox');
  assert.ok(found,'Missing checkbox '+needle);
  return found;
}
function select(m,user='editor-one',provider='openai'){
  field(m.render(),'-user').props.onChange({target:{value:user}});
  field(m.render(),'-provider').props.onChange({target:{value:provider}});
}
function checkConsent(m){
  checkbox(m.render(),'تأیید می‌کنم قصد ثبت رضایت').props.onChange({
    target:{checked:true},
  });
}
function safeString(value){return JSON.stringify(value);}

test('no render/mount-side-effect, and explicit grant read must precede CAS save',async()=>{
  const calls=[];
  const m=harness({command:async(...args)=>{
    calls.push(args);
    return reply('grant_get',null);
  }});
  m.render();m.render();
  assert.equal(calls.length,0);
  assert.equal(btn(m.render(),'خواندن مجوز').props.disabled,true);
  select(m);
  assert.equal(btn(m.render(),'ذخیره مجوز').props.disabled,true);
  await btn(m.render(),'خواندن مجوز').props.onClick();
  assert.deepEqual(calls, [['grant_get',{
    userId:'editor-one',provider:'openai'},'project-one']]);
  assert.match(words(m.render()),/CAS v\s*0/);
  assert.equal(btn(m.render(),'ذخیره مجوز').props.disabled,false);
});

test('host command grant_set is CAS exact-shape, bounded, no actor/org/PII',async()=>{
  const calls=[];
  const m=harness({command:async(action,data,project)=>{
    calls.push({action,data,project});
    if(action==='grant_get')return reply(action,null);
    assert.equal(action,'grant_set');
    return reply(action,{
      provider:data.provider,version:data.expectedVersion+1,
      enabled:data.enabled,cloud_enabled:data.cloudEnabled,
      monthly_requests:data.monthlyRequests,monthly_tokens:data.monthlyTokens,
      monthly_cost_micro:data.monthlyCostMicro,
    });
  }});
  select(m);
  await btn(m.render(),'خواندن مجوز').props.onClick();
  checkbox(m.render(),'فعال بودن مجوز').props.onChange({target:{checked:true}});
  checkbox(m.render(),'اجازه استفاده ابری').props.onChange({target:{checked:true}});
  for(const [name,value] of [['monthlyRequests','5'],['monthlyTokens','200'],
    ['monthlyCostMicro','300']]){
    field(m.render(),'-'+name).props.onChange({target:{value}});
  }
  await btn(m.render(),'ذخیره مجوز').props.onClick();
  const saved=calls[1];
  assert.equal(saved.project,'project-one');
  assert.deepEqual(Object.keys(saved.data).sort(),[
    'cloudEnabled','enabled','eventId','expectedVersion','monthlyCostMicro',
    'monthlyRequests','monthlyTokens','provider','userId',
  ].sort());
  assert.deepEqual({...saved.data,eventId:'synthetic-event'},{
    userId:'editor-one',provider:'openai',enabled:true,cloudEnabled:true,
    monthlyRequests:5,monthlyTokens:200,monthlyCostMicro:300,
    expectedVersion:0,eventId:'synthetic-event',
  });
  assert.match(saved.data.eventId,/^ai-ui-[0-9a-f-]+$/);
  assert.match(words(m.render()),/CAS v\s*1/);
  const raw=safeString(calls);
  for(const secret of ['private@example.invalid','PRIVATE SHOULD NOT RENDER',
    'synthetic-key','apiKey','payloadDigest','orgId','actorId','role']){
    assert.equal(raw.includes(secret),false,secret);
  }
});

test('CAS stale/revoked response leaves previous version and stable retry ID',async()=>{
  const calls=[];
  const m=harness({command:async(action,data)=>{
    calls.push({action,data});
    if(action==='grant_get')return reply(action,grant);
    const error=new Error('private server stack and token should not render');
    error.code='version_conflict';
    throw error;
  }});
  select(m);
  await btn(m.render(),'خواندن مجوز').props.onClick();
  await btn(m.render(),'ذخیره مجوز').props.onClick();
  assert.match(words(m.render()),/نسخه مجوز تغییر کرده/);
  assert.doesNotMatch(words(m.render()),/private server stack/);
  assert.match(words(m.render()),/CAS v\s*7/);
  await btn(m.render(),'ذخیره مجوز').props.onClick();
  assert.equal(calls[1].data.expectedVersion,7);
  assert.equal(calls[1].data.eventId,calls[2].data.eventId);
  assert.equal(calls.length,3);
});

test('reordered/contradictory host action and budget cannot become saved',async()=>{
  const variants=[
    {schemaVersion:1,action:'grant_get',result:grant},
    {schemaVersion:2,action:'grant_set',result:{...grant,version:8}},
    reply('grant_set',{...grant,version:8,enabled:false}),
    reply('grant_set',{...grant,version:9}),
  ];
  for(const invalid of variants){
    const m=harness({command:async(action)=>{
      if(action==='grant_get')return reply(action,grant);
      return invalid;
    }});
    select(m);
    await btn(m.render(),'خواندن مجوز').props.onClick();
    await btn(m.render(),'ذخیره مجوز').props.onClick();
    assert.match(words(m.render()),/عملیات تأیید نشد/);
    assert.match(words(m.render()),/CAS v\s*7/);
  }
});

test('old in-flight grant read cannot authorize a newly selected project',async()=>{
  let resolve;
  const wait=new Promise(done=>{resolve=done;});
  const calls=[];
  const m=harness({command:(...args)=>{calls.push(args);return wait;}});
  select(m);
  const pending=btn(m.render(),'خواندن مجوز').props.onClick();
  m.setProps({projectId:'project-two'});
  assert.equal(btn(m.render(),'ذخیره مجوز').props.disabled,true);
  resolve(reply('grant_get',grant));
  await pending;
  assert.equal(btn(m.render(),'ذخیره مجوز').props.disabled,true);
  assert.doesNotMatch(words(m.render()),/CAS v\s*7/);
  assert.equal(calls.length,1);
  assert.equal(calls[0][2],'project-one');
});

test('admin privilege display revoked while mounted disables any new action',async()=>{
  const calls=[];
  const m=harness({command:async(...args)=>{
    calls.push(args);return reply('grant_get',grant);
  }});
  select(m);
  await btn(m.render(),'خواندن مجوز').props.onClick();
  m.setProps({isAdmin:false});
  assert.equal(visit(m.render()).filter(node=>node.type==='button'
    &&words(node).includes('ذخیره مجوز')).length,0);
  assert.equal(calls.length,1);
});

test('spoofed isAdmin prop cannot override a host-side permission denial',async()=>{
  const calls=[];
  const m=harness({isAdmin:true,command:async(...args)=>{
    calls.push(args);
    const denied=new Error('real account and server internals must stay hidden');
    denied.code='permission_denied';
    throw denied;
  }});
  select(m);
  await btn(m.render(),'خواندن مجوز').props.onClick();
  assert.equal(btn(m.render(),'ذخیره مجوز').props.disabled,true);
  assert.match(words(m.render()),/مجوز انجام عملیات ندارید/);
  assert.doesNotMatch(words(m.render()),/server internals/);
  assert.deepEqual(calls.map(call=>call[0]),['grant_get']);
});

test('cloud consent needs exact hint and fresh human checkbox, one action only',async()=>{
  const calls=[];
  const m=harness({isAdmin:false,cloudConsent:consent,
    command:async(...args)=>{calls.push(args);return reply('cloud_consent','recorded');}});
  assert.equal(btn(m.render(),'ثبت قصد رضایت').props.disabled,true);
  assert.equal(calls.length,0);
  checkConsent(m);
  await btn(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(calls.length,1);
  assert.deepEqual(calls[0].slice(0,1),['cloud_consent']);
  assert.deepEqual(Object.keys(calls[0][1]).sort(),[
    'eventId','payloadDigest','provider','requestId'].sort());
  assert.equal(calls[0][1].requestId,consent.requestId);
  assert.equal(calls[0][1].payloadDigest,consent.payloadDigest);
  assert.equal(calls[0][2],'project-one');
  assert.equal(btn(m.render(),'ثبت قصد رضایت').props.disabled,true);
  assert.doesNotMatch(words(m.render()),/a{32}|b{64}/);
  assert.match(words(m.render()),/هیچ متنی به ارائه‌دهنده ارسال نشد/);
  m.setProps({cloudConsent:{...consent,requestId:'c'.repeat(32)}});
  assert.equal(btn(m.render(),'ثبت قصد رضایت').props.disabled,true);
  m.setProps({cloudConsent:consent});
  assert.equal(btn(m.render(),'ثبت قصد رضایت').props.disabled,true);
  assert.equal(calls.length,1);
});

test('cloud consent in flight is single submit; callback cannot send or reserve',async()=>{
  const calls=[];
  let finish;
  const wait=new Promise(done=>{finish=done;});
  const m=harness({isAdmin:false,cloudConsent:consent,
    command:(...args)=>{calls.push(args);return wait;}});
  checkConsent(m);
  const first=btn(m.render(),'ثبت قصد رضایت').props.onClick();
  const second=btn(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(btn(m.render(),'ثبت قصد رضایت').props.disabled,true);
  await second;
  assert.equal(calls.length,1);
  finish(reply('cloud_consent','recorded_replay'));
  await first;
  assert.equal(btn(m.render(),'ثبت قصد رضایت').props.disabled,true);
  assert.deepEqual(calls.map(value=>value[0]),['cloud_consent']);
  assert.doesNotMatch(safeString(calls),/mark_dispatched|reserve|send|generate/);
});

test('failed consent retry keeps exact event ID; new intent needs new explicit checkbox',async()=>{
  const calls=[];
  let tries=0;
  const m=harness({isAdmin:false,cloudConsent:consent,
    command:async(action,data,projectId)=>{
      calls.push({action,data,projectId});tries++;
      if(tries===1){const error=new Error('prompt and credential');
        error.code='consent_required';throw error;}
      return reply(action,'recorded');
    }});
  checkConsent(m);
  await btn(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.doesNotMatch(words(m.render()),/prompt and credential/);
  assert.match(words(m.render()),/رضایت معتبر/);
  await btn(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(calls.length,2);
  assert.equal(calls[0].data.eventId,calls[1].data.eventId);
  assert.equal(btn(m.render(),'ثبت قصد رضایت').props.disabled,true);
  m.setProps({cloudConsent:{...consent,requestId:'c'.repeat(32)}});
  assert.equal(btn(m.render(),'ثبت قصد رضایت').props.disabled,true);
  checkConsent(m);
  await btn(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(calls.length,3);
  assert.notEqual(calls[1].data.eventId,calls[2].data.eventId);
});

test('consent prop cannot override project and must contain no text/credential field',()=>{
  const sourceCases=[
    {...consent,projectId:'other-project'},
    {...consent,provider:'local_ollama'},
    {...consent,requestId:'NOT-HEX'},
    {...consent,payloadDigest:'not-a-digest'},
    {...consent,preverified:1},
    {...consent,promptText:'private'},
    {...consent,apiKey:'secret'},
    {...consent,orgId:'forged-org'},
  ];
  for(const intent of sourceCases){
    const m=harness({isAdmin:false,cloudConsent:intent});
    assert.equal(visit(m.render()).some(node=>node.type==='button'
      &&words(node).includes('ثبت قصد رضایت')),false);
  }
});

test('strict host JSON envelope grammar accepts UI commands and rejects injection',async()=>{
  const calls=[];
  const m=harness({command:async(action,data,project)=>{
    calls.push({action,data,project});
    if(action==='grant_get')return reply(action,null);
    if(action==='grant_set')return reply(action,{
      provider:data.provider,version:1,enabled:data.enabled,
      cloud_enabled:data.cloudEnabled,monthly_requests:data.monthlyRequests,
      monthly_tokens:data.monthlyTokens,monthly_cost_micro:data.monthlyCostMicro,
    });
    return reply(action,'recorded');
  },cloudConsent:consent});
  select(m);
  await btn(m.render(),'خواندن مجوز').props.onClick();
  await btn(m.render(),'ذخیره مجوز').props.onClick();
  checkConsent(m);
  await btn(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.deepEqual(calls.map(call=>call.action),[
    'grant_get','grant_set','cloud_consent']);
  const wrap=call=>({
    schemaVersion:1,action:call.action,projectId:call.project,data:call.data,
    ...(['grant_set','cloud_consent'].includes(call.action)
      ?{manualAction:true}:{}),
  });
  const items=[
    ...calls.map(call=>wrap(call)),
    (()=>{const missing=wrap(calls[1]);delete missing.manualAction;return missing;})(),
    {...wrap(calls[2]),manualAction:false},
    {...wrap(calls[1]),manualAction:1},
    {...wrap(calls[1]),orgId:'forged'},
    {...wrap(calls[2]),data:{...calls[2].data,apiKey:'forbidden'}},
    {...wrap(calls[0]),manualAction:true},
  ];
  // Evaluate actual host parser only: no LanService instance, profile or
  // real network, only JSON bytes through stdin to a local Python process.
  const python=[
    'import sys,json',
    'from madar_ai_usage_host_adapter import _command,AiUsageHostError',
    'items=json.load(sys.stdin)',
    'out=[]',
    'for command in items:',
    ' try:',
    '  result=_command(json.dumps(command))',
    '  out.append({"allowed":result["action"]})',
    ' except AiUsageHostError as error:',
    '  out.append({"denied":error.code})',
    'print(json.dumps(out))',
  ].join('\n');
  const run=spawnSync('py',['-3.12','-B','-c',python],{
    cwd:root,input:JSON.stringify(items),encoding:'utf8',timeout:15000,
    env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'},
  });
  assert.equal(run.status,0,
    'Host parser could not run: '+String(run.stderr).slice(0,700));
  const parsed=JSON.parse(run.stdout);
  assert.deepEqual(parsed,[
    {allowed:'grant_get'},{allowed:'grant_set'},{allowed:'cloud_consent'},
    {denied:'invalid_command'},{denied:'manual_action_required'},
    {denied:'manual_action_required'},{denied:'invalid_command'},
    {denied:'invalid_data'},{denied:'invalid_command'},
  ]);
});

test('OBSERVED LIMIT: opaque wrong-user grant data needs host source attestation',async()=>{
  const m=harness({command:async(action,data)=>{
    if(action==='grant_get')return reply(action,null);
    if(action==='grant_set')return reply(action,{
      user_id:'unrelated-pseudonym',project_id:'unrelated-project',
      provider:data.provider,version:1,enabled:data.enabled,
      cloud_enabled:data.cloudEnabled,
      monthly_requests:data.monthlyRequests,monthly_tokens:data.monthlyTokens,
      monthly_cost_micro:data.monthlyCostMicro,
    });
    throw Error('unsupported');
  }});
  select(m);
  await btn(m.render(),'خواندن مجوز').props.onClick();
  await btn(m.render(),'ذخیره مجوز').props.onClick();
  assert.match(words(m.render()),/مجوز با نسخه جدید ثبت شد/);
  // A forged wrapper can still lie consistently about scope and opaque IDs.
  // This component cannot derive the host secret to cross-check pseudonyms;
  // its injected command must be bound to the authenticated host adapter.
});

test('OBSERVED LIMIT: synthetic wrong-user opaque grant is accepted with correctly attested wrapper',async()=>{
  // This is a characterization of a security gap, not a passing ACL claim.
  // Host-HMAC pseudonyms cannot be independently compared to raw usernames.
  // This test intentionally forges BOTH the opaque fields and routing scope.
  const foreign={...grant,user_id:'opaque-FOREIGN-user',
    project_id:'opaque-FOREIGN-project'};
  const m=harness({command:async(action)=>{
    assert.equal(action,'grant_get');
    return reply(action,foreign);
  }});
  select(m);
  await btn(m.render(),'خواندن مجوز').props.onClick();
  const unexpectedlyEnabled=btn(m.render(),'ذخیره مجوز').props.disabled===false;
  assert.equal(unexpectedlyEnabled,true,
    'A forged command wrapper must remain documented as a trust boundary');
});

test('wrong-target, wrong-project or missing grantScope blocks grant_get and CAS save',async()=>{
  const variants=[
    {projectId:'project-one',userId:'different-user',provider:'openai'},
    {projectId:'different-project',userId:'editor-one',provider:'openai'},
    {projectId:'project-one',userId:'editor-one',provider:'gemini'},
    null,
  ];
  for(const invalid of variants){
    const m=harness({command:async(action)=>{
      assert.equal(action,'grant_get');
      const response=reply('grant_get',grant);
      if(invalid===null)delete response.grantScope;
      else response.grantScope=invalid;
      return response;
    }});
    select(m);
    await btn(m.render(),'خواندن مجوز').props.onClick();
    assert.equal(btn(m.render(),'ذخیره مجوز').props.disabled,true);
    assert.match(words(m.render()),/عملیات تأیید نشد/);
  }
});

test('wrong-target, wrong-project or missing grantScope rejects saved status',async()=>{
  for(const invalid of [
    {projectId:'project-one',userId:'another-user',provider:'openai'},
    {projectId:'wrong-project',userId:'editor-one',provider:'openai'},
    null,
  ]){
    const m=harness({command:async(action,data)=>{
      if(action==='grant_get')return reply(action,null);
      const response=reply(action,{
        provider:data.provider,version:1,enabled:data.enabled,
        cloud_enabled:data.cloudEnabled,monthly_requests:data.monthlyRequests,
        monthly_tokens:data.monthlyTokens,monthly_cost_micro:data.monthlyCostMicro,
      });
      if(invalid===null)delete response.grantScope;
      else response.grantScope=invalid;
      return response;
    }});
    select(m);
    await btn(m.render(),'خواندن مجوز').props.onClick();
    await btn(m.render(),'ذخیره مجوز').props.onClick();
    assert.match(words(m.render()),/عملیات تأیید نشد/);
    assert.match(words(m.render()),/CAS v\s*0/);
  }
});

test('OBSERVED GAP: an arbitrary valid-shaped preverified prop can issue consent intent',async()=>{
  // A client can create a syntactically valid hint. UI cannot authenticate
  // its provenance. Existing Python host records intent, no paid dispatch.
  const calls=[];
  const forged={...consent,preverified:true};
  const m=harness({isAdmin:false,cloudConsent:forged,
    command:async(...args)=>{
      calls.push(args);
      return reply('cloud_consent','recorded');
    }});
  checkConsent(m);
  await btn(m.render(),'ثبت قصد رضایت').props.onClick();
  assert.equal(calls.length,1);
  assert.equal(calls[0][0],'cloud_consent');
});

test('static source has no host route, credential, outbound call, or prompt field',()=>{
  const sourceText=fs.readFileSync(source,'utf8');
  assert.doesNotMatch(sourceText,/\bfetch\s*\(|\bWebSocket\b|\bXMLHttpRequest\b/);
  assert.doesNotMatch(sourceText,/\b(localStorage|sessionStorage|indexedDB)\b/);
  assert.doesNotMatch(sourceText,/\bconsole\.(log|warn|error)\s*\(/);
  assert.doesNotMatch(sourceText,/\b(sendModel|mark_dispatched|reserve)\s*\(/);
  const html=renderToStaticMarkup(React.createElement(AiUsageAdminPanel,
    {...base,cloudConsent:consent}));
  assert.doesNotMatch(html,/PRIVATE SHOULD NOT RENDER|private@example.invalid|synthetic-key/);
  assert.doesNotMatch(html,/a{32}|b{64}/);
});
