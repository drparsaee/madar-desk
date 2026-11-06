// Browser-only, origin-scoped Madar storage. No desktop profile, LAN host or
// accounting database is opened here. Browser data is NOT an online backup.
export const WEB_DB_NAME = 'madar-web-local-v1';
export const WEB_BACKUP_FORMAT = 'madar-web-local-backup';
const STORE = 'documents';
const KEY = 'board-state';
const MAX_IMPORT_BYTES = 16 * 1024 * 1024;

const revisionOf = value => Number.isSafeInteger(value?.__localRevision) &&
  value.__localRevision >= 0 ? value.__localRevision : 0;

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
  // Do not copy stale revisions from another tab or device.
  const {__localRevision, __remoteRevision, ...data} = validateWebSnapshot(envelope.state);
  return data;
}

export function createWebStorage(indexedDBFactory = globalThis.indexedDB) {
  if (!indexedDBFactory) throw Error('مرورگر شما IndexedDB را پشتیبانی نمی‌کند.');
  const open = () => new Promise((resolve, reject) => {
    const request = indexedDBFactory.open(WEB_DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE))
        request.result.createObjectStore(STORE);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || Error('بازکردن حافظه مرورگر ناموفق بود.'));
    request.onblocked = () => reject(Error('به‌روزرسانی حافظه مرورگر توسط تب دیگر مسدود است.'));
  });
  const readRaw = async () => {
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction(STORE, 'readonly');
        const request = transaction.objectStore(STORE).get(KEY);
        let record;
        request.onsuccess = () => { record = request.result; };
        transaction.oncomplete = () => resolve(record || null);
        transaction.onerror = () => reject(transaction.error || Error('خواندن داده ناموفق بود.'));
        transaction.onabort = () => reject(transaction.error || Error('خواندن داده متوقف شد.'));
      });
    } finally { db.close(); }
  };
  const persist = async (value, expectedRevision) => {
    validateWebSnapshot(value);
    const db = await open();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction(STORE, 'readwrite');
        const store = transaction.objectStore(STORE);
        const request = store.get(KEY);
        let failure;
        let nextRevision = null;
        request.onsuccess = () => {
          const currentRevision = revisionOf(request.result);
          if (currentRevision !== expectedRevision) {
            failure = Error('اطلاعات در تب دیگر تغییر کرده است. برای جلوگیری از بازنویسی، ذخیره متوقف شد. ابتدا خروجی بگیرید و داده‌ها را بازخوانی کنید.');
            transaction.abort();
            return;
          }
          nextRevision = currentRevision + 1;
          store.put({...value, __localRevision: nextRevision}, KEY);
        };
        transaction.oncomplete = () => resolve({localRevision: nextRevision});
        transaction.onabort = () => reject(failure || transaction.error || Error('ذخیره مرورگر ناموفق بود.'));
        transaction.onerror = () => reject(transaction.error || Error('ذخیره مرورگر ناموفق بود.'));
      });
    } finally { db.close(); }
  };
  return {
    async read(fresh) {
      const stored = await readRaw();
      return stored ? validateWebSnapshot(stored) : {...fresh(), __localRevision: 0};
    },
    save: state => persist(state, revisionOf(state)),
    replace: (state, expectedRevision) => persist(state, expectedRevision),
    async backup() {
      const record = await readRaw();
      if (!record) throw Error('هنوز داده‌ای برای پشتیبان‌گیری ثبت نشده است.');
      return JSON.stringify({format: WEB_BACKUP_FORMAT, schema: 1,
        exportedAt: new Date().toISOString(), state: record}, null, 2);
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
