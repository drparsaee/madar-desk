'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const entry=path.join(root,'src','accounting_print_template.js');
const compiled=esbuild.buildSync({entryPoints:[entry],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const file=path.join(root,'tests','virtual-accounting-print.cjs');
const loaded=new Module(file,module);
loaded.filename=file;loaded.paths=Module._nodeModulePaths(path.dirname(file));
loaded._compile(compiled,file);
const {DEFAULT_PRINT_TEMPLATE,validatePrintTemplate,templatePageSize,
  renderPrintTemplatePages,buildCustomPrintExport}=loaded.exports;

test('print template accepts independent named layout with safe geometry',()=>{
  const draft=validatePrintTemplate(DEFAULT_PRINT_TEMPLATE);
  assert.equal(draft.format,'madar-print-layout-v1');
  assert.deepEqual(templatePageSize(draft),[210,297]);
  assert.deepEqual(templatePageSize({...draft,page:'A5',orientation:'landscape'}),[210,148]);
  assert.notEqual(draft,DEFAULT_PRINT_TEMPLATE);
});

test('reject arbitrary scripts, unknown fields and invalid logo',()=>{
  for(const change of [{font:'url(javascript:alert(1))'},
    {logo:'javascript:alert(1)'},{color:'red'},
    {table:{...DEFAULT_PRINT_TEMPLATE.table,y:999}},
    {fields:[...DEFAULT_PRINT_TEMPLATE.fields.slice(1),DEFAULT_PRINT_TEMPLATE.fields[1]]}]){
    assert.throws(()=>validatePrintTemplate({...DEFAULT_PRINT_TEMPLATE,...change}),/معتبر|تکرار/);
  }
});

test('multipage print never skips a record in synthetic canvas renderer',async()=>{
  const previous=global.document;const labels=[];
  global.document={createElement(tag){
    assert.equal(tag,'canvas');
    return {width:0,height:0,getContext(){return {
      fillRect(){},strokeRect(){},fillText(text){labels.push(String(text));},
      drawImage(){},
    };},toDataURL(){return 'data:image/jpeg;base64,/9j/2Q==';},
      toBlob(callback){callback(new Blob(['png'],{type:'image/png'}));}};
  }};
  const lines=Array.from({length:44},(_,i)=>({description:'ردیف یکتا '+i,
    quantity:1,unitPrice:100,total:100}));
  const doc={id:'PREVIEW.1',documentDate:'2026-10-25',status:'draft',
    lines,subtotal:4400,discount:0,tax:0,total:4400};
  try{
    const ctx={kind:'invoice',doc,party:'مشتری آزمایشی',company:{legalName:'شرکت اول'},currency:'RIAL'};
    const pages=await renderPrintTemplatePages(DEFAULT_PRINT_TEMPLATE,ctx);
    assert.ok(pages.length>1);
    for(let i=0;i<lines.length;i++){
      assert.equal(labels.filter(x=>x==='ردیف یکتا '+i).length,1,'line '+i+' must appear once');
    }
    await assert.rejects(()=>buildCustomPrintExport({...ctx,template:DEFAULT_PRINT_TEMPLATE,
      format:'png',pattern:'madar-{id}'}),/چندصفحه‌ای/);
    const pdf=await buildCustomPrintExport({...ctx,template:DEFAULT_PRINT_TEMPLATE,
      format:'pdf',pattern:'madar-{id}'});
    assert.equal(pdf.blob.type,'application/pdf');
    assert.match(await pdf.blob.text(),/\/Count 3/);
  }finally{
    if(previous===undefined)delete global.document;else global.document=previous;
  }
});
