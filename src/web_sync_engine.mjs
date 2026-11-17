import {WebApiError} from './web_api_client.mjs';

/**
 * Local-first snapshot synchronization.
 *
 * - A first upload is never implicit.
 * - An in-flight request is immutable and can be retried with the same key.
 * - New local edits coalesce into a separate pending snapshot.
 * - Revision conflicts preserve both copies and stop automatic writes.
 */
async function runSyncWebState({storage, api, freshState, bootstrap = false, maxWrites = 8}) {
  if (!storage || !api) throw new TypeError('Storage and API adapters are required.');
  const user = await api.getSession();
  if (!user) throw new WebApiError('auth_required', 401,
    'برای همگام‌سازی ابتدا وارد حساب شوید.');
  if (typeof user.workspaceId !== 'string' || !user.workspaceId)
    throw new WebApiError('workspace_scope_missing', 0,
      'سرور شناسهٔ فضای کاری معتبر ارائه نکرده است. همگام‌سازی متوقف شد.');
  if (!await storage.bindWorkspace(user.workspaceId))
    throw new WebApiError('workspace_scope_mismatch', 409,
      'داده‌های این مرورگر به فضای کاری دیگری متصل‌اند. پیش از تغییر حساب، پشتیبان بگیرید و فضای کاری را جداگانه تطبیق دهید.');

  let sync = await storage.readSyncState();
  if (sync.conflict) return {kind: 'conflict', processed: 0};

  // If a request was sent but its response was lost, retry that exact request
  // first. A GET that now sees the created remote state must not turn an
  // ambiguous first-write result into a false "different device" conflict.
  if (!sync.remoteRevision && !sync.inFlight) {
    const remote = await api.readState();
    if (remote.exists) {
      const local = await storage.read(freshState);
      await storage.recordConflict({
        localSnapshot: local,
        remoteSnapshot: remote.state,
        remoteRevision: remote.revision,
        remoteEtag: remote.etag,
        reason: 'remote_exists_without_local_baseline',
      });
      return {kind: 'conflict', processed: 0};
    }
    if (!bootstrap) return {kind: 'bootstrap_required', processed: 0};
    await storage.enqueueCurrent(freshState);
  }

  let processed = 0;
  while (processed < Math.max(1, Math.min(20, maxWrites))) {
    sync = await storage.readSyncState();
    if (sync.conflict) return {kind: 'conflict', processed};
    const job = await storage.claimPending();
    if (!job) {
      const latest = await storage.readSyncState();
      return {
        kind: latest.inFlight || latest.pending ? 'pending' : 'synced',
        processed,
      };
    }

    const current = await storage.readSyncState();
    if (job.baseRemoteRevision !== current.remoteRevision ||
        job.baseRemoteEtag !== current.remoteEtag) {
      // The immutable in-flight job may have already reached the server.
      // Changing its conditional headers under the same idempotency key is
      // unsafe even if another tab has since advanced the local journal.
      const error = new WebApiError('stale_outbox_base', 409,
        'مبنای صف با نسخهٔ ثبت‌شده متفاوت است؛ درخواست قدیمی بدون تغییر نگهداری شد.');
      await storage.markUncertain(job.id, error);
      return {kind: 'pending', processed, error};
    }

    try {
      const result = await api.writeState(job.snapshot,
        job.baseRemoteRevision === null ? null : {etag: job.baseRemoteEtag},
        job.id);
      await storage.acknowledge(job.id, result);
      processed++;
    } catch (error) {
      if (error?.status === 409 &&
          ['revision_conflict', 'stale_revision', 'precondition_failed'].includes(error.code)) {
        try {
          const remote = await api.readState();
          if (remote.exists) {
            const local = await storage.read(freshState);
            await storage.recordConflict({
              localSnapshot: local,
              remoteSnapshot: remote.state,
              remoteRevision: remote.revision,
              remoteEtag: remote.etag,
              reason: error.code,
            });
            return {kind: 'conflict', processed};
          }
        } catch (readError) {
          await storage.markUncertain(job.id, readError);
          return {kind: 'pending', processed, error: readError};
        }
      }
      await storage.markUncertain(job.id, error);
      return {kind: 'pending', processed, error};
    }
  }
  const latest = await storage.readSyncState();
  return {kind: latest.pending || latest.inFlight ? 'pending' : 'synced', processed};
}

const activeSyncs = new WeakMap();
export function syncWebState(options) {
  if (!options?.storage || typeof options.storage !== 'object')
    return Promise.reject(new TypeError('A storage instance is required.'));
  const active = activeSyncs.get(options.storage);
  if (active) return active;
  const promise = runSyncWebState(options).finally(() => {
    if (activeSyncs.get(options.storage) === promise)
      activeSyncs.delete(options.storage);
  });
  activeSyncs.set(options.storage, promise);
  return promise;
}
