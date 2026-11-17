'use strict';

const crypto=require('node:crypto');
const {transact,utcNow,canonical,hashToken}=require('./storage.cjs');
const TARGET_RE=/^[A-Za-z0-9_.:-]{1,128}$/;
const IDEM_RE=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/;
class ConversationError extends Error{
  constructor(status,code){super(code);this.status=status;this.code=code;this.conversation=true;}
}
const deny=(status,code)=>{throw new ConversationError(status,code);};
const validTarget=value=>typeof value==='string'&&TARGET_RE.test(value);
const validText=value=>typeof value==='string'&&value.trim()&&value.length<=4000&&
  !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value);
const exact=(value,fields)=>{
  if(!value||typeof value!=='object'||Array.isArray(value)||
    Object.keys(value).sort().join(',')!==fields.slice().sort().join(','))
    deny(422,'invalid_message_schema');
};
function scopeFor(db,session,scope,target,write=false){
  if(!['card','project'].includes(scope)||!validTarget(target))deny(404,'conversation_not_found');
  const head=db.prepare('SELECT state_json FROM web_workspace_heads WHERE workspace_id=?')
    .get(session.workspace_id);
  if(!head)deny(404,'state_not_initialized');
  const state=JSON.parse(head.state_json);
  const card=scope==='card'?state.tasks.find(t=>t.id===target):null;
  const projectId=scope==='card'?card?.projectId:target;
  const project=state.projects.find(p=>p.id===projectId);
  if(!project||(scope==='card'&&!card))deny(404,'conversation_not_found');
  const grants=session.project_ids_json===null?null:JSON.parse(session.project_ids_json);
  if(session.role!=='admin'&&(!Array.isArray(grants)||!grants.includes(projectId)))
    deny(403,'project_permission_denied');
  if(write&&(session.role==='viewer'||project.archived===true||
    (scope==='card'&&(card.deleted===true||card.archived===true))))
    deny(403,'conversation_read_only');
  return {projectId};
}
function listMessages(db,session,scope,target){
  const {projectId}=scopeFor(db,session,scope,target);
  const rows=db.prepare(`SELECT m.*,u.username AS author
    FROM web_conversation_messages m JOIN web_users u ON u.id=m.author_id
    WHERE m.workspace_id=? AND m.project_id=? AND m.scope=? AND m.target_id=?
    ORDER BY m.created_at DESC,m.id DESC LIMIT 300`)
    .all(session.workspace_id,projectId,scope,target);
  return {items:rows.reverse().map(row=>({
    id:row.id,projectId:row.project_id,cardId:scope==='card'?target:null,
    author:row.author,text:row.deleted_at?'':row.body,replyToId:row.reply_to||'',
    createdAt:row.created_at,updatedAt:row.updated_at,deletedAt:row.deleted_at,
    revision:row.revision
  }))};
}
function messageAction(db,session,{method,scope,target,messageId,payload,key}){
  if(!IDEM_RE.test(String(key||'')))deny(400,'invalid_idempotency_key');
  const creation=method==='POST',deletion=method==='DELETE';
  if(creation)exact(payload,['text','replyToId']);
  else if(deletion)exact(payload,[]);
  else if(method==='PUT')exact(payload,['text']);
  else deny(405,'method_not_allowed');
  if(creation&&!validText(payload.text)||method==='PUT'&&!validText(payload.text)||
    creation&&payload.replyToId!==''&&!validTarget(payload.replyToId))
    deny(422,'invalid_message_body');
  if(!creation&&!validTarget(messageId))deny(404,'message_not_found');
  const digest=hashToken(canonical({method,scope:scope||null,target:target||null,
    messageId:messageId||null,payload}));
  return transact(db,()=>{
    const saved=db.prepare(`SELECT request_hash,response_body FROM web_conversation_receipts
      WHERE actor_id=? AND workspace_id=? AND idem_key=?`)
      .get(session.user_id,session.workspace_id,key);
    if(saved){
      if(saved.request_hash!==digest)deny(409,'idempotency_key_conflict');
      // Verify current membership even when replaying a successful write.
      const previous=JSON.parse(saved.response_body);
      const {projectId}=scopeFor(db,session,previous.scope,previous.targetId,true);
      const earlier=db.prepare(`SELECT project_id,scope,target_id FROM web_conversation_messages
        WHERE id=? AND workspace_id=?`).get(previous.messageId,session.workspace_id);
      if(!earlier||earlier.project_id!==projectId||earlier.scope!==previous.scope||
         earlier.target_id!==previous.targetId)deny(403,'conversation_scope_changed');
      return previous;
    }
    const row=creation?null:db.prepare('SELECT * FROM web_conversation_messages WHERE id=? AND workspace_id=?')
      .get(messageId,session.workspace_id);
    if(!creation&&!row)deny(404,'message_not_found');
    const currentScope=creation?scope:row.scope,currentTarget=creation?target:row.target_id;
    const {projectId}=scopeFor(db,session,currentScope,currentTarget,true);
    if(row&&row.project_id!==projectId)deny(403,'conversation_scope_changed');
    const at=utcNow();
    let id=messageId,revision=1;
    if(creation){
      if(payload.replyToId){
        const reply=db.prepare('SELECT scope,target_id,project_id,deleted_at FROM web_conversation_messages WHERE id=? AND workspace_id=?')
          .get(payload.replyToId,session.workspace_id);
        if(!reply||reply.scope!==scope||reply.target_id!==target||reply.project_id!==projectId||
          reply.deleted_at)deny(422,'invalid_reply_target');
      }
      id=crypto.randomUUID();
      db.prepare(`INSERT INTO web_conversation_messages
        (id,workspace_id,project_id,scope,target_id,author_id,body,reply_to,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)`).run(id,session.workspace_id,projectId,
        scope,target,session.user_id,payload.text.trim(),payload.replyToId||null,at,at);
    }else{
      if(row.deleted_at)deny(409,'message_deleted');
      if(row.author_id!==session.user_id&&
        !(deletion&&session.role==='admin'))deny(403,'message_owner_required');
      revision=row.revision+1;
      db.prepare(`INSERT INTO web_conversation_revisions
        (message_id,workspace_id,actor_id,prior_revision,prior_body,prior_deleted_at,action,changed_at)
        VALUES(?,?,?,?,?,?,?,?)`).run(row.id,session.workspace_id,session.user_id,
        row.revision,row.body,row.deleted_at,deletion?'delete':'edit',at);
      db.prepare(`UPDATE web_conversation_messages SET body=?,updated_at=?,deleted_at=?,revision=?
        WHERE id=? AND workspace_id=?`).run(deletion?'':payload.text.trim(),
        at,deletion?at:null,revision,id,session.workspace_id);
    }
    const result={messageId:id,scope:currentScope,targetId:currentTarget,revision,
      updatedAt:at};
    db.prepare(`INSERT INTO web_conversation_receipts
      (actor_id,workspace_id,idem_key,request_hash,response_body,created_at)
      VALUES(?,?,?,?,?,?)`).run(session.user_id,session.workspace_id,key,digest,
      JSON.stringify(result),at);
    return result;
  });
}
module.exports={ConversationError,listMessages,messageAction};
