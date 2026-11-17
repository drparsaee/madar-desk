'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {openDatabase,createUser}=require('../server/storage.cjs');

test('existing populated SQLite v1 migrates to v3 without losing accounts, snapshots or sessions',t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'madar-web-v1-migrate-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const filename=path.join(dir,'legacy.sqlite');
  const legacy=openDatabase(filename);
  let id;
  try{
    id=createUser(legacy,{username:'legacy',password:'legacy-test-password-123',
      role:'admin',workspaceId:'legacy-team'}).id;
    legacy.prepare(`INSERT INTO web_workspace_heads
      (workspace_id,revision,state_json,updated_at) VALUES (?,?,?,?)`)
      .run('legacy-team','revision-v1',JSON.stringify({tasks:[{id:'legacy-card'}]}),
        '2026-11-06T12:00:00.000Z');
    legacy.prepare(`INSERT INTO web_workspace_snapshots
      (workspace_id,revision,state_json,created_at) VALUES (?,?,?,?)`)
      .run('legacy-team','revision-v1','{"test":true}','2026-11-06T12:00:00.000Z');
    legacy.prepare(`INSERT INTO web_sessions
      (token_hash,user_id,csrf_hash,created_at,last_seen_at,expires_at)
      VALUES(?,?,?,?,?,?)`).run('legacy-hash',id,'legacy-csrf',1,2,3);
    // Recreate an exact v1 schema from the current v2 schema without touching
    // any old user/snapshot/session rows. No real user file is involved.
    legacy.exec('DROP TABLE web_conversation_revisions');
    legacy.exec('DROP TABLE web_conversation_receipts');
    legacy.exec('DROP TABLE web_conversation_messages');
    legacy.exec('PRAGMA user_version=1');
  }finally{legacy.close();}

  const upgraded=openDatabase(filename);
  try{
    assert.equal(upgraded.prepare('PRAGMA user_version').get().user_version,3);
    assert.equal(upgraded.prepare('SELECT id FROM web_users WHERE username=?').get('legacy').id,id);
    assert.equal(upgraded.prepare('SELECT revision FROM web_workspace_heads WHERE workspace_id=?')
      .get('legacy-team').revision,'revision-v1');
    assert.equal(upgraded.prepare('SELECT state_json FROM web_workspace_snapshots').get().state_json,
      '{"test":true}');
    assert.equal(upgraded.prepare('SELECT user_id FROM web_sessions').get().user_id,id);
    assert.equal(upgraded.prepare('SELECT COUNT(*) AS count FROM web_conversation_messages')
      .get().count,0);
    assert.equal(upgraded.prepare('SELECT COUNT(*) AS count FROM web_conversation_revisions')
      .get().count,0);
    assert.equal(upgraded.prepare('PRAGMA integrity_check').get().integrity_check,'ok');
  }finally{upgraded.close();}
});

test('populated SQLite v2 conversation messages survive in-place v3 audit migration',t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'madar-web-v2-migrate-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const filename=path.join(dir,'legacy.sqlite');
  const old=openDatabase(filename);
  try{
    const id=createUser(old,{username:'v2-user',password:'legacy-test-password-123',
      role:'admin',workspaceId:'legacy-team'}).id;
    old.prepare(`INSERT INTO web_conversation_messages
      (id,workspace_id,project_id,scope,target_id,author_id,body,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?)`).run('retained-message','legacy-team','p1',
        'project','p1',id,'Historical v2 body','2026-11-07T01:00:00Z','2026-11-07T01:00:00Z');
    old.exec('DROP TABLE web_conversation_revisions');
    old.exec('PRAGMA user_version=2');
  }finally{old.close();}
  const upgraded=openDatabase(filename);
  try{
    assert.equal(upgraded.prepare('PRAGMA user_version').get().user_version,3);
    assert.equal(upgraded.prepare('SELECT body FROM web_conversation_messages WHERE id=?')
      .get('retained-message').body,'Historical v2 body');
    assert.equal(upgraded.prepare('SELECT COUNT(*) AS count FROM web_conversation_revisions')
      .get().count,0);
  }finally{upgraded.close();}
});
