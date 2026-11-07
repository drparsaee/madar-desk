'use strict';

const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const net=require('node:net');
const {createApp}=require('../server/index.cjs');
const {createUser,resetPassword}=require('../server/storage.cjs');

const PREFIX='/api/web/v1';
function state(){
  const stage={id:'todo',label:'To do'};
  return {
    version:1,
    workspaces:[{id:'w1',name:'Team'}],
    projects:[{id:'p1',name:'First'},{id:'p2',name:'Second'}],
    boards:[
      {id:'b1',workspaceId:'w1',projectId:'p1',name:'First board',stages:[stage]},
      {id:'b2',workspaceId:'w1',projectId:'p2',name:'Second board',stages:[stage]}
    ],
    tasks:[
      {id:'t1',projectId:'p1',boardId:'b1',listId:'todo',status:'todo',
        title:'A card',checklist:[],labels:[]},
      {id:'t2',projectId:'p2',boardId:'b2',listId:'todo',status:'todo',
        title:'Private card',checklist:[],labels:[]}
    ],
    stages:[stage],settings:{theme:'dark',labelLibrary:[{id:'l1',name:'Urgent',color:'#ffaa00'}]}
  };
}
async function freePort(){
  // A Windows bind(0) can allocate ports in the 6000s. These restricted
  // Fetch/undici ports are unusable by the test's fetch client despite
  // being valid TCP listeners. Avoid them rather than masking API failures.
  const restricted=new Set([
    1,7,9,11,13,15,17,19,20,21,22,23,25,37,42,43,53,69,77,79,87,95,
    101,102,103,104,109,110,111,113,115,117,119,123,135,137,139,143,
    161,179,389,427,465,512,513,514,515,526,530,531,532,540,548,554,
    556,563,587,601,636,989,990,993,995,1719,1720,1723,2049,3659,
    4045,4190,5060,5061,6000,6566,6665,6666,6667,6668,6669,6679,6697,10080
  ]);
  for(let attempt=0;attempt<12;attempt++){
    const sock=net.createServer();
    await new Promise((resolve,reject)=>sock.once('error',reject).listen(0,'127.0.0.1',resolve));
    const port=sock.address().port;
    await new Promise(resolve=>sock.close(resolve));
    if(!restricted.has(port))return port;
  }
  throw Error('Unable to choose a safe HTTP test port.');
}
async function fixture(t){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'madar-api-test-'));
  const dbPath=path.join(dir,'private.sqlite');
  const port=await freePort();
  const origin='http://127.0.0.1:'+port;
  const app=createApp({dbPath,publicOrigin:origin});
  createUser(app.db,{username:'admin',password:'very-secure-test-password',role:'admin',
    workspaceId:'team'});
  createUser(app.db,{username:'editor',password:'very-secure-test-password',role:'editor',
    workspaceId:'team',projectIds:['p1']});
  createUser(app.db,{username:'viewer',password:'very-secure-test-password',role:'viewer',
    workspaceId:'team',projectIds:['p1']});
  await new Promise((resolve,reject)=>app.server.once('error',reject).listen(port,'127.0.0.1',resolve));
  t.after(async()=>{
    await app.close();
    fs.rmSync(dir,{recursive:true,force:true});
  });
  return {app,dbPath,origin};
}
function client(origin){
  const jar=new Map();
  return {
    jar,
    async call(method,pathname,body,headers={}){
      const all={
        Accept:'application/json',
        ...(jar.size?{Cookie:[...jar.entries()].map(([k,v])=>k+'='+v).join('; ')}:{}),
        ...(method==='GET'?{}:{Origin:origin,'Sec-Fetch-Site':'same-origin'}),
        ...(body===undefined?{}:{'Content-Type':'application/json'}),
        ...headers
      };
      const res=await fetch(origin+PREFIX+pathname,{
        method,headers:all,redirect:'manual',body:body===undefined?undefined:JSON.stringify(body)});
      const cookies=res.headers.getSetCookie();
      for(const header of cookies){
        const pair=header.split(';')[0],index=pair.indexOf('=');
        if(index<0)continue;
        const key=pair.slice(0,index),value=pair.slice(index+1);
        if(value)jar.set(key,value);else jar.delete(key);
      }
      const payload=res.status===204?null:await res.json();
      return {status:res.status,payload,headers:res.headers,cookies};
    },
    async login(name='admin',password='very-secure-test-password'){
      const csrf=await this.call('GET','/csrf');
      assert.equal(csrf.status,200);
      const response=await this.call('POST','/session',{username:name,password},
        {'X-CSRF-Token':csrf.payload.csrfToken});
      if(response.status===200) this.csrf=response.payload.csrfToken;
      return response;
    },
    async put(snapshot,etag,key='save-1'){
      return this.call('PUT','/state',{schemaVersion:1,state:snapshot},
        {'X-CSRF-Token':this.csrf,'Idempotency-Key':key,
          ...(etag?{'If-Match':etag}:{'If-None-Match':'*'})});
    }
  };
}

test('independent card/project conversations enforce ACL, reply integrity and durable idempotency',async t=>{
  const {origin,app}=await fixture(t);
  const admin=client(origin),editor=client(origin),viewer=client(origin);
  assert.equal((await admin.login()).status,200);
  assert.equal((await admin.put(state(),null,'bootstrap-conversations')).status,201);
  assert.equal((await editor.login('editor')).status,200);
  assert.equal((await viewer.login('viewer')).status,200);
  const cardPath='/conversations/card/t1',projectPath='/conversations/project/p1';
  assert.deepEqual((await editor.call('GET',cardPath)).payload.items,[]);
  const send=(c,path,body,key)=>c.call('POST',path+'/messages',body,
    {'X-CSRF-Token':c.csrf,'Idempotency-Key':key});
  const comment=await send(editor,cardPath,{text:'سلام',replyToId:''},'card-message-1');
  assert.equal(comment.status,201,JSON.stringify(comment.payload));
  const duplicate=await send(editor,cardPath,{text:'سلام',replyToId:''},'card-message-1');
  assert.equal(duplicate.payload.messageId,comment.payload.messageId);
  assert.equal((await send(editor,cardPath,{text:'دیگر',replyToId:''},'card-message-1')).status,409);
  const got=await viewer.call('GET',cardPath);
  assert.equal(got.payload.items.length,1);
  assert.equal(got.payload.items[0].author,'editor');
  assert.equal(got.payload.items[0].text,'سلام');
  const reply=await send(editor,cardPath,{text:'پاسخ',replyToId:comment.payload.messageId},'reply-1');
  assert.equal(reply.status,201);
  assert.equal((await send(editor,projectPath,{text:'پیام پروژه',replyToId:comment.payload.messageId},'bad-reply')).status,422);
  assert.equal((await send(editor,projectPath,{text:'پیام پروژه',replyToId:''},'project-1')).status,201);
  assert.equal((await viewer.call('GET',projectPath)).payload.items.length,1);
  assert.equal((await viewer.call('GET','/conversations/project/p2')).status,403);
  assert.equal((await viewer.call('GET','/conversations/card/t2')).status,403);
  assert.equal((await send(viewer,cardPath,{text:'رد',replyToId:''},'denied')).status,403);
  const edit=await viewer.call('PUT','/messages/'+comment.payload.messageId,
    {text:'غیرمجاز'},{'X-CSRF-Token':viewer.csrf,'Idempotency-Key':'illegal-edit'});
  assert.equal(edit.status,403);
  const validEdit=await editor.call('PUT','/messages/'+comment.payload.messageId,
    {text:'ویرایش شد'},{'X-CSRF-Token':editor.csrf,'Idempotency-Key':'edit-1'});
  assert.equal(validEdit.status,200);
  const removed=await admin.call('DELETE','/messages/'+comment.payload.messageId,{},
    {'X-CSRF-Token':admin.csrf,'Idempotency-Key':'delete-1'});
  assert.equal(removed.status,200);
  const after=(await viewer.call('GET',cardPath)).payload.items;
  assert.equal(after[0].text,'');
  assert.ok(after[0].deletedAt);
  assert.equal(after[1].replyToId,comment.payload.messageId);
  assert.equal(app.db.prepare('SELECT COUNT(*) AS n FROM web_conversation_messages').get().n,3);
  assert.equal(app.db.prepare('PRAGMA user_version').get().user_version,3);
  const history=app.db.prepare(`SELECT prior_revision,prior_body,action
    FROM web_conversation_revisions WHERE message_id=? ORDER BY prior_revision`)
    .all(comment.payload.messageId).map(row=>({...row}));
  assert.deepEqual(history,[
    {prior_revision:1,prior_body:'سلام',action:'edit'},
    {prior_revision:2,prior_body:'ویرایش شد',action:'delete'}
  ],'edits and deletion retain historical text in server-only audit storage');
});

test('moving a card between projects cannot expose or mutate old-project conversation history',async t=>{
  const {origin,app}=await fixture(t);
  const admin=client(origin),editor=client(origin);
  assert.equal((await admin.login()).status,200);
  assert.equal((await editor.login('editor')).status,200);
  const initial=await admin.put(state(),null,'move-initial');
  assert.equal(initial.status,201);
  const card='/conversations/card/t1';
  const body={text:'old private project',replyToId:''};
  const sent=await editor.call('POST',card+'/messages',body,
    {'X-CSRF-Token':editor.csrf,'Idempotency-Key':'old-project-msg'});
  assert.equal(sent.status,201);
  const moved=state();moved.tasks[0].projectId='p2';moved.tasks[0].boardId='b2';
  const saved=await admin.put(moved,initial.headers.get('etag'),'move-card');
  assert.equal(saved.status,200);
  assert.deepEqual((await admin.call('GET',card)).payload.items,[],
    'message history must not be silently re-parented to the new project');
  assert.equal((await editor.call('GET',card)).status,403);
  assert.equal((await editor.call('POST',card+'/messages',body,
    {'X-CSRF-Token':editor.csrf,'Idempotency-Key':'old-project-msg'})).status,403);
  const edit=await admin.call('DELETE','/messages/'+sent.payload.messageId,{},
    {'X-CSRF-Token':admin.csrf,'Idempotency-Key':'wrong-project-delete'});
  assert.equal(edit.status,403);
  assert.equal(app.db.prepare('SELECT project_id FROM web_conversation_messages WHERE id=?')
    .get(sent.payload.messageId).project_id,'p1','old conversation row stays retained');
  const newMessage=await admin.call('POST',card+'/messages',{text:'current project',replyToId:''},
    {'X-CSRF-Token':admin.csrf,'Idempotency-Key':'new-project-msg'});
  assert.equal(newMessage.status,201);
  assert.equal((await admin.call('GET',card)).payload.items[0].text,'current project');
});

test('health, real login, session cookie, CSRF, Origin, Fetch Metadata, logout',async t=>{
  const {origin}=await fixture(t),c=client(origin);
  const health=await c.call('GET','/health');
  assert.deepEqual({service:health.payload.service,contract:health.payload.contract,
    apiVersion:health.payload.apiVersion,stateSchemaVersion:health.payload.stateSchemaVersion,
    status:health.payload.status,features:health.payload.features},
  {service:'madar-web-api',contract:'madar-web-api-v1',apiVersion:1,
    stateSchemaVersion:1,status:'ready',features:{snapshotSync:true}});
  const csrf=await c.call('GET','/csrf');
  assert.match(csrf.cookies[0],/HttpOnly; SameSite=Strict/);
  const missingOrigin=await c.call('POST','/session',
    {username:'admin',password:'very-secure-test-password'},
    {Origin:'https://attacker.example','X-CSRF-Token':csrf.payload.csrfToken});
  assert.equal(missingOrigin.status,403);
  assert.equal(missingOrigin.payload.error,'origin_rejected');
  const crossSite=await c.call('POST','/session',
    {username:'admin',password:'very-secure-test-password'},
    {'Sec-Fetch-Site':'cross-site','X-CSRF-Token':csrf.payload.csrfToken});
  assert.equal(crossSite.status,403);
  const csrfBad=await c.call('POST','/session',
    {username:'admin',password:'very-secure-test-password'},
    {'X-CSRF-Token':'incorrect'});
  assert.equal(csrfBad.status,403);
  const login=await c.login();
  assert.equal(login.status,200);
  assert.equal(login.payload.user.workspaceId,'team');
  assert.equal(login.payload.user.role,'admin');
  assert.ok(login.cookies.some(x=>/madar_web_session=/.test(x)&&/HttpOnly; SameSite=Lax/.test(x)));
  assert.ok(login.cookies.some(x=>/madar_web_csrf=/.test(x)&&/HttpOnly; SameSite=Strict/.test(x)));
  assert.equal(login.cookies.some(x=>x.includes('Domain=')),false);
  assert.equal(login.cookies.some(x=>x.includes('; Secure')),false,'loopback HTTP development exemption');
  const check=await c.call('GET','/session');
  assert.equal(check.payload.authenticated,true);
  c.csrf=check.payload.csrfToken;
  const logout=await c.call('DELETE','/session',undefined,{'X-CSRF-Token':c.csrf});
  assert.equal(logout.status,204);
  assert.equal((await c.call('GET','/session')).status,401);
  assert.equal((await c.call('POST','/signup',{})).status,404);
});

test('SQLite conditional writes, durable receipt, stale conflict and exact replay',async t=>{
  const {app,origin}=await fixture(t),c=client(origin);
  assert.equal((await c.login()).status,200);
  assert.equal((await c.call('GET','/state')).payload.error,'state_not_initialized');
  const missing=await c.call('PUT','/state',{schemaVersion:1,state:state()},
    {'X-CSRF-Token':c.csrf,'Idempotency-Key':'first'});
  assert.equal(missing.status,428);
  const first=await c.put(state(),null,'first');
  assert.equal(first.status,201);
  assert.ok(first.headers.get('etag').startsWith('"'));
  const replay=await c.put(state(),null,'first');
  assert.equal(replay.status,201);
  assert.deepEqual(replay.payload,first.payload);
  assert.equal(replay.headers.get('etag'),first.headers.get('etag'));
  const changed=state();changed.tasks[0].title='Changed';
  const keyConflict=await c.put(changed,null,'first');
  assert.equal(keyConflict.status,409);
  assert.equal(keyConflict.payload.error,'idempotency_key_conflict');
  const stale=await c.put(changed,'W/"weak"','different');
  assert.equal(stale.status,400,'malformed precondition is rejected');
  const staleValid=await c.put(changed,'"unmatched"','stale');
  assert.equal(staleValid.status,409);
  assert.equal(staleValid.payload.currentRevision,first.payload.revision);
  const current=await c.call('GET','/state');
  assert.equal(current.status,200);
  assert.equal(current.payload.state.tasks[0].title,'A card');
  const second=await c.put(changed,first.headers.get('etag'),'second');
  assert.equal(second.status,200);
  assert.equal(app.db.prepare('SELECT count(*) c FROM web_idempotency').get().c,2);
  assert.equal(app.db.prepare('SELECT count(*) c FROM web_audit_events').get().c,2);
  assert.equal(app.db.prepare('SELECT count(*) c FROM web_workspace_snapshots').get().c,2);
  assert.equal((await c.call('GET','/state')).payload.state.tasks[0].title,'Changed');
});

test('server-owned roles, project grant, hidden records and finance denial',async t=>{
  const {app,origin}=await fixture(t),admin=client(origin),editor=client(origin),viewer=client(origin);
  await admin.login();
  const seeded=state();
  seeded.tasks[0].reports=[{id:'report-1',agent:'Madar',summary:'Progress is on track',
    createdAt:'2026-11-06T12:00:00Z'}];
  seeded.tasks[0].cover={type:'color',color:'#aabbcc',size:'full'};
  seeded.tasks[0].customFieldValues={};
  // Cross-project dependency references are invalid. A permitted editor
  // must never receive or preserve IDs from an unrelated project.
  seeded.tasks[0].dependencies=[];
  const initial=await admin.put(seeded,null,'init');
  assert.equal(initial.status,201);
  await editor.login('editor');
  await viewer.login('viewer');
  const read=await editor.call('GET','/state');
  assert.deepEqual(read.payload.state.projects.map(x=>x.id),['p1']);
  assert.deepEqual(read.payload.state.tasks.map(x=>x.id),['t1']);
  assert.deepEqual(read.payload.state.tasks[0].dependencies,[],
    'no cross-project dependency identifiers appear in scoped GET');
  assert.equal(read.payload.state.tasks[0].reports[0].summary,'Progress is on track');
  assert.equal(read.payload.state.tasks[0].cover.color,'#aabbcc');
  assert.equal(read.payload.user,undefined);
  assert.equal((await viewer.call('GET','/state')).payload.state.tasks.length,1);
  const blocked=await viewer.put(read.payload.state,read.headers.get('etag'),'viewer');
  assert.equal(blocked.status,403);
  const wrong=structuredClone(read.payload.state);wrong.projects[0].name='Escalated';
  assert.equal((await editor.put(wrong,read.headers.get('etag'),'structure')).status,403);
  const tamper=structuredClone(read.payload.state);tamper.tasks[0].projectId='p2';
  assert.equal((await editor.put(tamper,read.headers.get('etag'),'scope')).status,422);
  const next=structuredClone(read.payload.state);next.tasks[0].title='Edited by editor';
  const update=await editor.put(next,read.headers.get('etag'),'editor-valid');
  assert.equal(update.status,200);
  const full=await admin.call('GET','/state');
  assert.deepEqual(full.payload.state.tasks.map(x=>x.title),
    ['Edited by editor','Private card']);
  assert.deepEqual(full.payload.state.tasks[0].dependencies,[],
    'editor update does not introduce inaccessible project IDs');
  assert.equal(full.payload.state.tasks[0].reports.length,1,
    'server persists only allowlisted report fields');
  const withCost=structuredClone(full.payload.state);withCost.tasks[0].cost=999999;
  assert.equal((await admin.put(withCost,full.headers.get('etag'),'finance')).status,422);
  const withPath=structuredClone(full.payload.state);withPath.tasks[0].description='C:\\secret\\data';
  assert.equal((await admin.put(withPath,full.headers.get('etag'),'path')).status,422);
  const broken=structuredClone(full.payload.state);broken.projects=[];
  assert.equal((await admin.put(broken,full.headers.get('etag'),'orphan')).status,422);
  assert.equal(app.db.prepare('SELECT count(*) c FROM web_workspace_snapshots').get().c,2);
});

test('two concurrent devices conflict and transaction rollback is atomic',async t=>{
  const {app,origin}=await fixture(t),one=client(origin),two=client(origin);
  await one.login();await two.login();
  const initial=await one.put(state(),null,'init');
  assert.equal(initial.status,201);
  const a=state(),b=state();
  a.tasks[0].title='Device A';b.tasks[0].title='Device B';
  const [r1,r2]=await Promise.all([
    one.put(a,initial.headers.get('etag'),'device-a'),
    two.put(b,initial.headers.get('etag'),'device-b')
  ]);
  assert.deepEqual([r1.status,r2.status].sort(),[200,409]);
  const current=await one.call('GET','/state');
  assert.ok(['Device A','Device B'].includes(current.payload.state.tasks[0].title));
  const later=structuredClone(current.payload.state);later.tasks[0].title='After rollback';
  app.db.exec(`CREATE TRIGGER fail_audit BEFORE INSERT ON web_audit_events
    BEGIN SELECT RAISE(ABORT,'test audit rollback'); END`);
  const failed=await one.put(later,current.headers.get('etag'),'will-rollback');
  assert.equal(failed.status,500);
  assert.equal(app.db.prepare('SELECT count(*) c FROM web_workspace_heads').get().c,1);
  assert.equal(app.db.prepare('SELECT count(*) c FROM web_workspace_snapshots').get().c,2);
  assert.equal(app.db.prepare('SELECT count(*) c FROM web_idempotency').get().c,2);
  assert.equal((await one.call('GET','/state')).payload.state.tasks[0].title,
    current.payload.state.tasks[0].title);
  app.db.exec('DROP TRIGGER fail_audit');
  assert.equal((await one.put(later,current.headers.get('etag'),'will-rollback')).status,200);
});

test('password rotation revokes server sessions and bad password is denied',async t=>{
  const {app,origin}=await fixture(t),c=client(origin);
  assert.equal((await c.login('admin','incorrect-password')).status,401);
  assert.equal((await c.login()).status,200);
  resetPassword(app.db,'admin','new-very-secure-test-password');
  assert.equal((await c.call('GET','/session')).status,401);
  assert.equal((await c.login('admin','very-secure-test-password')).status,401);
  assert.equal((await c.login('admin','new-very-secure-test-password')).status,200);
});

test('login throttle, unsupported report fields and session expiry fail closed',async t=>{
  const {app,origin}=await fixture(t),c=client(origin);
  for(let i=0;i<5;i++)
    assert.equal((await c.login('admin','wrong-password')).status,401);
  assert.equal((await c.login('admin','wrong-password')).status,429);
  const limited=client(origin);
  assert.equal((await limited.login()).status,429);
  const expiry=client(origin);
  // Isolate expiry checks with a separately provisioned workspace account and
  // resetting the temporary local throttling table.
  app.db.prepare('DELETE FROM web_login_limits').run();
  assert.equal((await expiry.login()).status,200);
  const remote=await expiry.put(state(),null,'first');
  assert.equal(remote.status,201);
  const bad=state();
  bad.tasks[0].reports=[{id:'r1',agent:'X',summary:'safe',financeSourceId:'secret'}];
  const rejected=await expiry.put(bad,remote.headers.get('etag'),'bad-report');
  assert.equal(rejected.status,422);
  const token=expiry.jar.get('madar_web_session');
  app.db.prepare('UPDATE web_sessions SET last_seen_at=? WHERE token_hash=?')
    .run(Date.now()-31*60*1000,require('../server/storage.cjs').hashToken(token));
  assert.equal((await expiry.call('GET','/state')).status,401);
});

test('independent SQLite connection reads real committed state and revision',async t=>{
  const {dbPath,origin}=await fixture(t),first=client(origin);
  await first.login();
  const saved=await first.put(state(),null,'init');
  assert.equal(saved.status,201);
  const {openDatabase}=require('../server/storage.cjs');
  const otherDb=openDatabase(dbPath);
  try{
    const head=otherDb.prepare('SELECT revision,state_json FROM web_workspace_heads WHERE workspace_id=?')
      .get('team');
    assert.equal(head.revision,saved.payload.revision);
    assert.equal(JSON.parse(head.state_json).tasks[0].title,'A card');
    const changed=state();changed.tasks[0].title='Changed after reopening';
    assert.equal((await first.put(changed,saved.headers.get('etag'),'second')).status,200);
    const headAfter=otherDb.prepare('SELECT revision,state_json FROM web_workspace_heads WHERE workspace_id=?')
      .get('team');
    assert.notEqual(headAfter.revision,head.revision);
    assert.equal(JSON.parse(headAfter.state_json).tasks[0].title,'Changed after reopening');
  }finally{otherDb.close();}
});
