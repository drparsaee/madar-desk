'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const fs=require('node:fs');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'..');
const entry=path.join(root,'src','standalone_accounting_workspace.jsx');
const compiled=esbuild.buildSync({entryPoints:[entry],bundle:true,platform:'node',format:'cjs',
  write:false,jsx:'automatic',loader:{'.css':'empty','.jpg':'dataurl'},
  external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const virtual=path.join(root,'tests','wizard-virtual.cjs');
const shim=new Module(virtual,module);shim.filename=virtual;
shim.paths=Module._nodeModulePaths(path.dirname(virtual));
shim._compile(compiled,virtual);
const {invoiceWizardIssues,buildStandaloneInvoiceCommand}=shim.exports;
const accounts={'4000':{id:'4000',name:'Sales',kind:'revenue'}};
const today='2026-11-03';
const valid={document:{documentId:'INV-1405-0001',partyId:'CUSTOMER-QA',
  documentDate:today,dueDate:'',discount:'0',tax:'0',taxRuleId:'',note:''},
  rows:[{description:'خدمت آزمایشی',quantity:'2',unitPrice:'100',
    accountId:'4000',itemId:''}],
  accounts,items:{},today,kind:'invoice',tax:'0'};

test('guided stages validate only their actual inputs while the ledger builder gates final submission',()=>{
  assert.deepEqual(invoiceWizardIssues(valid),['','','','','']);
  assert.equal(buildStandaloneInvoiceCommand({...valid,...valid.document,
    lines:valid.rows,eventId:'QA-WIZARD-PREFLIGHT'}).error,'');
  const missing=invoiceWizardIssues({...valid,document:{...valid.document,partyId:''}});
  assert.match(missing[0],/مشتری/);
  const broken=invoiceWizardIssues({...valid,rows:[{...valid.rows[0],description:'',quantity:'0'}]});
  assert.match(broken[1],/تعداد/);
  const costly=invoiceWizardIssues({...valid,document:{...valid.document,discount:'9999'}});
  assert.match(costly[2],/تخفیف/);
  const invalidDue=invoiceWizardIssues({...valid,document:{...valid.document,dueDate:'2026-11-01'}});
  assert.match(invalidDue[3],/سررسید/);
  const correction=invoiceWizardIssues({...valid,correctionTarget:'INV-OLD',
    correctionReason:'',correctionDate:today});
  assert.match(correction[0],/اصلاح/);
});

test('wizard view retains all stages mounted and gates only invoice draft submit',()=>{
  const jsx=fs.readFileSync(entry,'utf8');
  const css=fs.readFileSync(path.join(root,'src/standalone_accounting_ux20.css'),'utf8');
  const nav=fs.readFileSync(path.join(root,'src/accounting_invoice_wizard.jsx'),'utf8');
  for(const key of ['document','lines','tax','due','review']){
    assert.match(jsx,new RegExp('sac-wizard-panel-'+key));
    assert.match(nav,new RegExp('id:\''+key+'\''));
  }
  assert.match(jsx,/noValidate=\{wizardEnabled\}/);
  assert.match(jsx,/if\(!validateInvoiceSubmission\(\)\)return/);
  assert.match(jsx,/if\(correctionTarget&&!window\.confirm/);
  assert.match(jsx,/buildStandaloneInvoiceCommand/);
  assert.match(jsx,/invoiceWizardStep===4|invoiceWizardStep<4/);
  assert.match(css,/\[data-invoice-step\]\[hidden\]\{display:none!important\}/);
  assert.match(css,/min-height:44px/);
  assert.match(css,/position:sticky;bottom:0/);
});

test('invoice stage navigator has five named steps and accessible current-step state',()=>{
  const src=path.join(root,'src','accounting_invoice_wizard.jsx');
  const compiledNav=esbuild.buildSync({entryPoints:[src],bundle:true,platform:'node',
    format:'cjs',write:false,jsx:'automatic',
    external:['react','react/jsx-runtime']}).outputFiles[0].text;
  const n=new Module(path.join(root,'tests','nav-virtual.cjs'),module);
  n.filename=path.join(root,'tests','nav-virtual.cjs');
  n.paths=Module._nodeModulePaths(path.dirname(n.filename));
  n._compile(compiledNav,n.filename);
  assert.equal(n.exports.INVOICE_WIZARD_STEPS.length,5);
  const html=renderToStaticMarkup(React.createElement(n.exports.InvoiceWizardNavigation,{
    mode:'guided',step:2,onModeChange(){},onStepChange(){},hasUnsavedChanges:true,
  }));
  assert.match(html,/aria-label="مراحل ثبت فاکتور فروش"/);
  assert.match(html,/aria-current="step"/);
  assert.match(html,/تغییرات ذخیره‌نشده/);
  const professional=renderToStaticMarkup(React.createElement(n.exports.InvoiceWizardNavigation,{
    mode:'advanced',step:1,onModeChange(){},onStepChange(){},
  }));
  assert.doesNotMatch(professional,/sac-wizard-step-nav/);
  assert.match(professional,/حالت حرفه‌ای/);
});
