'use strict';
const crypto=require('node:crypto');

const API_PREFIX='/api/web/v1';
const COOKIE_SESSION='madar_web_session';
const COOKIE_CSRF='madar_web_csrf';
const USER={username:'web-admin',workspaceId:'workspace-demo',displayName:'مدیر آزمایشی',role:'admin',projectIds:null};
const clone=value=>value==null?value:JSON.parse(JSON.stringify(value));
const token=()=>crypto.randomBytes(32).toString('base64url');
const cookies=header=>Object.fromEntries(String(header||'').split(';').map(part=>{
  const index=part.indexOf('=');
  return index<0?['','']:[part.slice(0,index).trim(),part.slice(index+1).trim()];
}).filter(([key])=>key));
const setCookie=(name,value,sameSite,maxAge=3600)=>
  name+'='+value+'; Path='+API_PREFIX+'; Max-Age='+maxAge+'; Secure; HttpOnly; SameSite='+sameSite;

function sendJson(res,status,payload,headers={}){
  res.statusCode=status;
  res.setHeader('Content-Type','application/json; charset=utf-8');
  res.setHeader('Cache-Control','no-store');
  for(const [name,value] of Object.entries(headers))res.setHeader(name,value);
  res.end(JSON.stringify(payload));
}
function sendError(res,status,error,message=error){sendJson(res,status,{error,message});}
async function readJson(req){
  const chunks=[];let size=0;
  for await(const chunk of req){
    size+=chunk.length;
    if(size>16*1024*1024)throw Object.assign(Error('too large'),{status:413});
    chunks.push(chunk);
  }
  try{return JSON.parse(Buffer.concat(chunks).toString('utf8'));}
  catch{throw Object.assign(Error('invalid JSON'),{status:400});}
}

function createMadarWebApiStub(){
  const sessions=new Map();
  const idempotency=new Map();
  const requests=[];
  let snapshot=null;
  let revision=0;
  const handler=(req,res,next)=>{
    Promise.resolve().then(async()=>{
      let path=String(req.url||'/').split('?')[0];
      if(path.startsWith(API_PREFIX))path=path.slice(API_PREFIX.length)||'/';
      const method=String(req.method||'GET').toUpperCase();
      requests.push({method,path});
      const jar=cookies(req.headers.cookie);
      const session=sessions.get(jar[COOKIE_SESSION]);
      const requireSession=()=>{
        if(!session){sendError(res,401,'session_expired','نشست آزمایشی منقضی شده است.');return false;}
        return true;
      };
      const requireCsrf=()=>{
        if(!session||!jar[COOKIE_CSRF]||req.headers['x-csrf-token']!==jar[COOKIE_CSRF]){
          sendError(res,403,'csrf_failed','توکن CSRF نامعتبر است.');return false;
        }
        return true;
      };
      if(method==='GET'&&path==='/health'){
        sendJson(res,200,{service:'madar-web-api',contract:'madar-web-api-v1',
        apiVersion:1,stateSchemaVersion:1,status:'ready',
        features:{snapshotSync:true}});return;
      }
      if(method==='GET'&&path==='/csrf'){
        const csrf=token();
        res.setHeader('Set-Cookie',setCookie(COOKIE_CSRF,csrf,'Strict'));
        sendJson(res,200,{csrfToken:csrf});return;
      }
      if(method==='POST'&&path==='/session'){
        if(!jar[COOKIE_CSRF]||req.headers['x-csrf-token']!==jar[COOKIE_CSRF]){
          sendError(res,403,'csrf_failed');return;
        }
        const body=await readJson(req);
        if(body.username!=='web-admin'||body.password!=='test-password'){
          sendError(res,401,'invalid_credentials','نام کاربری یا گذرواژه آزمایشی نامعتبر است.');return;
        }
        const sessionId=token();const csrf=token();
        sessions.set(sessionId,clone(USER));
        res.setHeader('Set-Cookie',[
          setCookie(COOKIE_SESSION,sessionId,'Lax',3600),
          setCookie(COOKIE_CSRF,csrf,'Strict',3600),
        ]);
        sendJson(res,200,{user:USER,csrfToken:csrf});return;
      }
      if(method==='GET'&&path==='/session'){
        if(!requireSession())return;
        sendJson(res,200,{authenticated:true,user:session,csrfToken:jar[COOKIE_CSRF]});return;
      }
      if(method==='DELETE'&&path==='/session'){
        if(!requireSession()||!requireCsrf())return;
        sessions.delete(jar[COOKIE_SESSION]);
        res.statusCode=204;
        res.setHeader('Set-Cookie',[
          setCookie(COOKIE_SESSION,'','Lax',0),
          setCookie(COOKIE_CSRF,'','Strict',0),
        ]);
        res.end();return;
      }
      if(method==='GET'&&path==='/state'){
        if(!requireSession())return;
        if(!snapshot){sendError(res,404,'state_not_initialized');return;}
        res.setHeader('ETag','"r'+revision+'"');
        sendJson(res,200,{schemaVersion:1,exists:true,revision:'r'+revision,
          state:clone(snapshot),updatedAt:'2026-11-06T12:00:00.000Z'});return;
      }
      if(method==='PUT'&&path==='/state'){
        if(!requireSession()||!requireCsrf())return;
        const body=await readJson(req);
        const key=req.headers['idempotency-key'];
        const ifMatch=req.headers['if-match']||null;
        const ifNone=req.headers['if-none-match']||null;
        if(typeof key!=='string'||!key){sendError(res,400,'idempotency_key_required');return;}
        if(body.schemaVersion!==1||!body.state||body.state.version!==1){
          sendError(res,422,'invalid_state');return;
        }
        const fingerprint=crypto.createHash('sha256').update(JSON.stringify({body,ifMatch,ifNone})).digest('hex');
        const previous=idempotency.get(key);
        if(previous){
          if(previous.fingerprint!==fingerprint){sendError(res,409,'idempotency_key_conflict');return;}
          if(previous.etag)res.setHeader('ETag',previous.etag);
          sendJson(res,previous.status,previous.receipt);return;
        }
        if((snapshot===null&&ifNone!=='*')||
          (snapshot!==null&&(ifMatch!==('"r'+revision+'"')||ifNone!==null))){
          sendError(res,409,'revision_conflict','نسخهٔ سرور تغییر کرده است.');return;
        }
        const first=snapshot===null;
        snapshot=clone(body.state);revision++;
        const etag='"r'+revision+'"';
        const receipt={schemaVersion:1,revision:'r'+revision,savedAt:'2026-11-06T12:00:00.000Z'};
        const saved={fingerprint,status:first?201:200,etag,receipt};
        idempotency.set(key,saved);
        res.setHeader('ETag',etag);
        sendJson(res,saved.status,receipt);return;
      }
      sendError(res,404,'not_found');
    }).catch(error=>{
      if(res.headersSent)return;
      sendError(res,error.status||500,error.status===413?'payload_too_large':'stub_error');
      if(typeof next==='function'&&error.status!==400&&error.status!==413)next(error);
    });
  };
  return {handler,requests,get snapshot(){return clone(snapshot);},get revision(){return revision;},get idempotencyCount(){return idempotency.size;}};
}

module.exports={createMadarWebApiStub};
