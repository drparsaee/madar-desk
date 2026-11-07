'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {DatabaseSync} = require('node:sqlite');

const SCRYPT = {N: 1 << 17, r: 8, p: 1, maxmem: 256 * 1024 * 1024};
const hashToken = token => crypto.createHash('sha256').update(token).digest('hex');
const randomToken = () => crypto.randomBytes(32).toString('base64url');
const utcNow = () => new Date().toISOString();
const etagFor = revision => '"'+revision+'"';
const canonical = value => JSON.stringify(value, (_key, item) => {
  if (item && !Array.isArray(item) && typeof item === 'object')
    return Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]]));
  return item;
});

function passwordHash(password) {
  if (typeof password !== 'string' || password.length < 12 || password.length > 1024)
    throw Error('Password must contain 12 to 1024 characters.');
  const salt = crypto.randomBytes(32);
  const key = crypto.scryptSync(password, salt, 64, SCRYPT);
  return 'scrypt$'+SCRYPT.N+'$'+SCRYPT.r+'$'+SCRYPT.p+'$'+salt.toString('base64url')+'$'+key.toString('base64url');
}

function passwordValid(password, stored) {
  try {
    const [type, n, r, p, salt, reference] = String(stored).split('$');
    if (type !== 'scrypt' || Number(n) !== SCRYPT.N ||
        Number(r) !== SCRYPT.r || Number(p) !== SCRYPT.p) return false;
    const expected = Buffer.from(reference, 'base64url');
    const saltBytes = Buffer.from(salt, 'base64url');
    if (expected.length !== 64 || saltBytes.length !== 32) return false;
    const key = crypto.scryptSync(password, saltBytes, 64, SCRYPT);
    return crypto.timingSafeEqual(expected, key);
  } catch { return false; }
}

function transact(db, execute) {
  db.exec('BEGIN IMMEDIATE');
  try {
    const result = execute();
    db.exec('COMMIT');
    return result;
  } catch (error) {
    try { db.exec('ROLLBACK'); } catch {}
    throw error;
  }
}

function openDatabase(file) {
  if (!file || file === ':memory:') throw Error('A persistent MADAR_WEB_DB file is required.');
  fs.mkdirSync(path.dirname(path.resolve(file)), {recursive: true, mode: 0o700});
  const db = new DatabaseSync(path.resolve(file));
  db.exec('PRAGMA journal_mode=WAL');
  db.exec('PRAGMA synchronous=FULL');
  db.exec('PRAGMA busy_timeout=5000');
  db.exec('PRAGMA foreign_keys=ON');
  const version = db.prepare('PRAGMA user_version').get().user_version;
  if (version > 3) { db.close(); throw Error('Unsupported database migration version.'); }
  if (version === 0) transact(db, () => {
    db.exec(`
      CREATE TABLE web_users (
        id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin','editor','viewer')),
        workspace_id TEXT NOT NULL, project_ids_json TEXT,
        enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
      );
      CREATE TABLE web_sessions (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES web_users(id),
        csrf_hash TEXT NOT NULL, created_at INTEGER NOT NULL,
        last_seen_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
      );
      CREATE INDEX web_sessions_user ON web_sessions(user_id);
      CREATE TABLE web_workspace_heads (
        workspace_id TEXT PRIMARY KEY, revision TEXT NOT NULL,
        state_json TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE web_workspace_snapshots (
        workspace_id TEXT NOT NULL, revision TEXT NOT NULL,
        state_json TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (workspace_id, revision)
      );
      CREATE TABLE web_idempotency (
        actor_id TEXT NOT NULL, workspace_id TEXT NOT NULL, idem_key TEXT NOT NULL,
        request_hash TEXT NOT NULL, response_status INTEGER NOT NULL,
        response_body TEXT NOT NULL, response_etag TEXT NOT NULL,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        PRIMARY KEY(actor_id, workspace_id, idem_key)
      );
      CREATE TABLE web_audit_events (
        id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
        action TEXT NOT NULL, prior_revision TEXT, new_revision TEXT,
        created_at TEXT NOT NULL
      );
      CREATE TABLE web_login_limits (
        bucket_hash TEXT PRIMARY KEY, failures INTEGER NOT NULL,
        next_allowed_at INTEGER NOT NULL, last_at INTEGER NOT NULL
      );
    `);
    db.exec('PRAGMA user_version=1');
  });
  if(version<=1)transact(db,()=>{
    db.exec(`
      CREATE TABLE web_conversation_messages (
        id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, project_id TEXT NOT NULL,
        scope TEXT NOT NULL CHECK (scope IN ('project','card')), target_id TEXT NOT NULL,
        author_id TEXT NOT NULL REFERENCES web_users(id),
        body TEXT NOT NULL, reply_to TEXT REFERENCES web_conversation_messages(id),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT,
        revision INTEGER NOT NULL DEFAULT 1
      );
      CREATE INDEX web_conversation_scope ON web_conversation_messages
        (workspace_id,scope,target_id,created_at,id);
      CREATE TABLE web_conversation_receipts (
        actor_id TEXT NOT NULL, workspace_id TEXT NOT NULL, idem_key TEXT NOT NULL,
        request_hash TEXT NOT NULL, response_body TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (actor_id,workspace_id,idem_key)
      );
    `);
    db.exec('PRAGMA user_version=2');
  });
  if(version<=2)transact(db,()=>{
    db.exec(`
      CREATE TABLE web_conversation_revisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT NOT NULL REFERENCES web_conversation_messages(id),
        workspace_id TEXT NOT NULL,
        actor_id TEXT NOT NULL REFERENCES web_users(id),
        prior_revision INTEGER NOT NULL,
        prior_body TEXT NOT NULL,
        prior_deleted_at TEXT,
        action TEXT NOT NULL CHECK (action IN ('edit','delete')),
        changed_at TEXT NOT NULL
      );
      CREATE INDEX web_conversation_revisions_message
        ON web_conversation_revisions(workspace_id,message_id,prior_revision);
    `);
    db.exec('PRAGMA user_version=3');
  });
  return db;
}

function createUser(db, {username, displayName = username, password, role, workspaceId='default', projectIds=null}) {
  if (typeof username !== 'string' || !/^[A-Za-z0-9_.-]{1,128}$/.test(username) ||
      typeof displayName !== 'string' || !displayName || displayName.length > 160 ||
      !['admin','editor','viewer'].includes(role) ||
      !/^[A-Za-z0-9_.:-]{1,128}$/.test(workspaceId) ||
      !(projectIds === null || Array.isArray(projectIds) &&
        projectIds.length <= 1000 && projectIds.every(id => typeof id === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(id))))
    throw Error('Invalid local account profile.');
  // A non-admin cannot receive global scope accidentally during provisioning.
  if (role !== 'admin' && projectIds === null) throw Error('Non-admin accounts need explicit project grants.');
  const existing = db.prepare('SELECT id FROM web_users WHERE username=?').get(username);
  if (existing) throw Error('Account already exists; use password-reset or set-role.');
  const id=crypto.randomUUID();
  db.prepare(`INSERT INTO web_users
    (id,username,display_name,password_hash,role,workspace_id,project_ids_json,created_at)
    VALUES (?,?,?,?,?,?,?,?)`).run(id,username,displayName,passwordHash(password),role,
    workspaceId,projectIds === null ? null : JSON.stringify([...new Set(projectIds)]),utcNow());
  return {id,username,role,workspaceId,projectIds};
}

function resetPassword(db,username,password) {
  const user=db.prepare('SELECT id FROM web_users WHERE username=?').get(username);
  if (!user) throw Error('Account not found.');
  const hashed=passwordHash(password);
  transact(db,()=>{
    db.prepare('UPDATE web_users SET password_hash=? WHERE id=?').run(hashed,user.id);
    db.prepare('DELETE FROM web_sessions WHERE user_id=?').run(user.id);
  });
}

function setRole(db,username,role,projectIds) {
  if (!['admin','editor','viewer'].includes(role) ||
      !(projectIds === null || Array.isArray(projectIds) &&
        projectIds.length <= 1000 && projectIds.every(id => /^[A-Za-z0-9_.:-]{1,128}$/.test(id))) ||
      (role !== 'admin' && projectIds === null)) throw Error('Invalid grants.');
  const user=db.prepare('SELECT id FROM web_users WHERE username=?').get(username);
  if(!user) throw Error('Account not found.');
  transact(db,()=>{
    db.prepare('UPDATE web_users SET role=?,project_ids_json=? WHERE id=?').run(role,
      projectIds === null ? null : JSON.stringify([...new Set(projectIds)]),user.id);
    db.prepare('DELETE FROM web_sessions WHERE user_id=?').run(user.id);
  });
}

module.exports={openDatabase,createUser,resetPassword,setRole,transact,hashToken,randomToken,
  passwordHash,passwordValid,utcNow,etagFor,canonical};
