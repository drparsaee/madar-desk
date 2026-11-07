'use strict';

const readline=require('node:readline');
const fs=require('node:fs');
const path=require('node:path');
const {backup,DatabaseSync}=require('node:sqlite');
const {openDatabase,createUser,resetPassword,setRole}=require('./storage.cjs');

async function passwordFromStdin(){
  if(!process.stdin.isTTY) {
    const chunks=[];
    for await(const chunk of process.stdin)chunks.push(chunk);
    const password=Buffer.concat(chunks).toString('utf8').replace(/\r?\n$/,'');
    if(!password)throw Error('Password missing from stdin.');
    return password;
  }
  process.stdout.write('Password (hidden): ');
  readline.emitKeypressEvents(process.stdin);
  process.stdin.setRawMode(true);
  process.stdin.resume();
  return new Promise((resolve,reject)=>{
    const chars=[];
    const finish=(error)=>{
      process.stdin.removeListener('keypress',onKey);
      process.stdin.setRawMode(false);
      process.stdin.pause();
      process.stdout.write('\n');
      if(error)reject(error);else resolve(chars.join(''));
    };
    const onKey=(ch,key={})=>{
      if(key.ctrl&&key.name==='c')return finish(Error('Cancelled.'));
      if(key.name==='return'||key.name==='enter')return finish();
      if(key.name==='backspace'){chars.pop();return;}
      if(ch&&ch>=' '&&!key.ctrl&&!key.meta)chars.push(ch);
    };
    process.stdin.on('keypress',onKey);
  });
}
function readGrants(role,argument){
  if(role==='admin'){
    if(argument && argument!=='*')throw Error('Admin grants must be * (full scope).');
    return null;
  }
  if(typeof argument!=='string')throw Error('Provide comma-separated project IDs, or - for none.');
  return argument==='-'?[]:argument.split(',').filter(Boolean);
}
function verifyCandidate(filename){
  const verified=new DatabaseSync(path.resolve(filename),{readOnly:true});
  try{
    const version=verified.prepare('PRAGMA user_version').get().user_version;
    if(verified.prepare('PRAGMA integrity_check').get().integrity_check!=='ok'||
       (version!==1&&version!==2&&version!==3))
      throw Error('Restore candidate failed integrity/schema checks.');
    for(const table of ['web_users','web_sessions','web_workspace_heads',
      'web_idempotency','web_audit_events'])
      verified.prepare('SELECT count(*) c FROM '+table).get();
    if(version===2)for(const table of ['web_conversation_messages','web_conversation_receipts'])
      verified.prepare('SELECT count(*) c FROM '+table).get();
    if(version===3)for(const table of ['web_conversation_messages',
      'web_conversation_receipts','web_conversation_revisions'])
      verified.prepare('SELECT count(*) c FROM '+table).get();
  }finally{verified.close();}
}

async function main(args=process.argv.slice(2)){
  const [action,username,role,workspace,grantArg]=args;
  if(action==='restore:verify'){
    if(!username||!fs.existsSync(username))throw Error('A readable restore candidate is required.');
    verifyCandidate(username);
    process.stdout.write('Restore candidate verified; active database unchanged.\n');return;
  }
  if(!process.env.MADAR_WEB_DB)throw Error('Set MADAR_WEB_DB to the dedicated web SQLite file.');
  const db=openDatabase(process.env.MADAR_WEB_DB);
  try{
    if(action==='init'){
      process.stdout.write('SQLite v3 migration is applied.\n');return;
    }
    if(action==='user:list'){
      for(const row of db.prepare(`SELECT username,role,workspace_id,project_ids_json,enabled
        FROM web_users ORDER BY username`).all()){
        process.stdout.write(JSON.stringify({username:row.username,role:row.role,
          workspaceId:row.workspace_id,projectIds:JSON.parse(row.project_ids_json||'null'),
          enabled:!!row.enabled})+'\n');
      }
      return;
    }
    if(action==='backup'){
      if(!username)throw Error('Backup destination is required.');
      const destination=path.resolve(username);
      if(destination===path.resolve(process.env.MADAR_WEB_DB)||
         fs.existsSync(destination))throw Error('Backup destination already exists or equals the source.');
      fs.mkdirSync(path.dirname(destination),{recursive:true,mode:0o700});
      await backup(db,destination);
      fs.chmodSync(destination,0o600);
      verifyCandidate(destination);
      process.stdout.write('Verified SQLite backup at '+destination+'\n');return;
    }
    if(action==='user:add'){
      const grants=readGrants(role,grantArg);
      const result=createUser(db,{username,role,workspaceId:workspace||'default',
        projectIds:grants,password:await passwordFromStdin()});
      process.stdout.write('Created user '+result.username+' in workspace '+result.workspaceId+'\n');
      return;
    }
    if(action==='user:reset-password'){
      if(!username)throw Error('Username is required.');
      resetPassword(db,username,await passwordFromStdin());
      process.stdout.write('Password rotated and sessions revoked.\n');
      return;
    }
    if(action==='user:set-role'){
      if(!username)throw Error('Username is required.');
      setRole(db,username,role,readGrants(role,workspace));
      process.stdout.write('Role updated and sessions revoked.\n');
      return;
    }
    if(action==='user:disable'){
      const user=db.prepare('SELECT id FROM web_users WHERE username=?').get(username);
      if(!user)throw Error('Account not found.');
      db.exec('BEGIN IMMEDIATE');
      try{
        db.prepare('UPDATE web_users SET enabled=0 WHERE id=?').run(user.id);
        db.prepare('DELETE FROM web_sessions WHERE user_id=?').run(user.id);
        db.exec('COMMIT');
      }catch(error){db.exec('ROLLBACK');throw error;}
      process.stdout.write('Account disabled and sessions revoked.\n');return;
    }
    throw Error('Usage: init | user:list | backup <new-file> | restore:verify <existing-file> | user:add <username> <admin|editor|viewer> <workspace_id> <*|project1,project2|-> | user:reset-password <username> | user:set-role <username> <role> <*|project1,project2|-> | user:disable <username>');
  }finally{db.close();}
}
if(require.main===module)main().catch(error=>{process.stderr.write(error.message+'\n');process.exitCode=1;});
module.exports={main};
