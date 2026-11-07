'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
let syncWebState,WebApiError;
test.before(async()=>{
  ({syncWebState}=await import('../src/web_sync_engine.mjs'));
  ({WebApiError}=await import('../src/web_api_client.mjs'));
});

const copy=value=>value==null?value:JSON.parse(JSON.stringify(value));
const seed=()=>({version:1,workspaces:[],boards:[],projects:[],tasks:[],stages:[],
  settings:{theme:'dark'}});

class MemoryStorage {
  constructor(state=seed()){
    this.state=copy(state);this.revision=1;
    this.sync={remoteRevision:null,remoteEtag:null,lastSyncedAt:null,
      inFlight:null,pending:null,conflict:null,lastError:null,workspaceId:null};
  }
  async bindWorkspace(id){
    if(this.sync.workspaceId)return this.sync.workspaceId===id;
    if(this.sync.remoteRevision||this.sync.inFlight||this.sync.conflict)return false;
    this.sync.workspaceId=id;return true;
  }
  async read(fresh){return copy(this.state||fresh());}
  async readSyncState(){return copy(this.sync);}
  async enqueueCurrent(fresh){
    if(!this.state)this.state=copy(fresh());
    if(this.sync.conflict||this.sync.pending||this.sync.inFlight)return false;
    this.sync.pending={id:'job-'+Math.random().toString(36).slice(2),
      localRevision:this.revision,snapshot:copy(this.state),
      baseRemoteRevision:this.sync.remoteRevision,baseRemoteEtag:this.sync.remoteEtag};
    return true;
  }
  async save(next){
    this.state=copy(next);this.revision++;
    if(this.sync.conflict){
      this.sync.conflict.localSnapshot=copy(next);
      this.sync.conflict.localRevision=this.revision;
    }else this.sync.pending={id:'job-'+this.revision,localRevision:this.revision,
      snapshot:copy(next),baseRemoteRevision:this.sync.remoteRevision,
      baseRemoteEtag:this.sync.remoteEtag};
  }
  async claimPending(){
    if(this.sync.conflict)return null;
    if(this.sync.inFlight)return copy(this.sync.inFlight);
    if(!this.sync.pending)return null;
    this.sync.inFlight={...copy(this.sync.pending),status:'uncertain'};
    this.sync.pending=null;
    return copy(this.sync.inFlight);
  }
  async acknowledge(id,result){
    assert.equal(this.sync.inFlight?.id,id);
    this.sync.remoteRevision=result.revision;this.sync.remoteEtag=result.etag;
    this.sync.lastSyncedAt=result.savedAt||'now';
    this.sync.inFlight=null;
    if(this.sync.pending){
      this.sync.pending.baseRemoteRevision=result.revision;
      this.sync.pending.baseRemoteEtag=result.etag;
    }
  }
  async markUncertain(id,error){
    if(this.sync.inFlight?.id===id)this.sync.inFlight.status='uncertain';
    this.sync.lastError={code:error.code,message:error.message};
  }
  async recordConflict(conflict){
    this.sync.remoteRevision=conflict.remoteRevision;
    this.sync.remoteEtag=conflict.remoteEtag;
    this.sync.conflict=copy(conflict);
    this.sync.inFlight=null;
    this.sync.lastError={code:'revision_conflict'};
  }
}

function fakeApi({remote=null,failAfterCommitOnce=false,forceConflict=false,session=true,
  workspaceId='workspace-test'}={}){
  const calls=[];
  const idempotency=new Map();
  let remoteState=copy(remote);
  let revision=remote?'remote-1':null;
  let etag=remote?'"remote-1"':null;
  let failed=false;
  return {
    calls,
    async getSession(){return session?{username:'editor',role:'editor',workspaceId}:null;},
    async readState(){
      return remoteState?{exists:true,state:copy(remoteState),revision,etag}:
        {exists:false,revision:null,etag:null};
    },
    async writeState(snapshot,baseRevision,id){
      calls.push({snapshot:copy(snapshot),baseRevision:copy(baseRevision),id});
      const fingerprint=JSON.stringify({snapshot,baseRevision});
      if(idempotency.has(id)){
        const saved=idempotency.get(id);
        if(saved.fingerprint!==fingerprint)
          throw new WebApiError('idempotency_key_conflict',409);
        return copy(saved.result);
      }
      if(forceConflict||((remoteState&&baseRevision?.etag!==etag)||
          (!remoteState&&baseRevision!==null)))
        throw new WebApiError('revision_conflict',409);
      revision=remoteState?'remote-'+(Number(revision.split('-')[1])+1):'remote-1';
      etag='"'+revision+'"';
      remoteState=copy(snapshot);
      const result={revision,etag,savedAt:'2026-11-06T12:00:00Z'};
      idempotency.set(id,{fingerprint,result:copy(result)});
      if(failAfterCommitOnce&&!failed){failed=true;throw new WebApiError('network_unavailable',0);}
      return result;
    },
  };
}

test('first upload is refused until the user explicitly bootstraps an empty remote workspace',async()=>{
  const storage=new MemoryStorage();
  const api=fakeApi();
  const blocked=await syncWebState({storage,api,freshState:seed,bootstrap:false});
  assert.equal(blocked.kind,'bootstrap_required');
  assert.equal(api.calls.length,0);
  const result=await syncWebState({storage,api,freshState:seed,bootstrap:true});
  assert.equal(result.kind,'synced');
  assert.equal(api.calls.length,1);
  assert.equal(api.calls[0].baseRevision,null);
  assert.equal((await storage.readSyncState()).remoteRevision,'remote-1');
});

test('uncertain first write is replayed exactly before newer pending work',async()=>{
  const storage=new MemoryStorage();
  const api=fakeApi({failAfterCommitOnce:true});
  const first=await syncWebState({storage,api,freshState:seed,bootstrap:true});
  assert.equal(first.kind,'pending');
  const journal=await storage.readSyncState();
  const originalId=journal.inFlight.id;
  const originalBody=copy(journal.inFlight.snapshot);
  await storage.save({...seed(),tasks:[{id:'newer',title:'ویرایش جدید',checklist:[],labels:[],reports:[]}]});
  const second=await syncWebState({storage,api,freshState:seed});
  assert.equal(second.kind,'synced');
  assert.equal(api.calls.length,3);
  assert.equal(api.calls[0].id,originalId);
  assert.equal(api.calls[1].id,originalId);
  assert.deepEqual(api.calls[0].snapshot,originalBody);
  assert.deepEqual(api.calls[1].snapshot,originalBody);
  assert.notEqual(api.calls[2].id,originalId);
  assert.equal(api.calls[2].baseRevision.etag,'"remote-1"');
  assert.equal(api.calls[2].snapshot.tasks[0].title,'ویرایش جدید');
  assert.equal((await storage.readSyncState()).remoteRevision,'remote-2');
});

test('an existing remote workspace without a local baseline becomes a preserved conflict',async()=>{
  const local={...seed(),tasks:[{id:'local',title:'نسخه محلی',checklist:[],labels:[],reports:[]}]};
  const remote={...seed(),tasks:[{id:'remote',title:'نسخه سرور',checklist:[],labels:[],reports:[]}]};
  const storage=new MemoryStorage(local);
  const api=fakeApi({remote});
  const result=await syncWebState({storage,api,freshState:seed});
  assert.equal(result.kind,'conflict');
  assert.equal(api.calls.length,0);
  const conflict=(await storage.readSyncState()).conflict;
  assert.equal(conflict.localSnapshot.tasks[0].title,'نسخه محلی');
  assert.equal(conflict.remoteSnapshot.tasks[0].title,'نسخه سرور');
});

test('a stale conditional write captures the remote snapshot and stops replay',async()=>{
  const local={...seed(),tasks:[{id:'local',title:'local',checklist:[],labels:[],reports:[]}]};
  const storage=new MemoryStorage(local);
  storage.sync.workspaceId='workspace-test';
  storage.sync.remoteRevision='remote-8';
  storage.sync.remoteEtag='"remote-8"';
  await storage.save({...local,tasks:[{...local.tasks[0],title:'local changed'}]});
  const remote={...seed(),tasks:[{id:'remote',title:'remote changed',checklist:[],labels:[],reports:[]}]};
  const api=fakeApi({remote,forceConflict:true});
  const result=await syncWebState({storage,api,freshState:seed});
  assert.equal(result.kind,'conflict');
  assert.equal(api.calls.length,1);
  const conflict=(await storage.readSyncState()).conflict;
  assert.equal(conflict.localSnapshot.tasks[0].title,'local changed');
  assert.equal(conflict.remoteSnapshot.tasks[0].title,'remote changed');
});

test('unauthenticated sync does not send queued data',async()=>{
  const storage=new MemoryStorage();
  await storage.enqueueCurrent(seed);
  const api=fakeApi({session:false});
  await assert.rejects(()=>syncWebState({storage,api,freshState:seed}),
    error=>error.code==='auth_required');
  assert.equal(api.calls.length,0);
  assert.ok((await storage.readSyncState()).pending);
});

test('a different workspace cannot reuse the same local revision and outbox',async()=>{
  const storage=new MemoryStorage();
  const firstApi=fakeApi({workspaceId:'workspace-A'});
  await syncWebState({storage,api:firstApi,freshState:seed,bootstrap:true});
  assert.equal(storage.sync.workspaceId,'workspace-A');
  await storage.save({...seed(),tasks:[{id:'keep',title:'Local pending',
    checklist:[],labels:[],reports:[]}]});
  const otherApi=fakeApi({workspaceId:'workspace-B'});
  await assert.rejects(()=>syncWebState({storage,api:otherApi,freshState:seed}),
    error=>error.code==='workspace_scope_mismatch');
  assert.equal(otherApi.calls.length,0);
  assert.equal(storage.sync.pending.snapshot.tasks[0].title,'Local pending');
});

test('an uncertain request retains its immutable precondition after a journal race',async()=>{
  const storage=new MemoryStorage();
  storage.sync.workspaceId='workspace-test';
  storage.sync.remoteRevision='r2';
  storage.sync.remoteEtag='"r2"';
  storage.sync.inFlight={id:'old-id',snapshot:seed(),localRevision:1,
    baseRemoteRevision:'r1',baseRemoteEtag:'"r1"'};
  const api=fakeApi({remote:seed()});
  const result=await syncWebState({storage,api,freshState:seed});
  assert.equal(result.kind,'pending');
  assert.equal(result.error.code,'stale_outbox_base');
  assert.equal(storage.sync.inFlight.baseRemoteRevision,'r1');
  assert.equal(storage.sync.inFlight.baseRemoteEtag,'"r1"');
  assert.equal(api.calls.length,0);
});
