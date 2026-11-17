export const WEB_API_BASE = '/api/web/v1';
export const WEB_API_CONTRACT = 'madar-web-api-v1';
const IDEMPOTENCY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$/;
const SPECIAL_ID_PATTERN = /^[A-Za-z0-9_.:-]{1,128}$/;
const MAX_API_BODY_BYTES = 16 * 1024 * 1024;

export class WebApiError extends Error {
  constructor(code, status = 0, message = code, details = null) {
    super(message || code);
    this.name = 'WebApiError';
    this.code = code;
    this.status = status;
    this.details = details;
    this.retryable = status === 0 || status === 408 || status === 425 ||
      status === 429 || status >= 500;
  }
}

const isObject = value => !!value && typeof value === 'object' && !Array.isArray(value);
const cleanRevision = value => typeof value === 'string' &&
  value.length > 0 && value.length <= 256 ? value : null;
const TASK_LOCAL_ONLY_FIELDS = [
  'cost', 'costEnabled', 'costDate', 'costCategory', 'expenseItems',
  'invoiceId', 'linkedFinanceIds', 'linkedPurchaseIds', 'financeSourceId',
  'purchaseId', 'saleId', 'purchaseSourceId', 'accountingEntryId',
  'fileLinks', 'attachments',
];
const PROJECT_LOCAL_ONLY_FIELDS = ['costEnabled', 'price', 'fileLinks'];

function omitFields(value, fields) {
  const result = {...value};
  for (const field of fields) delete result[field];
  return result;
}

/** A browser task API never transmits accounting amounts or local file paths. */
export function toWebApiSnapshot(state) {
  if (!isObject(state) || state.version !== 1 || !Array.isArray(state.tasks) ||
      !Array.isArray(state.projects) || !Array.isArray(state.boards) ||
      !Array.isArray(state.workspaces) || !Array.isArray(state.stages) ||
      !isObject(state.settings))
    throw new WebApiError('invalid_state_input', 400);
  const tasks = state.tasks.map(task => {
    if (!isObject(task)) throw new WebApiError('invalid_state_input', 400);
    const clean = omitFields(task, TASK_LOCAL_ONLY_FIELDS);
    if (Array.isArray(task.checklist)) {
      clean.checklist = task.checklist.map(step =>
        isObject(step) ? omitFields(step, TASK_LOCAL_ONLY_FIELDS) : step);
    }
    return clean;
  });
  const projects = state.projects.map(project =>
    isObject(project) ? omitFields(project, PROJECT_LOCAL_ONLY_FIELDS) : project);
  // Google OAuth configuration belongs to the native client, even if its
  // identifier is public. Browser synchronization must not replicate it.
  const settings = omitFields(state.settings, ['costDefault', 'googleClientId']);
  return {...state, tasks, projects, settings};
}

export class MadarWebApiClient {
  constructor({fetchImpl = globalThis.fetch, locationRef = globalThis.location,
    basePath = WEB_API_BASE} = {}) {
    if (typeof fetchImpl !== 'function') throw new TypeError('Fetch API is unavailable.');
    if (!locationRef?.origin || !locationRef?.href)
      throw new TypeError('A browser origin is required for the web API.');
    const origin = new URL(locationRef.href);
    if (origin.protocol !== 'https:' &&
        !['localhost', '127.0.0.1', '[::1]', '::1'].includes(origin.hostname))
      throw new TypeError('The Madar web API requires HTTPS outside loopback development.');
    if (typeof basePath !== 'string' || !/^\/[A-Za-z0-9/_-]+$/.test(basePath) ||
        basePath.includes('//'))
      throw new TypeError('The web API must use a fixed same-origin path.');
    const base = new URL(basePath, locationRef.href);
    if (base.origin !== locationRef.origin)
      throw new TypeError('Cross-origin web API URLs are not permitted.');
    this.fetchImpl = fetchImpl.bind(globalThis);
    this.location = locationRef;
    this.basePath = base.pathname.replace(/\/$/, '');
    this.csrfToken = '';
    this.currentUser = null;
    this.healthInfo = null;
    this.healthCheckedAt = 0;
  }

  endpoint(path) {
    if (typeof path !== 'string' || !path.startsWith('/') ||
        path.startsWith('//') || path.includes('\\'))
      throw new WebApiError('invalid_api_path', 0);
    const url = new URL(this.basePath + path, this.location.href);
    if (url.origin !== this.location.origin ||
        !url.pathname.startsWith(this.basePath + '/'))
      throw new WebApiError('cross_origin_api_blocked', 0);
    return url;
  }

  async request(path, {method = 'GET', body, headers = {}, csrf = false,
    timeoutMs = 12000} = {}) {
    const verb = String(method).toUpperCase();
    const url = this.endpoint(path);
    const requestHeaders = {
      Accept: 'application/json',
      'X-Requested-With': 'MadarWeb',
      ...headers,
    };
    const hasBody = body !== undefined;
    const serializedBody = hasBody ? JSON.stringify(body) : undefined;
    if (hasBody) {
      if (new TextEncoder().encode(serializedBody).length > MAX_API_BODY_BYTES)
        throw new WebApiError('payload_too_large', 413);
      requestHeaders['Content-Type'] = 'application/json';
    }
    if (csrf) {
      if (!this.csrfToken) throw new WebApiError('csrf_token_missing', 0);
      requestHeaders['X-CSRF-Token'] = this.csrfToken;
    }
    let response;
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timeout = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      response = await this.fetchImpl(url.href, {
        method: verb,
        headers: requestHeaders,
        body: serializedBody,
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
        referrerPolicy: 'same-origin',
        ...(controller ? {signal: controller.signal} : {}),
      });
    } catch (error) {
      throw new WebApiError('network_unavailable', 0,
        error?.message || 'ارتباط با سرور برقرار نشد.');
    } finally {
      if (timeout !== null) clearTimeout(timeout);
    }
    if (response?.url) {
      try {
        if (new URL(response.url, this.location.href).origin !== this.location.origin)
          throw new WebApiError('cross_origin_response_blocked', 0);
      } catch (error) {
        if (error instanceof WebApiError) throw error;
        throw new WebApiError('invalid_api_response', 0);
      }
    }
    const contentType = response?.headers?.get?.('content-type') || '';
    if (response.status === 204)
      return {payload: {}, headers: response.headers, status: response.status};
    if (!/^application\/(?:[a-z0-9.+-]*\+)?json(?:\s*;|$)/i.test(contentType)) {
      if (response.status === 404 || response.status === 405 || response.status === 200)
        throw new WebApiError('api_not_installed', response.status,
          'زیرساخت API وب مدار هنوز روی این دامنه نصب نشده است.');
      throw new WebApiError('invalid_api_content_type', response.status);
    }
    let payload;
    try { payload = await response.json(); }
    catch { throw new WebApiError('invalid_api_json', response.status); }
    if (!response.ok) {
      const code = typeof payload?.error === 'string' ? payload.error :
        typeof payload?.code === 'string' ? payload.code : 'api_request_failed';
      throw new WebApiError(code, response.status,
        typeof payload?.message === 'string' ? payload.message : code, payload?.details || null);
    }
    if (!isObject(payload))
      throw new WebApiError('invalid_api_payload', response.status);
    return {payload, headers: response.headers, status: response.status};
  }

  async health({force = false} = {}) {
    if (!force && this.healthInfo && Date.now() - this.healthCheckedAt < 15000)
      return this.healthInfo;
    const {payload} = await this.request('/health', {timeoutMs: 5000});
    if (payload.service !== 'madar-web-api' || payload.contract !== WEB_API_CONTRACT ||
        payload.apiVersion !== 1 ||
        payload.stateSchemaVersion !== 1 || payload.status !== 'ready')
      throw new WebApiError('unsupported_api_contract', 0);
    this.healthInfo = payload;
    this.healthCheckedAt = Date.now();
    return payload;
  }

  async fetchCsrf() {
    const {payload} = await this.request('/csrf', {timeoutMs: 5000});
    if (typeof payload.csrfToken !== 'string' || payload.csrfToken.length < 24 ||
        payload.csrfToken.length > 512)
      throw new WebApiError('invalid_csrf_response', 0);
    this.csrfToken = payload.csrfToken;
    return this.csrfToken;
  }

  async login(username, password) {
    await this.health();
    if (typeof username !== 'string' || !username.trim() || username.length > 128 ||
        typeof password !== 'string' || password.length < 1 || password.length > 1024)
      throw new WebApiError('invalid_credentials_input', 400);
    await this.fetchCsrf();
    const {payload} = await this.request('/session', {
      method: 'POST', csrf: true,
      body: {username: username.trim(), password},
    });
    if (!isObject(payload.user) || typeof payload.user.username !== 'string' ||
        typeof payload.user.workspaceId !== 'string' || !payload.user.workspaceId ||
        !['admin', 'editor', 'viewer'].includes(payload.user.role) ||
        typeof payload.csrfToken !== 'string' || payload.csrfToken.length < 24)
      throw new WebApiError('invalid_session_response', 0);
    this.currentUser = payload.user;
    this.csrfToken = payload.csrfToken;
    return this.currentUser;
  }

  async getSession({force = false} = {}) {
    await this.health({force});
    try {
      const {payload} = await this.request('/session', {timeoutMs: 5000});
      if (payload.authenticated !== true || !isObject(payload.user) ||
          typeof payload.user.username !== 'string' ||
          typeof payload.user.workspaceId !== 'string' || !payload.user.workspaceId ||
          !['admin', 'editor', 'viewer'].includes(payload.user.role) ||
          typeof payload.csrfToken !== 'string' || payload.csrfToken.length < 24)
        throw new WebApiError('invalid_session_response', 0);
      this.currentUser = payload.user;
      this.csrfToken = payload.csrfToken;
      return this.currentUser;
    } catch (error) {
      if (error.status === 401 || error.code === 'session_expired') {
        this.currentUser = null;
        this.csrfToken = '';
        return null;
      }
      throw error;
    }
  }

  async logout() {
    if (!this.csrfToken) await this.fetchCsrf();
    await this.request('/session', {method: 'DELETE', csrf: true, timeoutMs: 5000});
    this.currentUser = null;
    this.csrfToken = '';
    return true;
  }

  async readState() {
    let response;
    try { response = await this.request('/state', {timeoutMs: 20000}); }
    catch (error) {
      if (error.status === 404 && error.code === 'state_not_initialized')
        return {exists: false, revision: null, etag: null};
      throw error;
    }
    const {payload, headers} = response;
    const revision = cleanRevision(payload.revision);
    const etag = headers.get('etag');
    if (payload.exists === false) return {exists: false, revision: null, etag: null};
    if (payload.schemaVersion !== 1 || payload.exists !== true ||
        !isObject(payload.state) || !revision ||
        typeof etag !== 'string' || !etag.trim() || /^W\//i.test(etag))
      throw new WebApiError('invalid_state_response', 0);
    const safeState = toWebApiSnapshot(payload.state);
    if (JSON.stringify(safeState) !== JSON.stringify(payload.state))
      throw new WebApiError('protected_data_in_web_api', 0,
        'سرور وب دادهٔ مالی یا مسیر فایل محلی را برگردانده است.');
    return {exists: true, state: safeState, revision, etag,
      updatedAt: typeof payload.updatedAt === 'string' ? payload.updatedAt : null};
  }

  async writeState(state, baseRevision, idempotencyKey) {
    if (!isObject(state)) throw new WebApiError('invalid_state_input', 400);
    if (!IDEMPOTENCY_PATTERN.test(String(idempotencyKey || '')))
      throw new WebApiError('invalid_idempotency_key', 400);
    const headers = {'Idempotency-Key': idempotencyKey};
    if (baseRevision === null || baseRevision === undefined) {
      headers['If-None-Match'] = '*';
    } else {
      const etag = typeof baseRevision === 'object' ? baseRevision.etag : baseRevision;
      if (typeof etag !== 'string' || !etag.trim() || /^W\//i.test(etag))
        throw new WebApiError('invalid_base_revision', 400);
      headers['If-Match'] = etag;
    }
    const {payload, headers: responseHeaders} = await this.request('/state', {
      method: 'PUT', csrf: true, headers,
      timeoutMs: 30000,
      body: {schemaVersion: 1, state: toWebApiSnapshot(state)},
    });
    const revision = cleanRevision(payload.revision);
    const etag = responseHeaders.get('etag');
    if (payload.schemaVersion !== 1 || !revision || typeof etag !== 'string' ||
        !etag.trim() || /^W\//i.test(etag))
      throw new WebApiError('invalid_state_write_response', 0);
    return {revision, etag, savedAt: typeof payload.savedAt === 'string'
      ? payload.savedAt : null};
  }
  async collabRead(kind, targetId) {
    const scope=kind==='comments'?'card':kind==='project-comments'?'project':null;
    if(!scope)throw new WebApiError('unsupported_collab_scope',400);
    if(typeof targetId!=='string'||!SPECIAL_ID_PATTERN.test(targetId))
      throw new WebApiError('invalid_collab_target',400);
    const {payload}=await this.request('/conversations/'+scope+'/'+targetId);
    if(!Array.isArray(payload.items))throw new WebApiError('invalid_collab_response',0);
    return payload.items;
  }
  async collabCommand(command) {
    if(!command||typeof command!=='object'||typeof command.eventId!=='string'||
      !IDEMPOTENCY_PATTERN.test(command.eventId))
      throw new WebApiError('invalid_collab_command',400);
    const type=command.type;
    const create=type==='comment.add'||type==='comment.reply'||
      type==='project.comment.add';
    const edit=type==='comment.edit'||type==='project.comment.edit';
    const remove=type==='comment.delete'||type==='project.comment.delete';
    if(!create&&!edit&&!remove)throw new WebApiError('unsupported_collab_command',400);
    const scope=type.startsWith('project.')?'project':'card';
    const target=create?(scope==='card'?command.cardId:command.projectId):null;
    if(create&&(typeof target!=='string'||!SPECIAL_ID_PATTERN.test(target)))
      throw new WebApiError('invalid_collab_target',400);
    const messageId=create?null:command.commentId;
    if(!create&&(typeof messageId!=='string'||!SPECIAL_ID_PATTERN.test(messageId)))
      throw new WebApiError('invalid_collab_message',400);
    const path=create?'/conversations/'+scope+'/'+target+'/messages':'/messages/'+messageId;
    const body=remove?{}:create?{text:command.text,replyToId:command.replyToId||''}:
      {text:command.text};
    const {payload}=await this.request(path,{method:create?'POST':edit?'PUT':'DELETE',
      csrf:true,body,headers:{'Idempotency-Key':command.eventId}});
    if(typeof payload.messageId!=='string')throw new WebApiError('invalid_collab_response',0);
    return {commentId:payload.messageId,revision:payload.revision};
  }
}
