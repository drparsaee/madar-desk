const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const target = pathToFileURL(path.resolve(__dirname,'../src/standalone_order_adapter.js')).href;

test('task handoff sends only immutable reference IDs, no financial fields',async()=>{
  const {prepareStandaloneFromTask} = await import(target);
  let sent;
  const api={standaloneAccountingPrepare:async request=>{
    sent=request;
    return {id:'sale.abc',existing:false};
  }};
  const task={id:'task.1',title:'کتاب',description:'۴۰۰ صفحه محرمانه',
    saleUnitPrice:999999,salePartyId:'private',checklist:[]};
  assert.deepEqual(await prepareStandaloneFromTask(api,{task}),{id:'sale.abc',existing:false});
  assert.deepEqual(sent,{taskId:'task.1',expenseId:null});
  await prepareStandaloneFromTask(api,{task,expense:{id:'cost.1',
    unitPrice:150000,partyId:'vendor',description:'pocket'}});
  assert.deepEqual(sent,{taskId:'task.1',expenseId:'cost.1'});
});

test('no fallback to caller-selected financial command or malformed IDs',async()=>{
  const {prepareStandaloneFromTask} = await import(target);
  await assert.rejects(()=>prepareStandaloneFromTask({
    standaloneAccountingCommand:async()=>({})},{task:{id:'task.1'}}),/میزبان/);
  await assert.rejects(()=>prepareStandaloneFromTask({
    standaloneAccountingPrepare:async()=>({id:'x',existing:false})},
    {task:{id:'../bad'}}),/شناسه/);
});
