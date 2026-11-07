'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');

let apiModule;
let MadarWebApiClient,WebApiError,toWebApiSnapshot;
test.before(async()=>{
  apiModule=await import('../src/web_api_client.mjs');
  ({MadarWebApiClient,WebApiError,toWebApiSnapshot}=apiModule);
});
const ORIGIN='https://madar.example';
const locationRef={origin:ORIGIN,href:ORIGIN+'/'};
const token='c'.repeat(40);
const user={username:'web-editor',workspaceId:'workspace-test',displayName:'ویرایشگر آزمایشی',role:'editor',projectIds:['p1']};

function response(status,payload,headers={},url=ORIGIN+'/api/web/v1/health'){
  const values={'content-type':'application/json; charset=utf-8',...headers};
  return {status,ok:status>=200&&status<300,url,
    headers:{get:name=>values[String(name).toLowerCase()]??null},
    json:async()=>payload};
}
function clientWith(responses){
  const calls=[];
  const client=new MadarWebApiClient({locationRef,fetchImpl:async(url,init)=>{
    calls.push({url,init});
    const next=responses.shift();
    if(typeof next==='function')return next(url,init);
    return next;
  }});
  return {client,calls};
}
const health=response(200,{service:'madar-web-api',contract:'madar-web-api-v1',
  apiVersion:1,stateSchemaVersion:1,status:'ready',features:{snapshotSync:true}});

test('API client accepts only a fixed same-origin path',()=>{
  assert.throws(()=>new MadarWebApiClient({locationRef,basePath:'https://evil.example/api'}),
    TypeError);
  assert.throws(()=>new MadarWebApiClient({locationRef:{
    origin:'http://madar.example',href:'http://madar.example/'}}),/HTTPS/);
  const {client}=clientWith([]);
  assert.throws(()=>client.endpoint('//evil.example/state'),WebApiError);
  assert.throws(()=>client.endpoint('/../other'),WebApiError);
});

test('API health must report database readiness, not only a live process',async()=>{
  const {client}=clientWith([response(200,{service:'madar-web-api',
    contract:'madar-web-api-v1',apiVersion:1,stateSchemaVersion:1,
    status:'starting',features:{snapshotSync:true}})]);
  await assert.rejects(()=>client.health(),error=>
    error instanceof WebApiError&&error.code==='unsupported_api_contract');
});

test('login uses same-origin cookie credentials and a CSRF token held only in memory',async()=>{
  const {client,calls}=clientWith([
    health,
    response(200,{csrfToken:token},{'set-cookie':'madar_web_csrf=opaque; Secure; HttpOnly; SameSite=Strict'}),
    response(200,{user,csrfToken:'d'.repeat(40)},
      {'set-cookie':'madar_web_session=secret; Secure; HttpOnly; SameSite=Lax'}),
  ]);
  const result=await client.login(' web-editor ','password-only-for-this-request');
  assert.equal(result.username,'web-editor');
  assert.equal(client.currentUser.role,'editor');
  assert.equal(client.csrfToken,'d'.repeat(40));
  assert.equal(calls.length,3);
  assert.equal(calls[2].init.credentials,'same-origin');
  assert.equal(calls[2].init.cache,'no-store');
  assert.equal(calls[2].init.headers['X-CSRF-Token'],token);
  assert.deepEqual(JSON.parse(calls[2].init.body),{
    username:'web-editor',password:'password-only-for-this-request'});
  assert.equal(calls.some(call=>call.url.includes('password-only-for-this-request')),false);
  assert.equal(calls.some(call=>JSON.stringify(call.init.headers).includes('Bearer')),false);
});

test('session expiry clears the in-memory user and CSRF token',async()=>{
  const {client}=clientWith([health,response(401,{error:'session_expired'})]);
  client.currentUser=user;client.csrfToken=token;
  assert.equal(await client.getSession(),null);
  assert.equal(client.currentUser,null);
  assert.equal(client.csrfToken,'');
});

test('first snapshot uses If-None-Match and strips finance/local path fields',async()=>{
  const {client,calls}=clientWith([response(201,{schemaVersion:1,revision:'rev-1',
    savedAt:'2026-11-06T12:00:00Z'},{etag:'"rev-1"'})]);
  client.csrfToken=token;
  const state={version:1,workspaces:[],boards:[],projects:[{id:'p1',name:'نمونه',
    price:123,costEnabled:true,fileLinks:['C:/private']}],stages:[],
    tasks:[{id:'t1',title:'کارت',cost:900,costDate:'2026-11-06',invoiceId:'inv-1',
      linkedFinanceIds:['f1'],fileLinks:['C:/private'],labels:[],reports:[],
      checklist:[{id:'s1',title:'مرحله',cost:20,expenseItems:[{amount:20}],done:false}]}],
    settings:{theme:'dark',costDefault:true,googleClientId:'12345.apps.googleusercontent.com'}};
  const original=JSON.stringify(state);
  const result=await client.writeState(state,null,'initial-create-1');
  assert.equal(result.revision,'rev-1');
  assert.equal(result.etag,'"rev-1"');
  const call=calls[0];
  assert.equal(call.init.headers['If-None-Match'],'*');
  assert.equal(call.init.headers['If-Match'],undefined);
  assert.equal(call.init.headers['Idempotency-Key'],'initial-create-1');
  assert.equal(call.init.headers['X-CSRF-Token'],token);
  const payload=JSON.parse(call.init.body);
  assert.equal(payload.state.projects[0].price,undefined);
  assert.equal(payload.state.projects[0].fileLinks,undefined);
  assert.equal(payload.state.tasks[0].cost,undefined);
  assert.equal(payload.state.tasks[0].invoiceId,undefined);
  assert.equal(payload.state.tasks[0].checklist[0].cost,undefined);
  assert.equal(payload.state.settings.costDefault,undefined);
  assert.equal(payload.state.settings.googleClientId,undefined);
  assert.equal(JSON.stringify(state),original,'API projection must not mutate local state');
});

test('existing snapshot uses strong If-Match and preserves idempotency key',async()=>{
  const {client,calls}=clientWith([response(200,{schemaVersion:1,revision:'rev-2',
    savedAt:'2026-11-06T12:01:00Z'},{etag:'"rev-2"'})]);
  client.csrfToken=token;
  const state={version:1,workspaces:[],boards:[],projects:[],tasks:[],stages:[],settings:{}};
  await client.writeState(state,{etag:'"rev-1"'},'retryable-job-77');
  assert.equal(calls[0].init.headers['If-Match'],'"rev-1"');
  assert.equal(calls[0].init.headers['If-None-Match'],undefined);
  assert.equal(calls[0].init.headers['Idempotency-Key'],'retryable-job-77');
});

test('missing remote state is distinct from an API route that is not installed',async()=>{
  const {client}=clientWith([response(404,{error:'state_not_initialized'})]);
  const missing=await client.readState();
  assert.deepEqual(missing,{exists:false,revision:null,etag:null});
  const unavailable=clientWith([{
    status:200,ok:true,url:ORIGIN+'/api/web/v1/health',
    headers:{get:()=> 'text/html'},json:async()=>({})}]);
  await assert.rejects(()=>unavailable.client.health(),error=>
    error instanceof WebApiError&&error.code==='api_not_installed');
});

test('valid remote state requires a strong ETag and web-safe projection',async()=>{
  const state={version:1,workspaces:[],boards:[],projects:[],tasks:[],stages:[],settings:{theme:'dark'}};
  const {client}=clientWith([response(200,{schemaVersion:1,exists:true,revision:'rev-4',
    state,updatedAt:'2026-11-06T12:00:00Z'},{etag:'"rev-4"'})]);
  const result=await client.readState();
  assert.equal(result.exists,true);
  assert.equal(result.revision,'rev-4');
  assert.equal(result.state.version,1);
});

test('weak ETags and missing CSRF fail closed',async()=>{
  const {client}=clientWith([response(200,{schemaVersion:1,revision:'rev-1',
    state:{version:1,workspaces:[],boards:[],projects:[],tasks:[],stages:[],settings:{}},
    updatedAt:'2026-11-06T12:00:00Z'},{etag:'W/"rev-1"'})]);
  await assert.rejects(()=>client.readState(),error=>
    error instanceof WebApiError&&error.code==='invalid_state_response');
  await assert.rejects(()=>client.writeState({
    version:1,workspaces:[],boards:[],projects:[],tasks:[],stages:[],settings:{}
  },null,'job-1'),error=>error.code==='csrf_token_missing');
});

test('409 revision conflict is returned as a typed API error',async()=>{
  const {client}=clientWith([response(409,{error:'revision_conflict',currentRevision:'rev-9'})]);
  client.csrfToken=token;
  await assert.rejects(()=>client.writeState({
    version:1,workspaces:[],boards:[],projects:[],tasks:[],stages:[],settings:{}
  },{etag:'"rev-8"'},'job-2'),error=>
    error instanceof WebApiError&&error.status===409&&error.code==='revision_conflict');
});

test('standalone projection keeps task UX fields and strips known local-only fields',()=>{
  const state={version:1,workspaces:[],boards:[],stages:[],projects:[{id:'p',name:'P',price:50}],
    tasks:[{id:'t',title:'T',description:'D',labels:['urgent'],cost:4,
      checklist:[{id:'c',title:'C',cost:2}]}],settings:{theme:'light',costDefault:true}};
  const result=toWebApiSnapshot(state);
  assert.equal(result.tasks[0].title,'T');
  assert.deepEqual(result.tasks[0].labels,['urgent']);
  assert.equal(result.tasks[0].cost,undefined);
  assert.equal(result.tasks[0].checklist[0].cost,undefined);
  assert.equal(result.projects[0].price,undefined);
  assert.equal(result.settings.costDefault,undefined);
});
