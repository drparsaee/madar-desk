'use strict';

// Pure, independently testable UX acceptance decisions. No passing score is
// emitted for an absent feature, skipped browser audit, or unknown outcome.
const UX_IDS=Object.freeze(Array.from({length:10},(_,index)=>
  'UX-'+String(index+1).padStart(2,'0')));
const STATUSES=Object.freeze(['PASS','FAIL','MISSING','BLOCKED']);

function observation(id,status,evidence,context={}){
  if(!UX_IDS.includes(id))throw Error('Unknown UX criterion: '+id);
  if(!STATUSES.includes(status))throw Error('Invalid audit status: '+status);
  if(!evidence||typeof evidence!=='string')throw Error('Audit evidence required');
  return {id,status,evidence,...context};
}

function assessAxe(audit){
  if(!audit||audit.version!=='4.14.0')return {status:'BLOCKED',severe:[],reason:'axe-core 4.14.0 unavailable or not executed'};
  const severe=(audit.violations||[]).filter(item=>
    ['serious','critical'].includes(item.impact));
  return {status:severe.length?'FAIL':'PASS',severe,
    incomplete:(audit.incomplete||[]).length,
    reason:severe.length?'serious/critical axe violations':'No serious/critical axe violations in measured DOM'};
}

function assessContrast(samples){
  if(!Array.isArray(samples)||!samples.length)return {status:'BLOCKED',reason:'No computed content text contrast samples'};
  const unresolved=samples.filter(item=>!Number.isFinite(item.ratio));
  const failures=samples.filter(item=>Number.isFinite(item.ratio)&&item.ratio<4.5);
  return {status:failures.length?'FAIL':unresolved.length?'BLOCKED':'PASS',
    sampleCount:samples.length,failures,unresolved,
    reason:failures.length?'Ordinary text below project 4.5:1 requirement':
      unresolved.length?'Some content backgrounds could not be measured':'All sampled content text at least 4.5:1'};
}

function assessTouch(targets){
  if(!Array.isArray(targets)||!targets.length)return {status:'BLOCKED',reason:'No critical touch targets measured'};
  const failures=targets.filter(item=>item.width<44||item.height<44);
  return {status:failures.length?'FAIL':'PASS',failures,measured:targets.length,
    reason:failures.length?'Critical target below project 44x44 CSS px goal':'All measured critical targets meet 44px goal'};
}

function summarize(checks){
  const groups=Object.fromEntries(UX_IDS.map(id=>[id,[]]));
  for(const check of checks){
    if(!groups[check.id])throw Error('Unknown result: '+check.id);
    groups[check.id].push(check);
  }
  const statusByUX=Object.fromEntries(UX_IDS.map(id=>{
    const entries=groups[id];
    const status=entries.some(e=>e.status==='FAIL')?'FAIL':
      entries.some(e=>e.status==='MISSING')?'MISSING':
      entries.some(e=>e.status==='BLOCKED')?'BLOCKED':
      entries.length?'PASS':'BLOCKED';
    return [id,{status,checks:entries.length}];
  }));
  const totals=Object.fromEntries(STATUSES.map(s=>[s,
    Object.values(statusByUX).filter(item=>item.status===s).length]));
  return {statusByUX,totals,overall:totals.FAIL||totals.MISSING?'FAIL':totals.BLOCKED?'BLOCKED':'PASS'};
}

module.exports={UX_IDS,observation,assessAxe,assessContrast,assessTouch,summarize};
