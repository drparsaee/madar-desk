import React,{useMemo,useRef,useState} from 'react';

function newRequestId(){
  const rng=globalThis.crypto?.getRandomValues;
  if(typeof rng!=='function')throw Error('شناسه امن درخواست در این دستگاه در دسترس نیست.');
  const bytes=new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes,x=>x.toString(16).padStart(2,'0')).join('');
}

const validHex=value=>typeof value==='string'&&/^[0-9a-f]{32}$/.test(value);

export default function TarazCustomerPicker({api,task,username='',canEdit=false,onUpdate}){
  const [expanded,setExpanded]=useState(false);
  const [adminUser,setAdminUser]=useState(username||'');
  const [adminPassword,setAdminPassword]=useState('');
  const [companyId,setCompanyId]=useState(task.tarazCustomerRef?.companyId||task.tarazCustomerRequest?.companyId||'');
  const [install,setInstall]=useState(task.tarazCustomerRef?.installationId||task.tarazCustomerRequest?.installationId||'');
  const [keyId,setKeyId]=useState('');
  const [connections,setConnections]=useState([]);
  const [confirmed,setConfirmed]=useState(false);
  const [query,setQuery]=useState('');
  const [attempt,setAttempt]=useState(null);
  const [pending,setPending]=useState(task.tarazCustomerRequest||null);
  const [page,setPage]=useState(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const current=task.tarazCustomerRef;
  const available=['integrationMailboxConnections','integrationMailboxApproveCompany',
    'integrationMailboxEnqueue','integrationMailboxReconcile']
    .every(name=>typeof api?.[name]==='function');
  const credentials=()=>({username:adminUser,password:adminPassword});
  const active=pending||task.tarazCustomerRequest;
  const chosen=useMemo(()=>connections.find(x=>x.keyId===keyId&&x.status==='active'&&x.product==='TARAZ'),[connections,keyId]);
  const perform=async action=>{
    if(loading)return;
    setError('');setNotice('');setLoading(true);
    try{await action();}catch(e){
      // A remote/offline error must never be mistaken for cached current data.
      setError('درخواست انجام نشد. اتصال HTTPS، مجوز مدیر، شرکت ثبت‌شده و اجرای تراز را بررسی کنید.');
    }finally{setLoading(false);}
  };
  const load=()=>perform(async()=>{
    const answer=await api.integrationMailboxConnections(credentials());
    const peers=(answer?.connections||[]).filter(x=>x.product==='TARAZ'&&x.status==='active');
    setConnections(peers);
    if(!peers.some(x=>x.keyId===keyId))setKeyId(peers[0]?.keyId||'');
    setInstall(value=>value||peers[0]?.installationId||'');
    setNotice(peers.length?'نصب‌های تراز شناسایی شدند. برای دسترسی به شرکت مشخص، تأیید مجزای مدیر لازم است.':'نصب فعالی از تراز پیدا نشد. ابتدا Pairing را تکمیل کنید.');
  });
  const approve=()=>perform(async()=>{
    if(!confirmed||!chosen||!validHex(companyId))throw Error('company approval required');
    await api.integrationMailboxApproveCompany(credentials(),{
      keyId:chosen.keyId,companyId,installationId:chosen.installationId,
      manualConfirmation:true});
    setInstall(chosen.installationId);
    setNotice('مجوز مستقل این شرکت برای همین نصب تراز ثبت شد.');
  });
  const search=()=>perform(async()=>{
    if(!query.trim()||query.length>120||!validHex(companyId)||!validHex(install))
      throw Error('invalid search');
    const identity=JSON.stringify([companyId,install,query.trim()]);
    const requestId=attempt?.identity===identity?attempt.requestId:newRequestId();
    setAttempt({identity,requestId});
    const answer=await api.integrationMailboxEnqueue(credentials(),{
      companyId,installationId:install,requestId,query:query.trim(),
      kind:'customer',limit:10,cursor:null});
    const request={workspaceId:answer.workspaceId,companyId,installationId:install,requestId};
    if(!validHex(request.workspaceId))throw Error('invalid authoritative workspace');
    setPending(request);setPage(null);
    onUpdate({tarazCustomerRequest:request});
    setNotice('درخواست در صندوق پایدار مدار ثبت شد. تراز باید «پردازش درخواست‌های مدار» را اجرا کند؛ سپس پاسخ را تازه‌سازی کنید.');
  });
  const refresh=()=>perform(async()=>{
    if(!active)throw Error('no request');
    const answer=await api.integrationMailboxReconcile(credentials(),{
      companyId:active.companyId,installationId:active.installationId,
      requestId:active.requestId,acknowledge:false});
    if(answer.status==='completed'&&answer.result&&Array.isArray(answer.result.parties)){
      setPage(answer.result);
      setNotice('پاسخ امضاشدهٔ تراز دریافت شد. این پاسخ مربوط به درخواست قبلی است، نه استعلام لحظه‌ای جدید.');
    }else{
      setPage(null);
      setNotice(answer.status==='expired'?'مهلت درخواست پایان یافته؛ جست‌وجوی جدید لازم است.':
        'درخواست هنوز در انتظار پاسخ تراز است. نتیجهٔ Cache شده نمایش داده نمی‌شود.');
    }
  });
  const select=party=>{
    if(!canEdit||!active||!page||!page.parties.includes(party)||
       !['customer','both'].includes(party.kind))return;
    onUpdate({tarazCustomerRef:{workspaceId:active.workspaceId,
      companyId:active.companyId,installationId:active.installationId,
      partyId:party.partyId,kind:party.kind},tarazCustomerRequest:null});
    setPending(null);setPage(null);setAttempt(null);
    setNotice('شناسه مشتری به کارت مرتبط شد. ذخیرهٔ کارت باید در وضعیت همگام‌سازی مدار تأیید شود.');
  };
  return <section className="edit-section taraz-customer-picker" aria-label="انتخاب مشتری از تراز">
    <div style={{display:'flex',gap:8,alignItems:'center',justifyContent:'space-between',flexWrap:'wrap'}}>
      <strong>انتخاب مشتری از تراز</strong>
      <button type="button" className="btn secondary" onClick={()=>setExpanded(x=>!x)} aria-expanded={expanded}>
        {expanded?'بستن جست‌وجو':'بازکردن جست‌وجو'}
      </button>
    </div>
    {current&&<p role="status">مشتری مرتبط: <code dir="ltr">{current.partyId}</code>
      <small> شناسهٔ داخلی تراز، شرکت: {current.companyId}. برای نام یا وضعیت فعلی، استعلام تازه انجام دهید.</small></p>}
    {!current&&<small>هنوز مشتری تأییدشده‌ای به این کارت متصل نیست.</small>}
    {expanded&&<div style={{display:'grid',gap:8,marginTop:10}}>
      {!available&&<p role="alert">نسخهٔ نصب‌شدهٔ مدار قابلیت جست‌وجوی عملیاتی تراز را ندارد.</p>}
      <label>نام مدیر میزبان<input value={adminUser} maxLength={40} autoComplete="username" onChange={e=>setAdminUser(e.target.value)}/></label>
      <label>رمز ورود مدیر<input type="password" value={adminPassword} autoComplete="off" onChange={e=>setAdminPassword(e.target.value)}/></label>
      <button type="button" disabled={!available||loading||!adminUser||!adminPassword} onClick={load}>بررسی نصب‌های Pairشده</button>
      {connections.length>0&&<label>نصب تراز<select value={keyId} onChange={e=>{
        setKeyId(e.target.value);setInstall(connections.find(p=>p.keyId===e.target.value)?.installationId||'');setConfirmed(false);
      }}><option value="">انتخاب نصب</option>{connections.map(p=><option key={p.keyId} value={p.keyId}>{p.installationId} | {p.username}</option>)}</select></label>}
      <label>شناسهٔ ۳۲رقمی شرکت از داخل تراز<input dir="ltr" value={companyId} maxLength={32} placeholder="companyId" onChange={e=>setCompanyId(e.target.value.toLowerCase())}/></label>
      {chosen&&<><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>
        شناسهٔ شرکت را با اطلاعات همان شرکت در تراز مستقل تطبیق دادم.</label>
        <button type="button" disabled={!confirmed||loading||!validHex(companyId)} onClick={approve}>تأیید مجوز شرکت</button></>}
      <label>جست‌وجوی نام مشتری<input aria-label="جست‌وجوی مشتری تراز" value={query} maxLength={120} onChange={e=>setQuery(e.target.value)}/></label>
      <button type="button" disabled={!canEdit||!available||loading||!validHex(companyId)||!validHex(install)||!query.trim()}
        onClick={search}>ثبت درخواست جست‌وجو در Mailbox</button>
      {active&&<><small>شناسهٔ درخواست پایدار: <code dir="ltr">{active.requestId}</code></small>
        <button type="button" disabled={loading||!available} onClick={refresh}>دریافت پاسخ امضاشدهٔ تراز</button></>}
      {page&&<div role="region" aria-label="نتایج درخواست تأییدشدهٔ تراز">
        {page.parties.length===0?<p>برای این درخواست مشتری‌ای یافت نشد.</p>:
          page.parties.map(p=><div key={p.partyId} style={{display:'flex',gap:8,justifyContent:'space-between',alignItems:'center'}}>
            <span>{p.name} <code dir="ltr">{p.partyId}</code></span>
            <button type="button" disabled={!canEdit} onClick={()=>select(p)}>انتخاب</button>
          </div>)}
        {page.hasMore&&<small>نتایج بیشتر وجود دارد؛ برای صفحهٔ بعد درخواست جدید با Cursor مجاز لازم است.</small>}
      </div>}
      {notice&&<p role="status">{notice}</p>}
      {error&&<p role="alert">{error}</p>}
      <small>هیچ مانده، هزینه، شماره تماس یا تاریخچهٔ مالی منتقل نمی‌شود. جست‌وجوی صف‌شده پاسخ زنده محسوب نمی‌شود.</small>
    </div>}
  </section>;
}
