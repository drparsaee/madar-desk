'use strict';

const http=require('node:http');
const crypto=require('node:crypto');
const {
  openDatabase,transact,passwordHash,passwordValid,hashToken,randomToken,utcNow,etagFor,canonical
}=require('./storage.cjs');
const {ValidationError,validateSnapshot,projectSnapshot,mergeEditor}=require('./policy.cjs');
const {ConversationError,listMessages,messageAction}=require('./conversations.cjs');
const {GanttShiftError,prepareGanttShift}=require('./gantt_shift_guard.cjs');

const PREFIX='/api/web/v1';
const SESSION_COOKIE='madar_web_session';
const CSRF_COOKIE='madar_web_csrf';
const BODY_LIMIT=16*1024*1024;
const IDLE_MS=30*60*1000;
const ABSOLUTE_MS=12*60*60*1000;
const IDEM_DAYS=90;
const IDEM_RE=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/;
const timingEqual=(left,right)=>{
  if(typeof left!=='string'||typeof right!=='string')return false;
  const a=Buffer.from(left),b=Buffer.from(right);
  return a.length===b.length&&crypto.timingSafeEqual(a,b);
};
class HttpError extends Error{
  constructor(status,code,message=code,details={}){
    super(message);this.status=status;this.code=code;this.details=details;
  }
}
function cookies(header){
  const result=Object.create(null);
  for(const part of String(header||'').split(';')){
    const at=part.indexOf('=');
    if(at>0)result[part.slice(0,at).trim()]=part.slice(at+1).trim();
  }
  return result;
}
function cookie(name,value,sameSite,maxAge,secure){
  return name+'='+value+'; Path='+PREFIX+'; Max-Age='+maxAge+
    '; HttpOnly; SameSite='+sameSite+(secure?'; Secure':'');
}
function response(res,status,body,headers={}){
  res.statusCode=status;
  for(const [name,value] of Object.entries(headers))res.setHeader(name,value);
  if(status===204){res.end();return;}
  res.setHeader('Content-Type','application/json; charset=utf-8');
  res.end(JSON.stringify(body));
}
function reject(status,code,message=code,details={}){
  throw new HttpError(status,code,message,details);
}
function jsonInput(req) {
  const type=req.headers['content-type'];
  if(typeof type!=='string'||!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(type))
    reject(415,'unsupported_media_type');
  const declared=Number(req.headers['content-length']||0);
  if(!Number.isFinite(declared)||declared<0||declared>BODY_LIMIT)
    reject(413,'payload_too_large');
  return new Promise((resolve,rejectPromise)=>{
    const chunks=[];let total=0;let finished=false;
    req.on('data',part=>{
      if(finished)return;
      total+=part.length;
      if(total>BODY_LIMIT){
        finished=true;req.pause();rejectPromise(new HttpError(413,'payload_too_large'));return;
      }
      chunks.push(part);
    });
    req.on('end',()=>{
      if(finished)return;finished=true;
      try {resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));}
      catch{rejectPromise(new HttpError(400,'invalid_json'));}
    });
    req.on('error',error=>{if(!finished){finished=true;rejectPromise(error);}});
    req.on('aborted',()=>{if(!finished){finished=true;rejectPromise(new HttpError(400,'request_aborted'));}});
  });
}
function publicAccount(user){
  return {username:user.username,displayName:user.display_name,role:user.role,
    workspaceId:user.workspace_id,
    projectIds:user.project_ids_json===null?null:JSON.parse(user.project_ids_json)};
}
function createApp({dbPath,publicOrigin,host='127.0.0.1'}={}){
  if(typeof publicOrigin!=='string')throw Error('MADAR_WEB_PUBLIC_ORIGIN is required.');
  const parsed=new URL(publicOrigin);
  const local=['127.0.0.1','localhost','[::1]'].includes(parsed.hostname);
  if(parsed.origin!==publicOrigin||parsed.username||parsed.password||
     (parsed.protocol!=='https:'&&!(parsed.protocol==='http:'&&local)))
    throw Error('Public origin must be exact HTTPS, except for loopback HTTP.');
  if(!['127.0.0.1','::1','localhost'].includes(host))
    throw Error('Bind the plain HTTP backend to loopback behind an HTTPS reverse proxy.');
  const secure=parsed.protocol==='https:';
  const db=openDatabase(dbPath);
  const csrfKey=crypto.randomBytes(32);
  const dummyHash=passwordHash(randomToken());
  const signedCsrf=()=>{
    const value=randomToken();
    return value+'.'+crypto.createHmac('sha256',csrfKey).update(value).digest('base64url');
  };
  const validPreAuth=token=>{
    if(typeof token!=='string')return false;
    const pos=token.indexOf('.');
    if(pos<0)return false;
    const expected=crypto.createHmac('sha256',csrfKey).update(token.slice(0,pos)).digest('base64url');
    return timingEqual(expected,token.slice(pos+1));
  };
  const csrfCookies=(token,age=1800)=>cookie(CSRF_COOKIE,token,'Strict',age,secure);
  const sessionCookies=(token,age=1800)=>cookie(SESSION_COOKIE,token,'Lax',age,secure);
  const cleanCookies=()=>[sessionCookies('',0),csrfCookies('',0)];

  function lookupSession(jar){
    const token=jar[SESSION_COOKIE];
    if(!token||token.length>256)return null;
    const row=db.prepare(`SELECT s.*,u.username,u.display_name,u.role,u.workspace_id,
      u.project_ids_json,u.enabled FROM web_sessions s
      JOIN web_users u ON u.id=s.user_id WHERE s.token_hash=?`).get(hashToken(token));
    const now=Date.now();
    if(!row)return null;
    if(!row.enabled||now>=row.expires_at||now-row.last_seen_at>=IDLE_MS){
      db.prepare('DELETE FROM web_sessions WHERE token_hash=?').run(row.token_hash);
      return null;
    }
    return row;
  }
  function requireSession(jar){
    const session=lookupSession(jar);
    if(!session)reject(401,'session_expired');
    db.prepare('UPDATE web_sessions SET last_seen_at=? WHERE token_hash=?')
      .run(Date.now(),session.token_hash);
    return session;
  }
  function checkOrigin(req){
    if(req.headers.origin!==publicOrigin)reject(403,'origin_rejected');
    const fetchSite=req.headers['sec-fetch-site'];
    if(fetchSite!=='same-origin'&&fetchSite!=='same-site')
      reject(403,'fetch_metadata_rejected');
    if(req.headers['sec-fetch-mode']==='navigate')
      reject(403,'fetch_metadata_rejected');
  }
  function checkCsrf(req,jar,session){
    const header=req.headers['x-csrf-token'];
    const stored=jar[CSRF_COOKIE];
    if(!timingEqual(header,stored)||!stored||stored.length>512)
      reject(403,'csrf_failed');
    if(session && !timingEqual(hashToken(stored),session.csrf_hash))
      reject(403,'csrf_failed');
    if(!session && !validPreAuth(stored))reject(403,'csrf_failed');
  }
  function rotateCsrf(session){
    const token=randomToken();
    db.prepare('UPDATE web_sessions SET csrf_hash=? WHERE token_hash=?')
      .run(hashToken(token),session.token_hash);
    return token;
  }
  function loginBucket(identity){return hashToken(identity.toLowerCase());}
  function denyIfLimited(bucket) {
    const record=db.prepare('SELECT next_allowed_at FROM web_login_limits WHERE bucket_hash=?').get(bucket);
    if(record && Date.now()<record.next_allowed_at)reject(429,'login_rate_limited');
  }
  function failedLogin(buckets){
    const at=Date.now();
    for(const bucket of buckets){
      const previous=db.prepare('SELECT failures,last_at FROM web_login_limits WHERE bucket_hash=?').get(bucket);
      const failures=previous&&at-previous.last_at<24*60*60*1000?previous.failures+1:1;
      const delay=failures<5?0:Math.min(60*60*1000,2000*(2**Math.min(11,failures-5)));
      db.prepare(`INSERT INTO web_login_limits(bucket_hash,failures,next_allowed_at,last_at)
        VALUES(?,?,?,?) ON CONFLICT(bucket_hash) DO UPDATE SET
        failures=excluded.failures,next_allowed_at=excluded.next_allowed_at,
        last_at=excluded.last_at`).run(bucket,failures,at+delay,at);
    }
  }

  async function handle(req,res){
    res.setHeader('Cache-Control','no-store');
    res.setHeader('X-Content-Type-Options','nosniff');
    res.setHeader('Referrer-Policy','no-referrer');
    res.setHeader('X-Frame-Options','DENY');
    res.setHeader('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'; base-uri 'none'");
    res.setHeader('Vary','Origin, Sec-Fetch-Site');
    if(secure)res.setHeader('Strict-Transport-Security','max-age=63072000; includeSubDomains');
    try {
      if(!req.url||req.url.includes('?')||req.url.includes('#'))
        reject(400,'invalid_api_path');
      if(!req.url.startsWith(PREFIX+'/'))reject(404,'not_found');
      const pathname=req.url.slice(PREFIX.length);
      const method=req.method;
      const jar=cookies(req.headers.cookie);
      if(method==='GET'&&pathname==='/health'){
        db.prepare('SELECT 1 AS ready').get();
        response(res,200,{service:'madar-web-api',contract:'madar-web-api-v1',
          apiVersion:1,stateSchemaVersion:1,status:'ready',
          features:{snapshotSync:true}});return;
      }
      if(method==='GET'&&pathname==='/csrf'){
        if(req.headers['sec-fetch-site']==='cross-site')reject(403,'fetch_metadata_rejected');
        const session=lookupSession(jar);
        const token=session?rotateCsrf(session):signedCsrf();
        response(res,200,{csrfToken:token},{'Set-Cookie':csrfCookies(token)});return;
      }
      if(method==='POST'&&pathname==='/session'){
        checkOrigin(req);checkCsrf(req,jar,null);
        const body=await jsonInput(req);
        if(!body||typeof body!=='object'||Array.isArray(body)||
           Object.keys(body).some(k=>!['username','password'].includes(k))||
           typeof body.username!=='string'||body.username.length>128||!body.username.trim()||
           typeof body.password!=='string'||!body.password||body.password.length>1024)
          reject(400,'invalid_credentials_input');
        const username=body.username.trim();
        const ip=String(req.socket.remoteAddress||'unknown');
        const buckets=[loginBucket('ip:'+ip),loginBucket('account:'+username+':'+ip)];
        buckets.forEach(denyIfLimited);
        const account=db.prepare('SELECT * FROM web_users WHERE username=?').get(username);
        // Keep the expensive password check for an unknown/disabled account too.
        const accepted=passwordValid(body.password,account?.password_hash||dummyHash);
        if(!accepted||!account?.enabled){
          failedLogin(buckets);reject(401,'invalid_credentials');
        }
        db.prepare('DELETE FROM web_login_limits WHERE bucket_hash=?').run(buckets[1]);
        const current=lookupSession(jar),secret=randomToken(),csrf=randomToken();
        const now=Date.now();
        transact(db,()=>{
          if(current)db.prepare('DELETE FROM web_sessions WHERE token_hash=?').run(current.token_hash);
          db.prepare(`INSERT INTO web_sessions
            (token_hash,user_id,csrf_hash,created_at,last_seen_at,expires_at)
            VALUES(?,?,?,?,?,?)`).run(hashToken(secret),account.id,hashToken(csrf),now,now,now+ABSOLUTE_MS);
        });
        response(res,200,{user:publicAccount(account),csrfToken:csrf},{
          'Set-Cookie':[sessionCookies(secret,Math.floor(ABSOLUTE_MS/1000)),csrfCookies(csrf,Math.floor(ABSOLUTE_MS/1000))]});
        return;
      }
      if(method==='GET'&&pathname==='/session'){
        const session=requireSession(jar);
        // Keep the existing token on frequent status polls. Rotating on every
        // GET invalidates pending writes from another tab.
        const existing=jar[CSRF_COOKIE];
        const valid=typeof existing==='string'&&timingEqual(hashToken(existing),session.csrf_hash);
        const token=valid?existing:rotateCsrf(session);
        response(res,200,{authenticated:true,user:publicAccount(session),csrfToken:token},
          {'Set-Cookie':csrfCookies(token,Math.floor(ABSOLUTE_MS/1000))});return;
      }
      if(method==='DELETE'&&pathname==='/session'){
        checkOrigin(req);
        const session=requireSession(jar);checkCsrf(req,jar,session);
        db.prepare('DELETE FROM web_sessions WHERE token_hash=?').run(session.token_hash);
        response(res,204,null,{'Set-Cookie':cleanCookies()});return;
      }
      const conversation=/^\/conversations\/(card|project)\/([A-Za-z0-9_.:-]{1,128})(\/messages)?$/.exec(pathname);
      if(conversation&&(method==='GET'&&!conversation[3]||method==='POST'&&conversation[3])){
        const session=requireSession(jar);
        if(method==='GET'){
          response(res,200,listMessages(db,session,conversation[1],conversation[2]));return;
        }
        checkOrigin(req);checkCsrf(req,jar,session);
        const input=await jsonInput(req);
        const result=messageAction(db,session,{method,scope:conversation[1],
          target:conversation[2],payload:input,key:req.headers['idempotency-key']});
        response(res,201,result);return;
      }
      const message=/^\/messages\/([A-Za-z0-9_.:-]{1,128})$/.exec(pathname);
      if(message&&(method==='PUT'||method==='DELETE')){
        const session=requireSession(jar);
        checkOrigin(req);checkCsrf(req,jar,session);
        const input=await jsonInput(req);
        response(res,200,messageAction(db,session,{method,messageId:message[1],
          payload:input,key:req.headers['idempotency-key']}));return;
      }
      if(method==='POST'&&pathname==='/gantt/shift/preview'){
        checkOrigin(req);
        const session=requireSession(jar);checkCsrf(req,jar,session);
        if(session.role==='viewer')reject(403,'insufficient_permissions');
        const request=await jsonInput(req);
        const head=db.prepare('SELECT revision,state_json FROM web_workspace_heads WHERE workspace_id=?')
          .get(session.workspace_id);
        if(!head)reject(404,'state_not_initialized');
        try {
          // Full host state (never the filtered UI projection). Preview is
          // read-only; transaction-bound revalidation is mandatory for commit.
          const result=prepareGanttShift(JSON.parse(head.state_json),request,{
            role:session.role,
            projects:session.project_ids_json===null?null:JSON.parse(session.project_ids_json),
            actualRevision:head.revision
          });
          response(res,200,{schemaVersion:1,readOnly:true,revision:head.revision,
            scope:result.scope,changedCount:result.changedCount,updates:result.updates},
          {ETag:etagFor(head.revision)});return;
        }catch(error){
          if(!(error instanceof GanttShiftError))throw error;
          if(error.code==='stale_revision')reject(409,'revision_conflict');
          if(error.code==='forbidden'||error.code==='unavailable_target')
            reject(404,'gantt_preview_unavailable');
          reject(422,'gantt_preview_unavailable');
        }
      }
      if(method==='GET'&&pathname==='/state'){
        const session=requireSession(jar);
        const head=db.prepare('SELECT * FROM web_workspace_heads WHERE workspace_id=?')
          .get(session.workspace_id);
        if(!head)reject(404,'state_not_initialized');
        const state=projectSnapshot(JSON.parse(head.state_json),session);
        response(res,200,{schemaVersion:1,exists:true,revision:head.revision,
          state,updatedAt:head.updated_at},{ETag:etagFor(head.revision)});return;
      }
      if(method==='PUT'&&pathname==='/state'){
        checkOrigin(req);
        const session=requireSession(jar);checkCsrf(req,jar,session);
        if(session.role==='viewer')reject(403,'insufficient_permissions');
        const key=req.headers['idempotency-key'];
        if(typeof key!=='string'||!IDEM_RE.test(key))reject(400,'invalid_idempotency_key');
        const match=req.headers['if-match'],none=req.headers['if-none-match'];
        if(!match&&!none)reject(428,'precondition_required');
        if((match&&none)||none&&none!=='*'||match&&(!/^"[\w.:-]{1,256}"$/.test(match)||match.startsWith('W/')))
          reject(400,'invalid_precondition');
        const request=await jsonInput(req);
        if(!request||typeof request!=='object'||Array.isArray(request)||
           Object.keys(request).sort().join(',')!=='schemaVersion,state'||request.schemaVersion!==1)
          reject(422,'invalid_state');
        validateSnapshot(request.state);
        const requestHash=hashToken(canonical({body:request,match:match||null,none:none||null}));
        const result=transact(db,()=>{
          const receipt=db.prepare(`SELECT * FROM web_idempotency
            WHERE actor_id=? AND workspace_id=? AND idem_key=?`)
            .get(session.user_id,session.workspace_id,key);
          if(receipt){
            if(receipt.request_hash!==requestHash)
              reject(409,'idempotency_key_conflict');
            return {status:receipt.response_status,body:JSON.parse(receipt.response_body),
              etag:receipt.response_etag};
          }
          const head=db.prepare('SELECT * FROM web_workspace_heads WHERE workspace_id=?')
            .get(session.workspace_id);
          if(!head&&none!=='*'||head&&match!==etagFor(head.revision))
            reject(409,'revision_conflict','Workspace revision changed.',
              head?{currentRevision:head.revision}:{});
          if(!head&&session.role!=='admin')reject(403,'insufficient_permissions');
          const state=head&&session.role==='editor'
            ?mergeEditor(JSON.parse(head.state_json),request.state,session):request.state;
          validateSnapshot(state);
          const stateJson=JSON.stringify(state);
          const size=db.prepare(`SELECT COALESCE(SUM(LENGTH(state_json)),0) AS bytes
            FROM web_workspace_snapshots WHERE workspace_id=?`).get(session.workspace_id).bytes;
          if(size+Buffer.byteLength(stateJson,'utf8')>512*1024*1024)
            reject(413,'workspace_storage_limit');
          const revision=crypto.randomUUID(),savedAt=utcNow(),etag=etagFor(revision);
          const status=head?200:201;
          const body={schemaVersion:1,revision,savedAt};
          db.prepare(`INSERT INTO web_workspace_heads(workspace_id,revision,state_json,updated_at)
            VALUES(?,?,?,?) ON CONFLICT(workspace_id) DO UPDATE SET
            revision=excluded.revision,state_json=excluded.state_json,
            updated_at=excluded.updated_at`).run(session.workspace_id,revision,stateJson,savedAt);
          db.prepare(`INSERT INTO web_workspace_snapshots
            (workspace_id,revision,state_json,created_at) VALUES(?,?,?,?)`)
            .run(session.workspace_id,revision,stateJson,savedAt);
          db.prepare(`INSERT INTO web_audit_events
            (id,actor_id,workspace_id,action,prior_revision,new_revision,created_at)
            VALUES(?,?,?,?,?,?,?)`).run(crypto.randomUUID(),session.user_id,
              session.workspace_id,head?'state.update':'state.create',head?.revision||null,revision,savedAt);
          const expires=new Date(Date.now()+IDEM_DAYS*86400000).toISOString();
          db.prepare(`INSERT INTO web_idempotency
            (actor_id,workspace_id,idem_key,request_hash,response_status,response_body,response_etag,created_at,expires_at)
            VALUES(?,?,?,?,?,?,?,?,?)`).run(session.user_id,session.workspace_id,key,
              requestHash,status,JSON.stringify(body),etag,savedAt,expires);
          return {status,body,etag};
        });
        response(res,result.status,result.body,{ETag:result.etag});return;
      }
      reject(404,'not_found');
    } catch(error){
      if(res.headersSent)return;
      const expected=error instanceof HttpError||error instanceof ValidationError||
        error instanceof ConversationError;
      response(res,expected?error.status:500,{
        error:expected?error.code:'internal_error',
        message:expected?error.message:'Internal server error.',
        ...(expected&&error.details?error.details:{})
      });
    }
  }
  const server=http.createServer((req,res)=>{void handle(req,res);});
  server.requestTimeout=35000;
  server.headersTimeout=15000;
  server.maxRequestsPerSocket=200;
  return {server,db,close:()=>new Promise((resolve,reject)=>{
    server.close(error=>{db.close();error?reject(error):resolve();});
    server.closeAllConnections();
  }),host};
}

if(require.main===module){
  const dbPath=process.env.MADAR_WEB_DB;
  const origin=process.env.MADAR_WEB_PUBLIC_ORIGIN;
  const host=process.env.MADAR_WEB_HOST||'127.0.0.1';
  const port=Number(process.env.MADAR_WEB_PORT||8781);
  if(!Number.isInteger(port)||port<1||port>65535)
    throw Error('MADAR_WEB_PORT must be 1..65535.');
  const app=createApp({dbPath,publicOrigin:origin,host});
  let stopping=false;
  app.server.listen(port,host,()=>{
    process.stdout.write('Madar Web API listening on '+host+':'+port+'\n');
  });
  const shutdown=signal=>{
    if(stopping)return;
    stopping=true;
    process.stdout.write('Madar Web API shutting down ('+signal+').\n');
    const force=setTimeout(()=>app.server.closeAllConnections(),10000);
    force.unref();
    app.server.close(error=>{
      clearTimeout(force);
      try{app.db.close();}catch(closeError){
        process.stderr.write('Database close failed: '+closeError.message+'\n');
        process.exitCode=1;
      }
      if(error){process.stderr.write(error.message+'\n');process.exitCode=1;}
    });
    app.server.closeIdleConnections();
  };
  process.once('SIGTERM',()=>shutdown('SIGTERM'));
  process.once('SIGINT',()=>shutdown('SIGINT'));
}
module.exports={createApp};
