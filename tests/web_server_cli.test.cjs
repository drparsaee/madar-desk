'use strict';

const assert=require('node:assert/strict');
const {test}=require('node:test');
const {spawnSync}=require('node:child_process');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {openDatabase,createUser}=require('../server/storage.cjs');

const cli=path.resolve(__dirname,'../server/admin.cjs');

test('SQLite administrative backup is consistent, verifiable and non-overwriting',t=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'madar-web-cli-'));
  t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const db=path.join(dir,'workspace.sqlite');
  const copy=path.join(dir,'copy.sqlite');
  const env={...process.env,MADAR_WEB_DB:db};
  const call=(args,environment=env)=>spawnSync(process.execPath,[cli,...args],{
    cwd:path.resolve(__dirname,'..'),env:environment,encoding:'utf8',timeout:10000
  });
  assert.equal(call(['init']).status,0);
  const source=openDatabase(db);
  try {
    const user=createUser(source,{username:'restore-admin',password:'restore-only-test-password',
      role:'admin',workspaceId:'restore-team'});
    const state={version:1,workspaces:[{id:'work',name:'Backup Workspace'}],
      boards:[],projects:[],tasks:[{id:'retained-task',title:'Backup card',
        checklist:[],labels:[]}],stages:[],settings:{theme:'dark'}};
    source.prepare(`INSERT INTO web_workspace_heads
      (workspace_id,revision,state_json,updated_at) VALUES (?,?,?,?)`)
      .run('restore-team','revision-before-backup',JSON.stringify(state),
        '2026-11-06T12:00:00.000Z');
    source.prepare(`INSERT INTO web_conversation_messages
      (id,workspace_id,project_id,scope,target_id,author_id,body,created_at,updated_at)
      VALUES(?,?,?,?,?,?,?,?,?)`).run('message-retained','restore-team','project-1',
        'project','project-1',user.id,'Retained conversation',
        '2026-11-06T12:00:00.000Z','2026-11-06T12:00:00.000Z');
  } finally {source.close();}
  const backup=call(['backup',copy]);
  assert.equal(backup.status,0,backup.stderr);
  assert.equal(fs.existsSync(copy),true);
  assert.equal(call(['backup',copy]).status,1);
  const missing=path.join(dir,'absent.sqlite');
  const verify=call(['restore:verify',copy],
    {...process.env,MADAR_WEB_DB:missing});
  assert.equal(verify.status,0,verify.stderr);
  assert.equal(fs.existsSync(missing),false);
  const restored=path.join(dir,'restored.sqlite');
  fs.copyFileSync(copy,restored,fs.constants.COPYFILE_EXCL);
  const restoredList=call(['user:list'],{...process.env,MADAR_WEB_DB:restored});
  assert.equal(restoredList.status,0,restoredList.stderr);
  assert.match(restoredList.stdout,/restore-admin/);
  const restoredDb=openDatabase(restored);
  try {
    const head=restoredDb.prepare('SELECT revision,state_json FROM web_workspace_heads WHERE workspace_id=?')
      .get('restore-team');
    assert.equal(head.revision,'revision-before-backup');
    assert.equal(JSON.parse(head.state_json).tasks[0].title,'Backup card');
    assert.equal(restoredDb.prepare('SELECT body FROM web_conversation_messages WHERE id=?')
      .get('message-retained').body,'Retained conversation');
    assert.equal(restoredDb.prepare('PRAGMA user_version').get().user_version,3);
    assert.equal(restoredDb.prepare('SELECT COUNT(*) AS n FROM web_conversation_revisions')
      .get().n,0);
  } finally {restoredDb.close();}
});
