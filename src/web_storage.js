// Browser-only, origin-scoped Madar storage. No desktop profile, LAN host or
// accounting database is opened here. Browser data is NOT an online backup.
export const WEB_DB_NAME = 'madar-web-local-v1';
export const WEB_DB_VERSION = 2;
export const WEB_BACKUP_FORMAT = 'madar-web-local-backup';
const STORE = 'documents';
const SYNC_STORE = 'sync';
const KEY = 'board-state';
const PREFERENCES_KEY = 'preferences';
const RECOVERY_KEY = 'unsaved-recovery';
const SYNC_KEY = 'workspace-sync';
const MAX_IMPORT_BYTES = 16 * 1024 * 1024;

const revisionOf = value => Number.isSafeInteger(value?.__localRevision) &&
  value.__localRevision >= 0 ? value.__localRevision : 0;
const clone = value => value == null ? value : JSON.parse(JSON.stringify(value));
const randomId = () => globalThis.crypto?.randomUUID?.() ||
  'web-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)+
  Math.random().toString(36).slice(2);

function cleanSnapshot(value) {
  const {__localRevision, __remoteRevision, __offline, ...snapshot} = value || {};
  return clone(snapshot);
}

function emptySyncState() {
  return {
    workspaceId: null,
    remoteRevision: null,
    remoteEtag: null,
    lastSyncedAt: null,
    lastSyncedLocalRevision: 0,
    inFlight: null,
    pending: null,
    conflict: null,
    lastError: null,
  };
}

function normalizeSyncState(value) {
  return {...emptySyncState(), ...(value && typeof value === 'object' ? value : {})};
}

export function validateWebSnapshot(state) {
  if (!state || typeof state !== 'object' || Array.isArray(state))
    throw Error('ساختار دادهٔ مدار نامعتبر است.');
  for (const [key, limit] of Object.entries({
    tasks: 20000, projects: 1000, boards: 1000, workspaces: 200, stages: 200
  })) {
    if (!Array.isArray(state[key]) || state[key].length > limit ||
        state[key].some(item => !item || typeof item !== 'object' || Array.isArray(item)))
      throw Error('فهرست '+key+' در فایل معتبر نیست.');
  }
  if (!state.settings || typeof state.settings !== 'object' || Array.isArray(state.settings))
    throw Error('تنظیمات فایل پشتیبان نامعتبر است.');
  if (state.tasks.some(task => typeof task.id !== 'string' ||
      typeof task.title !== 'string' || !Array.isArray(task.checklist) ||
      !Array.isArray(task.labels) || !Array.isArray(task.reports || []) ||
      task.checklist.some(item => !item || typeof item !== 'object' || Array.isArray(item))))
    throw Error('ساختار یکی از کارت‌ها نامعتبر است.');
  return state;
}

export function decodeWebBackup(text) {
  if (typeof text !== 'string' || new TextEncoder().encode(text).length > MAX_IMPORT_BYTES)
    throw Error('فایل پشتیبان بیش از حد بزرگ است.');
  const envelope = JSON.parse(text);
  if (!envelope || envelope.format !== WEB_BACKUP_FORMAT ||
      envelope.schema !== 1 || !envelope.state)
    throw Error('فقط فایل پشتیبان نسخهٔ وب مدار قابل ورود است.');
  // Do not copy stale local or remote revision tokens from another device.
  return cleanSnapshot(validateWebSnapshot(envelope.state));
}

export function createWebStorage(indexedDBFactory = globalThis.indexedDB,
  {dbName = WEB_DB_NAME} = {}) {
  if (!indexedDBFactory) throw Error('مرورگر شما IndexedDB را پشتیبانی نمی‌کند.');
  const instanceId = randomId();
  const open = () => new Promise((resolve, reject) => {
    const request = indexedDBFactory.open(dbName, WEB_DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
      if (!db.objectStoreNames.contains(SYNC_STORE)) db.createObjectStore(SYNC_STORE);
      // v1 documents are deliberately retained byte-for-byte. The new sync
      // journal is additive and is created empty on upgrade.
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || Error('بازکردن حافظه مرورگر ناموفق بود.'));
    request.onblocked = () => reject(Error('به‌روزرسانی حافظه مرورگر توسط تب دیگر مسدود است.'));
  });

  const readRecord = async (storeName, key) => {
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction(storeName, 'readonly');
        const request = transaction.objectStore(storeName).get(key);
        request.onsuccess = () => resolve(request.result ?? null);
        request.onerror = () => reject(request.error || Error('خواندن داده ناموفق بود.'));
        transaction.onabort = () => reject(transaction.error || Error('خواندن داده متوقف شد.'));
      });
    } finally { db.close(); }
  };

  const persist = async (value, expectedRevision) => {
    validateWebSnapshot(value);
    const snapshot = cleanSnapshot(value);
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        // The board document and its latest pending sync snapshot are committed
        // in one IndexedDB transaction. A CAS failure aborts both writes.
        const transaction = db.transaction([STORE, SYNC_STORE], 'readwrite');
        const documents = transaction.objectStore(STORE);
        const syncStore = transaction.objectStore(SYNC_STORE);
        const currentRequest = documents.get(KEY);
        let failure;
        let nextRevision = null;
        currentRequest.onsuccess = () => {
          const currentRevision = revisionOf(currentRequest.result);
          if (currentRevision !== expectedRevision) {
            failure = Error('اطلاعات در تب دیگر تغییر کرده است. برای جلوگیری از بازنویسی، ذخیره متوقف شد. ابتدا خروجی بگیرید و داده‌ها را بازخوانی کنید.');
            transaction.abort();
            return;
          }
          nextRevision = currentRevision + 1;
          documents.put({...snapshot, __localRevision: nextRevision}, KEY);
          const syncRequest = syncStore.get(SYNC_KEY);
          syncRequest.onsuccess = () => {
            const sync = normalizeSyncState(syncRequest.result);
            const pending = {
              id: randomId(),
              localRevision: nextRevision,
              snapshot,
              baseRemoteRevision: sync.remoteRevision,
              baseRemoteEtag: sync.remoteEtag,
              createdAt: new Date().toISOString(),
            };
            if (sync.conflict) {
              sync.conflict.localSnapshot = snapshot;
              sync.conflict.localRevision = nextRevision;
            } else {
              // Coalesce only the not-yet-claimed snapshot. Any uncertain
              // in-flight write remains immutable for idempotent retry.
              sync.pending = pending;
            }
            sync.lastError = null;
            syncStore.put(sync, SYNC_KEY);
          };
          syncRequest.onerror = () => transaction.abort();
        };
        currentRequest.onerror = () => transaction.abort();
        transaction.oncomplete = () => resolve({localRevision: nextRevision});
        transaction.onabort = () => reject(failure || transaction.error || Error('ذخیره مرورگر ناموفق بود.'));
        transaction.onerror = () => reject(transaction.error || Error('ذخیره مرورگر ناموفق بود.'));
      });
    } finally { db.close(); }
  };

  const updateSync = async updater => {
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction(SYNC_STORE, 'readwrite');
        const store = transaction.objectStore(SYNC_STORE);
        const request = store.get(SYNC_KEY);
        let result;
        request.onsuccess = () => {
          const current = normalizeSyncState(request.result);
          result = updater(current);
          store.put(current, SYNC_KEY);
        };
        request.onerror = () => transaction.abort();
        transaction.oncomplete = () => resolve(clone(result));
        transaction.onabort = () => reject(transaction.error || Error('ثبت وضعیت همگام‌سازی ناموفق بود.'));
        transaction.onerror = () => reject(transaction.error || Error('ثبت وضعیت همگام‌سازی ناموفق بود.'));
      });
    } finally { db.close(); }
  };

  return {
    async read(fresh) {
      const stored = await readRecord(STORE, KEY);
      return stored ? validateWebSnapshot(stored) : {...fresh(), __localRevision: 0};
    },
    save: state => persist(state, revisionOf(state)),
    replace: (state, expectedRevision) => persist(state, expectedRevision),
    async backup() {
      const record = await readRecord(STORE, KEY);
      if (!record) throw Error('هنوز داده‌ای برای پشتیبان‌گیری ثبت نشده است.');
      return JSON.stringify({format: WEB_BACKUP_FORMAT, schema: 1,
        exportedAt: new Date().toISOString(), state: record}, null, 2);
    },
    async getPreferences() {
      return (await readRecord(STORE, PREFERENCES_KEY)) ||
        {calendar: 'jalali', widgetSettings: null};
    },
    async setPreferences(patch) {
      if (!patch || typeof patch !== 'object' || Array.isArray(patch))
        throw Error('تنظیمات مرورگر نامعتبر است.');
      const db = await open();
      try {
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction(STORE, 'readwrite');
          const store = transaction.objectStore(STORE);
          const request = store.get(PREFERENCES_KEY);
          let next;
          request.onsuccess = () => {
            const old = request.result || {calendar: 'jalali'};
            next = {...old, ...patch};
            store.put(next, PREFERENCES_KEY);
          };
          request.onerror = () => transaction.abort();
          transaction.oncomplete = () => resolve(clone(next));
          transaction.onabort = () => reject(transaction.error || Error('ذخیره تنظیمات ناموفق بود.'));
          transaction.onerror = () => reject(transaction.error || Error('ذخیره تنظیمات ناموفق بود.'));
        });
      } finally { db.close(); }
    },
    async saveRecovery(snapshot) {
      validateWebSnapshot(snapshot);
      const db = await open();
      try {
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction(STORE, 'readwrite');
          transaction.objectStore(STORE).put(cleanSnapshot(snapshot), RECOVERY_KEY);
          transaction.oncomplete = () => resolve(true);
          transaction.onabort = () => reject(transaction.error || Error('ثبت نسخه بازیابی ناموفق بود.'));
          transaction.onerror = () => reject(transaction.error || Error('ثبت نسخه بازیابی ناموفق بود.'));
        });
      } finally { db.close(); }
    },
    async getRecovery() {
      const recovery = await readRecord(STORE, RECOVERY_KEY);
      return recovery ? validateWebSnapshot(recovery) : null;
    },
    async clearRecovery() {
      const db = await open();
      try {
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction(STORE, 'readwrite');
          transaction.objectStore(STORE).delete(RECOVERY_KEY);
          transaction.oncomplete = () => resolve(true);
          transaction.onabort = () => reject(transaction.error || Error('پاک‌کردن نشان بازیابی ناموفق بود.'));
          transaction.onerror = () => reject(transaction.error || Error('پاک‌کردن نشان بازیابی ناموفق بود.'));
        });
      } finally { db.close(); }
    },
    readSyncState: async () => normalizeSyncState(await readRecord(SYNC_STORE, SYNC_KEY)),
    async bindWorkspace(workspaceId) {
      if (typeof workspaceId !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(workspaceId))
        throw Error('شناسه فضای کاری حساب معتبر نیست.');
      return updateSync(sync => {
        // An offline journal is scoped to exactly one authoritative workspace.
        // Reusing its ETag against another account can otherwise silently
        // overwrite a coincidentally equal remote revision.
        if (sync.workspaceId) return sync.workspaceId === workspaceId;
        // An already-synced legacy journal cannot be safely assigned to a
        // new account without an explicit migration/reconciliation.
        if (sync.remoteRevision || sync.inFlight || sync.conflict) return false;
        sync.workspaceId = workspaceId;
        return true;
      });
    },
    async getSyncStatus() {
      const sync = normalizeSyncState(await readRecord(SYNC_STORE, SYNC_KEY));
      const pendingCount = Number(!!sync.inFlight) + Number(!!sync.pending);
      return {
        mode: sync.remoteRevision ? 'client' : 'solo',
        connected: false,
        localOnly: !sync.remoteRevision,
        pending: pendingCount > 0 || !!sync.conflict,
        pendingCount,
        conflict: !!sync.conflict,
        remoteRevision: sync.remoteRevision,
        lastSync: sync.lastSyncedAt,
        lastError: sync.lastError,
      };
    },
    async enqueueCurrent(fresh) {
      const db = await open();
      try {
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction([STORE, SYNC_STORE], 'readwrite');
          const documents = transaction.objectStore(STORE);
          const syncStore = transaction.objectStore(SYNC_STORE);
          const currentRequest = documents.get(KEY);
          let result = false;
          currentRequest.onsuccess = () => {
            let current = currentRequest.result;
            if (!current) {
              if (typeof fresh !== 'function') { transaction.abort(); return; }
              current = {...fresh(), __localRevision: 0};
              try { validateWebSnapshot(current); }
              catch { transaction.abort(); return; }
              documents.put(current, KEY);
            }
            const syncRequest = syncStore.get(SYNC_KEY);
            syncRequest.onsuccess = () => {
              const sync = normalizeSyncState(syncRequest.result);
              if (sync.conflict || sync.pending || sync.inFlight) {
                result = false;
                return;
              }
              sync.pending = {
                id: randomId(),
                localRevision: revisionOf(current),
                snapshot: cleanSnapshot(current),
                baseRemoteRevision: sync.remoteRevision,
                baseRemoteEtag: sync.remoteEtag,
                createdAt: new Date().toISOString(),
              };
              syncStore.put(sync, SYNC_KEY);
              result = true;
            };
            syncRequest.onerror = () => transaction.abort();
          };
          currentRequest.onerror = () => transaction.abort();
          transaction.oncomplete = () => resolve(result);
          transaction.onabort = () => reject(transaction.error || Error('ساخت صف اولیه ناموفق بود.'));
          transaction.onerror = () => reject(transaction.error || Error('ساخت صف اولیه ناموفق بود.'));
        });
      } finally { db.close(); }
    },
    async claimPending() {
      return updateSync(sync => {
        if (sync.conflict) return null;
        const now = Date.now();
        if (sync.inFlight) {
          if (sync.inFlight.leaseUntil > now && sync.inFlight.leaseOwner !== instanceId)
            return null;
          sync.inFlight.leaseOwner = instanceId;
          sync.inFlight.leaseUntil = now + 35000;
          return sync.inFlight;
        }
        if (!sync.pending) return null;
        sync.inFlight = {...sync.pending, status: 'uncertain',
          attemptedAt: new Date().toISOString(),
          leaseOwner: instanceId, leaseUntil: now + 35000};
        sync.pending = null;
        return sync.inFlight;
      });
    },
    async acknowledge(id, {revision, etag, savedAt = null} = {}) {
      if (typeof revision !== 'string' || !revision || typeof etag !== 'string' || !etag)
        throw Error('پاسخ تأیید سرور ناقص است.');
      return updateSync(sync => {
        if (!sync.inFlight || sync.inFlight.id !== id) {
          // Another tab may have received the same idempotent receipt and
          // acknowledged it first. Treat that exact revision as success.
          if (!sync.inFlight && sync.remoteRevision === revision) return true;
          throw Error('پاسخ سرور به درخواست فعال تعلق ندارد.');
        }
        sync.remoteRevision = revision;
        sync.remoteEtag = etag;
        sync.lastSyncedAt = savedAt || new Date().toISOString();
        sync.lastSyncedLocalRevision = sync.inFlight.localRevision;
        sync.inFlight = null;
        if (sync.pending) {
          sync.pending.baseRemoteRevision = revision;
          sync.pending.baseRemoteEtag = etag;
        }
        sync.lastError = null;
        return true;
      });
    },
    async markUncertain(id, error) {
      return updateSync(sync => {
        if (sync.inFlight?.id === id) {
          sync.inFlight.status = 'uncertain';
          sync.inFlight.leaseOwner = null;
          sync.inFlight.leaseUntil = 0;
        }
        sync.lastError = {
          code: String(error?.code || 'network_unavailable').slice(0, 80),
          message: String(error?.message || error || 'ارتباط برقرار نشد.').slice(0, 300),
          at: new Date().toISOString(),
        };
        return !!sync.inFlight;
      });
    },
    async recordConflict({localSnapshot, remoteSnapshot, remoteRevision, remoteEtag,
      reason = 'revision_conflict'} = {}) {
      validateWebSnapshot(localSnapshot);
      validateWebSnapshot(remoteSnapshot);
      if (typeof remoteRevision !== 'string' || !remoteRevision ||
          typeof remoteEtag !== 'string' || !remoteEtag)
        throw Error('نسخه مرجع سرور برای ثبت تعارض معتبر نیست.');
      return updateSync(sync => {
        sync.remoteRevision = remoteRevision;
        sync.remoteEtag = remoteEtag;
        sync.conflict = {
          reason: String(reason).slice(0, 80),
          localSnapshot: cleanSnapshot(localSnapshot),
          localRevision: revisionOf(localSnapshot),
          remoteSnapshot: cleanSnapshot(remoteSnapshot),
          remoteRevision,
          remoteEtag,
          createdAt: new Date().toISOString(),
        };
        sync.inFlight = null;
        sync.lastError = {code: 'revision_conflict',
          message: 'نسخهٔ سرور و این دستگاه متفاوت‌اند.', at: new Date().toISOString()};
        return true;
      });
    },
    async resolveConflict(choice) {
      if (!['local', 'remote'].includes(choice)) throw Error('انتخاب حل تعارض معتبر نیست.');
      const db = await open();
      try {
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction([STORE, SYNC_STORE], 'readwrite');
          const documents = transaction.objectStore(STORE);
          const syncStore = transaction.objectStore(SYNC_STORE);
          const stateRequest = documents.get(KEY);
          const syncRequest = syncStore.get(SYNC_KEY);
          let result = null;
          let failure;
          let stateReady = false;
          let syncReady = false;
          const apply = () => {
            if (!stateReady || !syncReady || failure) return;
            const sync = normalizeSyncState(syncRequest.result);
            if (!sync.conflict) {
              failure = Error('تعارض فعالی برای حل‌کردن وجود ندارد.');
              transaction.abort();
              return;
            }
            const conflict = sync.conflict;
            if (choice === 'remote') {
              const remote = validateWebSnapshot(conflict.remoteSnapshot);
              const nextRevision = revisionOf(stateRequest.result) + 1;
              result = {...cleanSnapshot(remote), __localRevision: nextRevision,
                __remoteRevision: conflict.remoteRevision};
              documents.put(result, KEY);
              sync.lastSyncedLocalRevision = nextRevision;
              sync.lastSyncedAt = new Date().toISOString();
              sync.pending = null;
            } else {
              const local = validateWebSnapshot(stateRequest.result);
              result = {...cleanSnapshot(local), __localRevision: revisionOf(local),
                __remoteRevision: conflict.remoteRevision};
              sync.pending = {
                id: randomId(),
                localRevision: revisionOf(local),
                snapshot: cleanSnapshot(local),
                baseRemoteRevision: conflict.remoteRevision,
                baseRemoteEtag: conflict.remoteEtag,
                createdAt: new Date().toISOString(),
              };
            }
            sync.remoteRevision = conflict.remoteRevision;
            sync.remoteEtag = conflict.remoteEtag;
            sync.inFlight = null;
            sync.conflict = null;
            sync.lastError = null;
            syncStore.put(sync, SYNC_KEY);
          };
          stateRequest.onsuccess = () => { stateReady = true; apply(); };
          syncRequest.onsuccess = () => { syncReady = true; apply(); };
          stateRequest.onerror = syncRequest.onerror = () => {
            failure = Error('خواندن نسخه‌های تعارض ناموفق بود.');
            transaction.abort();
          };
          transaction.oncomplete = () => resolve(clone(result));
          transaction.onabort = () => reject(failure || transaction.error || Error('حل تعارض ناموفق بود.'));
          transaction.onerror = () => reject(transaction.error || Error('حل تعارض ناموفق بود.'));
        });
      } finally { db.close(); }
    },
  };
}

export function downloadWebBackup(text, documentRef = document, URLRef = URL) {
  const blob = new Blob([text], {type: 'application/json;charset=utf-8'});
  const url = URLRef.createObjectURL(blob);
  const link = documentRef.createElement('a');
  link.href = url;
  link.download = 'madar-web-backup-'+new Date().toISOString().slice(0, 10)+'.json';
  link.style.display = 'none';
  documentRef.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URLRef.revokeObjectURL(url), 2000);
  return {name: link.download};
}
