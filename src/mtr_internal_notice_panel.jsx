import React, {useId, useRef, useState} from 'react';

/**
 * UNMOUNTED opt-in E6 inbox pilot, independent from App.jsx and ordinary
 * collaboration notifications. Never fetches, marks or publishes on mount.
 *
 * command({schemaVersion:1, action, params}) MUST be injected by the trusted
 * authenticated host UI bridge, which owns the pinned-TLS transport, bearer
 * session, server project/recipient ACL and timeout. This component does NOT
 * authenticate the callback or use a browser network API.
 *
 * The host endpoint offers only projectId+limit, no offset/cursor. Pages below
 * are local slices of at most 100 freshly read notices, not a complete archive.
 * The LAN response has no project-scope echo. Check each returned row's scope
 * and ignore late responses, but independently enforce grants at the host.
 */
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,179}$/;
const LABELS = Object.freeze({
  request_status_changed: 'تغییر وضعیت درخواست',
  deficiency_assigned: 'ارجاع مورد نیاز به پیگیری',
  amendment_status_changed: 'تغییر وضعیت اصلاحیه',
});
const STYLE = {
  outer: {maxWidth:880,color:'var(--vs-ink,#192637)',
    background:'var(--vs-glass,#f6f8fa)',
    border:'1px solid var(--vs-edge,#b6bfcb)',borderRadius:18,padding:18},
  small: {color:'var(--vs-muted,#455369)',lineHeight:1.8},
  row: {display:'flex',flexWrap:'wrap',gap:12,alignItems:'center',marginBlock:14},
  button: {font:'inherit',minHeight:40,padding:'8px 14px',
    color:'var(--vs-ink,#192637)',
    background:'var(--vtr-glass-thick,#fff)',
    border:'1px solid var(--vs-edge,#b6bfcb)',borderRadius:10,cursor:'pointer'},
  item: {border:'1px solid var(--vs-edge,#b6bfcb)',borderRadius:12,
    padding:12,marginBlock:10,background:'var(--vtr-glass-thick,#fff)'},
  badge: {fontSize:13,color:'var(--vs-muted,#455369)'},
};
const FOCUS = '.mtr-internal-notices button:focus-visible{'
  +'outline:3px solid var(--vs-accent,#4b84bd);outline-offset:2px}'
  +'.mtr-internal-notices button:disabled{opacity:.6;cursor:not-allowed}';

function validProject(projectId){return typeof projectId==='string'&&ID.test(projectId);}
function validBounds(limit,pageSize){
  return Number.isInteger(limit)&&1<=limit&&limit<=100
    &&Number.isInteger(pageSize)&&1<=pageSize&&pageSize<=20&&pageSize<=limit;
}
function replyResult(response){
  if(!response||typeof response!=='object'||Array.isArray(response)
    ||Object.keys(response).length!==2||response.schemaVersion!==1
    ||!Object.prototype.hasOwnProperty.call(response,'result'))
    throw Error('invalid_host_envelope');
  return response.result;
}

/**
 * Only carry presentation-safe fields forward. The backend also returns
 * optional actor/status/amendment/summary and internal request identifiers;
 * NEVER render or keep those fields in component state.
 */
export function safeNoticeList(response,projectId,limit){
  if(!validProject(projectId)||!Number.isInteger(limit)||limit<1||limit>100)
    throw Error('invalid_scope');
  const result=replyResult(response);
  if(!Array.isArray(result)||result.length>limit)throw Error('invalid_host_list');
  const seen=new Set();
  return result.map(row=>{
    if(!row||typeof row!=='object'||Array.isArray(row)
      ||row.project_id!==projectId||row.channel!=='internal_only'
      ||!Number.isSafeInteger(row.notice_id)||row.notice_id<1
      ||seen.has(row.notice_id)||!Object.hasOwn(LABELS,row.event_kind)
      ||typeof row.is_read!=='boolean'
      ||!(row.read_at===null
        ||typeof row.read_at==='string'&&row.read_at.length>0&&row.read_at.length<=80)
      ||row.is_read!==(row.read_at!==null)){
      throw Error('invalid_or_foreign_notice');
    }
    seen.add(row.notice_id);
    return {id:row.notice_id,kind:row.event_kind,read:row.is_read};
  });
}

export function safeMarkReadResult(response,expectedId){
  const result=replyResult(response);
  if(!result||typeof result!=='object'||Array.isArray(result)
    ||Object.keys(result).length!==3
    ||result.notice_id!==expectedId
    ||typeof result.marked_read!=='boolean'
    ||typeof result.already_read!=='boolean'
    ||result.marked_read===result.already_read)
    throw Error('invalid_host_ack');
  return true;
}

export function MtrInternalNoticePanel({
  command,projectId,limit=50,pageSize=10,dir='rtl',
}){
  const uid=useId();
  const ready=typeof command==='function'
    &&validProject(projectId)&&validBounds(limit,pageSize);
  // Track callback identity by reference: replacing the authenticated bridge
  // invalidates any previously loaded rows, even for the same project.
  const currentRef=useRef({projectId,limit,pageSize,command});
  const generation=useRef(0),pending=useRef(false),completed=useRef(new Set());
  const [loaded,setLoaded]=useState(null),[page,setPage]=useState(0);
  const [busy,setBusy]=useState(false),[feedback,setFeedback]=useState(null);
  const current=currentRef.current;
  if(current.projectId!==projectId||current.limit!==limit
    ||current.pageSize!==pageSize||current.command!==command){
    currentRef.current={projectId,limit,pageSize,command};
    generation.current+=1;
  }
  const revision=generation.current;
  const visible=ready&&loaded?.projectId===projectId
    &&loaded.limit===limit&&loaded.pageSize===pageSize
    &&loaded.command===command&&loaded.generation===revision ?loaded.items:null;
  const total=visible?.length||0;
  const pageCount=Math.max(1,Math.ceil(total/pageSize||1));
  const actualPage=Math.min(page,pageCount-1);
  const rows=visible?.slice(actualPage*pageSize,(actualPage+1)*pageSize)||[];
  const liveFeedback=feedback?.projectId===projectId&&feedback.revision===revision
    ?feedback:null;
  const working=pending.current||busy;

  async function load(){
    if(!ready||pending.current||revision!==generation.current)return;
    pending.current=true;setBusy(true);
    const token=generation.current;
    setFeedback(null);setLoaded(null);
    try{
      const response=await command({
        schemaVersion:1,action:'list',params:{projectId,limit},
      });
      const items=safeNoticeList(response,projectId,limit);
      if(token!==generation.current)return;
      completed.current.clear();setLoaded({
        projectId,limit,pageSize,command,generation:token,items,
      });
      setPage(0);
      setFeedback({projectId,revision:token,error:false,
        text:'فهرست محدود اعلان‌های داخلی دریافت شد.'});
    }catch{
      if(token===generation.current){
        setLoaded(null);
        setFeedback({projectId,revision:token,error:true,
          text:'دریافت اعلان‌های این پروژه تأیید نشد. اتصال یا دسترسی میزبان را بررسی کنید.'});
      }
    }finally{
      pending.current=false;setBusy(false);
    }
  }

  async function mark(item){
    if(!ready||pending.current||revision!==generation.current||!visible||item.read
      ||!visible.some(row=>row.id===item.id&&!row.read)
      ||completed.current.has(item.id))return;
    pending.current=true;setBusy(true);
    const token=generation.current;
    setFeedback(null);
    try{
      const response=await command({
        schemaVersion:1,action:'mark-read',
        params:{noticeId:item.id,manualAction:true},
      });
      safeMarkReadResult(response,item.id);
      if(token!==generation.current)return;
      completed.current.add(item.id);
      setLoaded(old=>old?.projectId===projectId&&old?.command===command
        &&old?.generation===token
        ?{...old,items:old.items.map(row=>row.id===item.id?{...row,read:true}:row)}
        :old);
      setFeedback({projectId,revision:token,error:false,
        text:'اعلان در میزبان به‌عنوان خوانده‌شده ثبت شد.'});
    }catch{
      if(token===generation.current){
        setFeedback({projectId,revision:token,error:true,
          text:'ثبت خوانده‌شدن تأیید نشد؛ برای اطمینان فهرست را دوباره دریافت کنید.'});
      }
    }finally{
      pending.current=false;setBusy(false);
    }
  }

  return <section className="mtr-internal-notices" style={STYLE.outer}
    dir={dir==='ltr'?'ltr':'rtl'} aria-labelledby={uid+'-heading'}>
    <style>{FOCUS}</style>
    <h2 id={uid+'-heading'}>صندوق اعلان‌های داخلی</h2>
    <p style={STYLE.small}>فقط اعلان‌های ثبت‌شده در میزبان این پروژه.
      هیچ پیامک، ایمیل، سرویس ابری یا اقدام مالی ارسال نمی‌شود.
      دریافت و خوانده‌کردن هر دو دستی هستند.</p>
    {!ready&&<p role="alert">پروژه، حدود فهرست یا اتصال فرمان احراز‌شدهٔ میزبان معتبر نیست؛
      عملیات غیرفعال است.</p>}
    <div style={STYLE.row}>
      <button type="button" style={STYLE.button} disabled={!ready||working}
        onClick={load}>دریافت اعلان‌ها</button>
      {visible&&<span style={STYLE.badge} aria-live="polite">
        {total.toLocaleString('fa-IR')} اعلان از حداکثر {limit.toLocaleString('fa-IR')} مورد اخیر
      </span>}
    </div>
    {working&&<p role="status" aria-live="polite">در حال تأیید درخواست نزد میزبان…</p>}
    {liveFeedback&&<p role={liveFeedback.error?'alert':'status'} aria-live="polite">
      {liveFeedback.text}</p>}
    {visible&&<div>
      {rows.map(item=><article key={item.id} style={STYLE.item}
        aria-label={LABELS[item.kind]}>
        <div style={STYLE.row}>
          <strong>{LABELS[item.kind]}</strong>
          <span style={STYLE.badge}>{item.read?'خوانده‌شده':'خوانده‌نشده'}</span>
        </div>
        {!item.read&&<button type="button" style={STYLE.button}
          disabled={working||completed.current.has(item.id)}
          onClick={()=>mark(item)}>خوانده شد</button>}
      </article>)}
      {total===0&&<p role="status">در این محدوده اعلانی برای نمایش نیست.</p>}
      {pageCount>1&&<nav style={STYLE.row} aria-label="صفحه‌بندی اعلان‌های داخلی">
        <button type="button" style={STYLE.button}
          disabled={working||actualPage===0}
          onClick={()=>setPage(n=>Math.max(0,n-1))}>صفحه قبل</button>
        <span aria-live="polite">صفحه {(actualPage+1).toLocaleString('fa-IR')}
          از {pageCount.toLocaleString('fa-IR')}</span>
        <button type="button" style={STYLE.button}
          disabled={working||actualPage>=pageCount-1}
          onClick={()=>setPage(n=>Math.min(pageCount-1,n+1))}>صفحه بعد</button>
      </nav>}
      <p style={STYLE.small}>صفحه‌بندی فقط روی موارد دریافت‌شده است؛
        این endpoint صفحه‌های قدیمی‌تر را دریافت نمی‌کند.</p>
    </div>}
  </section>;
}

export default MtrInternalNoticePanel;
