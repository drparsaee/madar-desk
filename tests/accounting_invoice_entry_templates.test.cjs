'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const compiled=esbuild.buildSync({entryPoints:[path.join(root,'src','accounting_invoice_entry_templates.js')],
  bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const virtual=path.join(root,'tests','virtual-invoice-templates.cjs');
const loaded=new Module(virtual,module);
loaded.filename=virtual;loaded.paths=Module._nodeModulePaths(path.dirname(virtual));
loaded._compile(compiled,virtual);
const {buildAccountingInvoiceEntryTemplate,parseAccountingInvoiceEntryTemplate}=loaded.exports;
const row={description:'اسکن و ادیت فایل کتاب Big Pocket 2',
  quantity:'۳۶',unitPrice:'3,500,000',accountId:'4000',itemId:''};

test('portable RIAL invoice row preset roundtrips without posting a financial event',()=>{
  const doc=buildAccountingInvoiceEntryTemplate([row],{currency:'RIAL',title:'خدمات چاپ'});
  assert.deepEqual(Object.keys(doc),['format','version','title','currency','lines']);
  assert.equal(doc.lines[0].quantity,'36');
  assert.equal(doc.lines[0].unitPrice,'3500000');
  assert.equal(parseAccountingInvoiceEntryTemplate(JSON.stringify(doc),{currency:'RIAL'}).lines[0].description,
    row.description);
});
test('cross-company unit/currency mismatch cannot silently reinterpret money',()=>{
  const json=JSON.stringify(buildAccountingInvoiceEntryTemplate([row],{currency:'RIAL'}));
  assert.throws(()=>parseAccountingInvoiceEntryTemplate(json,{currency:'TOMAN'}),/واحد پول/);
});
test('rejects template expressions, overflows, malformed rows, and missing header',()=>{
  for(const value of ['5*9','-1','1e3','0.5','','999999999999999999999']){
    assert.throws(()=>buildAccountingInvoiceEntryTemplate([{...row,unitPrice:value}]),/قیمت|سقف/);
  }
  assert.throws(()=>buildAccountingInvoiceEntryTemplate([{...row,description:''}]),/شرح/);
  assert.throws(()=>buildAccountingInvoiceEntryTemplate([{...row,accountId:'../../id'}]),/شناسه/);
  assert.throws(()=>buildAccountingInvoiceEntryTemplate([]),/ردیف/);
  assert.throws(()=>parseAccountingInvoiceEntryTemplate('not json'),/JSON/);
  assert.throws(()=>parseAccountingInvoiceEntryTemplate('{}'),/ساختار/);
  assert.throws(()=>parseAccountingInvoiceEntryTemplate(' '.repeat(1048577)),/مگابایت/);
});
