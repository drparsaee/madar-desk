import React, {useId, useRef, useState} from 'react';

/**
 * Isolated E1 admin/consent UI. No model, provider transport, storage or keys.
 * command(action, data, projectId) is injected by the host UI and MUST add
 * manualAction:true for mutations, with fresh server-side ACL/CAS validation.
 *
 * Optional preverified cloudConsent presentation hint:
 * {preverified:true, projectId, provider, requestId, payloadDigest}.
 * The backend cannot trust a client boolean or digest to prove safe text or
 * user gesture; the current backend has no dispatch endpoint at all.
 */
const ID=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/;
const RID=/^[a-f0-9]{32}$/;
const HASH=/^[a-f0-9]{64}$/;
const PROVIDERS=[['local_ollama','Ollama · محلی'],['openai','OpenAI · ابری'],
  ['gemini','Gemini · ابری'],['anthropic','Anthropic · ابری']];
const CLOUD=new Set(['openai','gemini','anthropic']);
const MAX={monthlyRequests:100000,monthlyTokens:100000000,monthlyCostMicro:1000000000000};
const EMPTY={enabled:false,cloudEnabled:false,monthlyRequests:'0',
  monthlyTokens:'0',monthlyCostMicro:'0'};
const ERROR_TEXT={
  authentication_required:'نشست معتبر نیست. دوباره وارد شوید.',
  access_denied:'دسترسی مجاز نیست.',permission_denied:'مجوز انجام عملیات ندارید.',
  target_denied:'این حساب برای پروژه مجاز نیست.',
  scope_denied:'دسترسی به پروژه مجاز نیست.',
  ai_disabled:'دسترسی هوش مصنوعی این حساب غیرفعال است.',
  grant_denied:'مجوز این ارائه‌دهنده غیرفعال است.',
  version_conflict:'نسخه مجوز تغییر کرده است. دوباره آن را بخوانید.',
  event_conflict:'شناسه عملیات پیش‌تر برای داده متفاوت ثبت شده است.',
  consent_required:'رضایت معتبر برای درخواست موجود نیست.',
};
const S={
  base:{color:'var(--vs-ink,#192637)',maxWidth:1040},
  card:{border:'1px solid var(--vs-edge,#b6bfcb)',padding:20,marginBlock:14,
    borderRadius:'var(--vtr-tile-radius,20px)',background:'var(--vs-glass,#f6f8fa)'},
  grid:{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(100%,210px),1fr))',gap:14},
  label:{display:'flex',flexDirection:'column',gap:6,minWidth:0},
  input:{font:'inherit',width:'100%',padding:'9px 12px',borderRadius:10,
    border:'1px solid var(--vs-edge,#b6bfcb)',
    background:'var(--vtr-glass-thick,#fff)',color:'var(--vs-ink,#192637)'},
  line:{display:'flex',alignItems:'center',gap:10,marginBlock:12,lineHeight:1.7},
  actions:{display:'flex',gap:10,alignItems:'center',flexWrap:'wrap',marginBlock:14},
  button:{font:'inherit',padding:'10px 16px',borderRadius:10,
    border:'1px solid var(--vs-edge,#b6bfcb)',cursor:'pointer',
    background:'var(--vtr-glass-thick,#fff)',color:'var(--vs-ink,#192637)'},
  primary:{fontWeight:700,background:'var(--vs-accent-soft,#e4effb)',
    borderColor:'var(--vs-accent,#4b84bd)'},
  muted:{color:'var(--vs-muted,#455369)',lineHeight:1.8},
  status:{padding:'10px 12px',border:'1px solid var(--vs-edge,#b6bfcb)',
    borderRadius:9,marginBlock:10},
};
const ACCESSIBILITY_CSS = '.madar-ai-usage :is(button,input,select):focus-visible{'
  +'outline:3px solid var(--vs-accent,#4b84bd);outline-offset:3px}'
  +'.madar-ai-usage :is(button,input,select):disabled{opacity:.7;cursor:not-allowed}';

export function parseBudgetInteger(value,max){
  if(typeof value!=='string'||!/^(0|[1-9][0-9]{0,12})$/.test(value)
    ||!Number.isSafeInteger(max))return null;
  const n=Number(value);
  return Number.isSafeInteger(n)&&n<=max?n:null;
}
export function validateAiBudgetDraft(draft,provider){
  if(!draft||!PROVIDERS.some(([name])=>name===provider)
    ||typeof draft.enabled!=='boolean'||typeof draft.cloudEnabled!=='boolean'
    ||(draft.cloudEnabled&&(!CLOUD.has(provider)||!draft.enabled)))return null;
  const numbers=Object.fromEntries(Object.keys(MAX).map(key=>[
    key,parseBudgetInteger(draft[key],MAX[key])]));
  if(Object.values(numbers).some(value=>value===null))return null;
  return {enabled:draft.enabled,cloudEnabled:CLOUD.has(provider)&&draft.cloudEnabled,...numbers};
}
export function normalizeAiGrant(raw,provider){
  if(raw===null)return {version:0,...EMPTY};
  if(!raw||typeof raw!=='object'||Array.isArray(raw)
    ||raw.provider!==provider||!Number.isSafeInteger(raw.version)||raw.version<1
    ||typeof raw.enabled!=='boolean'||typeof raw.cloud_enabled!=='boolean'
    ||(!CLOUD.has(provider)&&raw.cloud_enabled))return null;
  const fields=[['monthlyRequests',raw.monthly_requests],
    ['monthlyTokens',raw.monthly_tokens],['monthlyCostMicro',raw.monthly_cost_micro]];
  if(fields.some(([key,value])=>!Number.isSafeInteger(value)||value<0||value>MAX[key]))
    return null;
  return {version:raw.version,enabled:raw.enabled,cloudEnabled:raw.cloud_enabled,
    monthlyRequests:String(raw.monthly_requests),monthlyTokens:String(raw.monthly_tokens),
    monthlyCostMicro:String(raw.monthly_cost_micro)};
}
export function validatePreverifiedCloudIntent(intent,projectId){
  if(!intent||typeof intent!=='object'||Array.isArray(intent)
    ||Object.keys(intent).length!==5||intent.preverified!==true
    ||typeof projectId!=='string'||!ID.test(projectId)
    ||intent.projectId!==projectId||!CLOUD.has(intent.provider)
    ||typeof intent.requestId!=='string'||!RID.test(intent.requestId)
    ||typeof intent.payloadDigest!=='string'||!HASH.test(intent.payloadDigest))
    return null;
  return {provider:intent.provider,projectId,requestId:intent.requestId,
    payloadDigest:intent.payloadDigest};
}
function accountsFor(users){
  if(!Array.isArray(users)||users.length>200)return null;
  const seen=new Set(),eligible=[];
  for(const user of users){
    if(!user||typeof user!=='object'||Array.isArray(user)
      ||typeof user.username!=='string'||!ID.test(user.username)
      ||!['admin','editor','viewer'].includes(user.role)||seen.has(user.username))
      return null;
    seen.add(user.username);
    if(user.role!=='viewer')eligible.push({id:user.username,role:user.role});
  }
  return eligible;
}
function resultOf(response,action,expectedGrantScope=null){
  if(!response||typeof response!=='object'||Array.isArray(response)
    ||response.schemaVersion!==1||response.action!==action
    ||!Object.prototype.hasOwnProperty.call(response,'result'))
    throw new Error('invalid_host_result');
  if(expectedGrantScope!==null){
    const scope=response.grantScope;
    if(!scope||typeof scope!=='object'||Array.isArray(scope)
      ||Object.keys(scope).length!==3
      ||scope.projectId!==expectedGrantScope.projectId
      ||scope.userId!==expectedGrantScope.userId
      ||scope.provider!==expectedGrantScope.provider)
      throw new Error('invalid_host_grant_scope');
  }
  return response.result;
}
function safeError(error){
  const code=error&&typeof error.code==='string'?error.code:'';
  return ERROR_TEXT[code]||'عملیات تأیید نشد. وضعیت را از میزبان دوباره بررسی کنید.';
}
function newEventId(){
  return typeof globalThis.crypto?.randomUUID==='function'
    ?'ai-ui-'+globalThis.crypto.randomUUID():null;
}

/** Default RTL. Optional dir="ltr" mirrors the layout without altering data. */
export function AiUsageAdminPanel({
  command,projectId,isAdmin=false,users=[],cloudConsent=null,dir='rtl',
}){
  const uid=useId();
  const ready=typeof command==='function'&&typeof projectId==='string'&&ID.test(projectId);
  const accounts=accountsFor(users),manage=ready&&isAdmin===true&&accounts!==null;
  const [user,setUser]=useState(''),[provider,setProvider]=useState('local_ollama');
  const [loaded,setLoaded]=useState(null),[draft,setDraft]=useState({...EMPTY});
  const [status,setStatus]=useState(null),[busy,setBusy]=useState(false);
  const [consentCheck,setConsentCheck]=useState(null);
  const [consentStatus,setConsentStatus]=useState(null);
  const pending=useRef(false),saveEvent=useRef(null),consentEvent=useRef(null);
  const completedConsents=useRef(new Set());
  const scopeRef=useRef(''),intentRef=useRef('');
  const target=manage&&accounts.some(entry=>entry.id===user);
  const scope=target?JSON.stringify([projectId,user,provider]):'';
  const hasLoaded=!!scope&&loaded?.scope===scope;
  const validated=validateAiBudgetDraft(draft,provider);
  const intent=ready?validatePreverifiedCloudIntent(cloudConsent,projectId):null;
  const intentKey=intent?JSON.stringify([projectId,intent.provider,
    intent.requestId,intent.payloadDigest]):'';
  scopeRef.current=scope;intentRef.current=intentKey;
  const consentAccepted=consentCheck?.key===intentKey&&consentCheck.checked===true;
  const recorded=!!intentKey&&completedConsents.current.has(intentKey);

  function select(nextUser,nextProvider){
    scopeRef.current='';setUser(nextUser);setProvider(nextProvider);
    setLoaded(null);setDraft({...EMPTY});setStatus(null);saveEvent.current=null;
  }
  function edit(key,value){
    setDraft(old=>({...old,[key]:value,
      ...(key==='enabled'&&!value?{cloudEnabled:false}:{})}));
    saveEvent.current=null;setStatus(null);
  }
  async function read(){
    if(!target||pending.current)return;
    pending.current=true;setBusy(true);
    const current=scope;
    setStatus({scope,kind:'status',text:'در حال دریافت مجوز از میزبان…'});
    try{
      const raw=resultOf(await command('grant_get',{userId:user,provider},projectId),
        'grant_get',{projectId,userId:user,provider});
      const next=normalizeAiGrant(raw,provider);
      if(!next)throw Error('invalid_grant_snapshot');
      if(scopeRef.current!==current)return;
      setLoaded({scope:current,version:next.version});
      setDraft({enabled:next.enabled,cloudEnabled:next.cloudEnabled,
        monthlyRequests:next.monthlyRequests,monthlyTokens:next.monthlyTokens,
        monthlyCostMicro:next.monthlyCostMicro});
      saveEvent.current=null;
      setStatus({scope,kind:'status',text:'مجوز از میزبان دریافت شد.'});
    }catch(error){
      if(scopeRef.current===current){
        setLoaded(null);setStatus({scope,kind:'error',text:safeError(error)});
      }
    }finally{pending.current=false;setBusy(false);}
  }
  async function save(){
    if(!target||!hasLoaded||!validated||pending.current)return;
    const current=scope,version=loaded.version;
    const data={userId:user,provider,...validated,expectedVersion:version};
    const key=JSON.stringify([projectId,data]);
    if(!saveEvent.current||saveEvent.current.key!==key){
      const id=newEventId();
      if(!id){setStatus({scope,kind:'error',text:'شناسه امن عملیات در دسترس نیست.'});return;}
      saveEvent.current={key,id};
    }
    const id=saveEvent.current.id;
    pending.current=true;setBusy(true);
    setStatus({scope,kind:'status',text:'در حال ثبت نسخه جدید…'});
    try{
      const raw=resultOf(await command('grant_set',{...data,eventId:id},projectId),
        'grant_set',{projectId,userId:user,provider});
      const next=normalizeAiGrant(raw,provider);
      if(!next||next.version!==version+1
        ||next.enabled!==data.enabled||next.cloudEnabled!==data.cloudEnabled
        ||Number(next.monthlyRequests)!==data.monthlyRequests
        ||Number(next.monthlyTokens)!==data.monthlyTokens
        ||Number(next.monthlyCostMicro)!==data.monthlyCostMicro)
        throw Error('invalid_save_result');
      if(scopeRef.current!==current)return;
      setLoaded({scope:current,version:next.version});
      setDraft({enabled:next.enabled,cloudEnabled:next.cloudEnabled,
        monthlyRequests:next.monthlyRequests,monthlyTokens:next.monthlyTokens,
        monthlyCostMicro:next.monthlyCostMicro});
      saveEvent.current=null;
      setStatus({scope,kind:'status',text:'مجوز با نسخه جدید ثبت شد.'});
    }catch(error){
      if(scopeRef.current===current)setStatus({scope,kind:'error',text:safeError(error)});
    }finally{pending.current=false;setBusy(false);}
  }
  async function consent(){
    if(!ready||!intent||!consentAccepted||recorded||pending.current)return;
    const key=intentKey;
    if(!consentEvent.current||consentEvent.current.key!==key){
      const id=newEventId();
      if(!id){setConsentStatus({key,kind:'error',text:'شناسه امن عملیات در دسترس نیست.'});return;}
      consentEvent.current={key,id};
    }
    const id=consentEvent.current.id;
    pending.current=true;setBusy(true);
    setConsentStatus({key,kind:'status',text:'در حال ثبت قصد رضایت…'});
    try{
      const value=resultOf(await command('cloud_consent',{
        provider:intent.provider,requestId:intent.requestId,
        payloadDigest:intent.payloadDigest,eventId:id,
      },projectId),'cloud_consent');
      if(!['recorded','recorded_replay'].includes(value))throw Error('invalid_consent');
      completedConsents.current.add(key);
      if(intentRef.current!==key)return;
      setConsentCheck({key,checked:false});consentEvent.current=null;
      setConsentStatus({key,kind:'status',
        text:'قصد رضایت ثبت شد. هیچ متنی به ارائه‌دهنده ارسال نشد.'});
    }catch(error){
      if(intentRef.current===key)
        setConsentStatus({key,kind:'error',text:safeError(error)});
    }finally{pending.current=false;setBusy(false);}
  }

  return <section className="madar-ai-usage" style={S.base}
    dir={dir==='ltr'?'ltr':'rtl'} aria-labelledby={uid+'-title'}>
    <style>{ACCESSIBILITY_CSS}</style>
    <h2 id={uid+'-title'}>کنترل مجوز و سهمیه هوش مصنوعی</h2>
    <p style={S.muted}>این صفحه فقط مجوز و قصد رضایت را ثبت می‌کند.
      هیچ مدل، سرویس خارجی یا هزینه‌ای از اینجا اجرا نمی‌شود.</p>
    {!ready&&<p style={S.status} role="alert">اتصال میزبان یا شناسه معتبر
      پروژه در دسترس نیست. عملیات غیرفعال است.</p>}
    {isAdmin===true&&<section style={S.card} aria-labelledby={uid+'-admin'}>
      <h3 id={uid+'-admin'}>سیاست مصرف کاربران</h3>
      <p style={S.muted}>حساب و ارائه‌دهنده را انتخاب کنید؛ سپس نسخه مجوز
        را بخوانید. ذخیره با کنترل نسخه انجام می‌شود.</p>
      {accounts===null?<p role="alert">فهرست حساب‌ها معتبر نیست؛ ویرایش غیرفعال است.</p>
        :accounts.length===0?<p role="status">حساب واجد شرایطی وجود ندارد.</p>
          :<>
            <div style={S.grid}>
              <label style={S.label} htmlFor={uid+'-user'}>حساب کاربری
                <select id={uid+'-user'} style={S.input}
                  disabled={!manage||busy} value={target?user:''}
                  onChange={e=>select(e.target.value,provider)}>
                  <option value="">انتخاب حساب…</option>
                  {accounts.map(a=><option key={a.id} value={a.id}>
                    {a.id} · {a.role==='admin'?'مدیر':'ویرایشگر'}
                  </option>)}
                </select>
              </label>
              <label style={S.label} htmlFor={uid+'-provider'}>ارائه‌دهنده
                <select id={uid+'-provider'} style={S.input} value={provider}
                  disabled={!manage||busy}
                  onChange={e=>select(user,e.target.value)}>
                  {PROVIDERS.map(([value,title])=>
                    <option key={value} value={value}>{title}</option>)}
                </select>
              </label>
            </div>
            <div style={S.actions}>
              <button type="button" style={S.button}
                disabled={!target||busy} onClick={read}>خواندن مجوز</button>
              {hasLoaded&&<output dir="ltr" aria-label="نسخه فعلی مجوز">
                CAS v{loaded.version}</output>}
            </div>
            <fieldset disabled={!hasLoaded||busy} aria-label="حدود مجاز مصرف">
              <legend>محدودیت‌های ماهانه</legend>
              <label style={S.line}><input type="checkbox" checked={draft.enabled}
                onChange={e=>edit('enabled',e.target.checked)}/>
                فعال بودن مجوز AI این ارائه‌دهنده</label>
              {CLOUD.has(provider)&&<label style={S.line}>
                <input type="checkbox" checked={draft.cloudEnabled}
                  disabled={!draft.enabled||!hasLoaded||busy}
                  onChange={e=>edit('cloudEnabled',e.target.checked)}/>
                اجازه استفاده ابری (هر ارسال رضایت جداگانه می‌خواهد)
              </label>}
              <div style={S.grid}>{[
                ['monthlyRequests','سقف درخواست در ماه'],
                ['monthlyTokens','سقف توکن در ماه'],
                ['monthlyCostMicro','سقف هزینه در ماه (میکروواحد سیاست)'],
              ].map(([key,label])=><label style={S.label}
                htmlFor={uid+'-'+key} key={key}>{label}
                <input id={uid+'-'+key} style={S.input} type="text"
                  inputMode="numeric" pattern="[0-9]*" maxLength={13}
                  autoComplete="off" dir="ltr" value={draft[key]}
                  aria-invalid={hasLoaded&&parseBudgetInteger(draft[key],MAX[key])===null}
                  onChange={e=>edit(key,e.target.value)}/>
              </label>)}</div>
              <p style={S.muted}>میکروواحد فقط سقف سیاست مصرف است؛
                مبلغ پرداخت، ارز یا صورت‌حساب واقعی نیست.</p>
            </fieldset>
            <button type="button" style={{...S.button,...S.primary}}
              disabled={!hasLoaded||!validated||busy} onClick={save}>
              ذخیره مجوز با کنترل نسخه</button>
            {status?.scope===scope&&<p style={S.status} aria-live="polite"
              role={status.kind==='error'?'alert':'status'}>{status.text}</p>}
          </>}
    </section>}
    <section style={S.card} aria-labelledby={uid+'-consent'}>
      <h3 id={uid+'-consent'}>رضایت برای انتقال ابری</h3>
      {intent?<>
        <p style={S.muted}>قصد رضایت برای همین درخواست و
          ارائه‌دهنده {PROVIDERS.find(([id])=>id===intent.provider)?.[1]} است.
          متن، شناسه درخواست و اثرانگشت آن در این صفحه نمایش داده نمی‌شوند.</p>
        <label style={S.line}><input type="checkbox" checked={consentAccepted}
          disabled={busy||recorded}
          onChange={e=>{
            setConsentCheck({key:intentKey,checked:e.target.checked});
            setConsentStatus(null);
          }}/>
          تأیید می‌کنم قصد ثبت رضایت برای همین درخواست را دارم.</label>
        <button type="button" style={{...S.button,...S.primary}}
          disabled={!ready||busy||!consentAccepted||recorded} onClick={consent}>
          ثبت قصد رضایت (بدون ارسال)</button>
        {consentStatus?.key===intentKey&&<p style={S.status} aria-live="polite"
          role={consentStatus.kind==='error'?'alert':'status'}>
          {consentStatus.text}</p>}
      </>:<p role="status" style={S.muted}>
        درخواست ابری پیش‌بررسی‌شده در دسترس نیست؛ هیچ رضایتی ثبت نمی‌شود.</p>}
    </section>
  </section>;
}
export default AiUsageAdminPanel;
