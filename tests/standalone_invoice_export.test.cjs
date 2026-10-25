'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
const pathToModule=path.join(root,'src','standalone_invoice_export.js');
const compiled=esbuild.buildSync({entryPoints:[pathToModule],bundle:true,
  platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const virtual=path.join(root,'tests','invoice-export-virtual.cjs');
const loaded=new Module(virtual,module);
loaded.filename=virtual;loaded.paths=Module._nodeModulePaths(path.dirname(virtual));
loaded._compile(compiled,virtual);
const {safeInvoiceFilename,jpegPagesToPdf,buildStandaloneDocumentExport}=loaded.exports;

test('invoice export filename template is validated and sanitized',()=>{
  const invoice={kind:'invoice',id:'book.100',date:'2026-10-22',number:'INV.5'};
  assert.equal(safeInvoiceFilename('madar-{kind}-{date}-{id}',invoice),
    'madar-invoice-2026-10-22-book.100');
  assert.equal(safeInvoiceFilename('{number}/{id}',invoice),'INV.5-book.100');
  assert.equal(safeInvoiceFilename('madar-{kind}-{id}',{...invoice,kind:'proforma'}),
    'madar-proforma-book.100');
  assert.throws(()=>safeInvoiceFilename('{bogus}',invoice),/متغیر/);
  assert.throws(()=>safeInvoiceFilename('{id}',{...invoice,id:'CON'}),/نام/);
  assert.throws(()=>safeInvoiceFilename('{id}',{...invoice,id:'PRN.txt'}),/نام/);
  assert.throws(()=>safeInvoiceFilename('',invoice),/الگو/);
  assert.throws(()=>safeInvoiceFilename('{id}',{...invoice,id:''}),/مشخصات/);
});

test('PDF export page tree, image count and offsets are well-formed',async()=>{
  // Synthetic short JPEG signatures: verifies the binary PDF container, not
  // a browser-rendered invoice image or print-device behavior.
  const jpeg=new Uint8Array([255,216,255,224,20,31,255,217]);
  const pdf=jpegPagesToPdf([{width:1240,height:1754,jpeg},
    {width:1240,height:1754,jpeg}]);
  assert.equal(pdf.type,'application/pdf');
  const bytes=Buffer.from(await pdf.arrayBuffer());
  const content=bytes.toString('latin1');
  assert.match(content,/^%PDF-1\.4/);
  assert.match(content,/\/Count 2/);
  assert.equal((content.match(/\/Subtype \/Image/g)||[]).length,2);
  const xrefStart=Number(/startxref\n(\d+)\n%%EOF/.exec(content)[1]);
  assert.equal(content.slice(xrefStart,xrefStart+5),'xref\n');
  const offsets=content.slice(xrefStart).split('\n').slice(2,11);
  for(let i=1;i<=8;i++){
    const offset=Number(offsets[i].slice(0,10));
    assert.match(content.slice(offset,offset+15),new RegExp('^'+i+' 0 obj'));
  }
  assert.throws(()=>jpegPagesToPdf([]),/PDF requires/);
  assert.throws(()=>jpegPagesToPdf([{width:0,height:10,jpeg}]),/Invalid JPEG/);
});

test('proforma print content is explicitly non-posting and never an issued invoice',async()=>{
  const previous=global.document, labels=[];
  const context={
    fillRect(){},fillText(text){labels.push(String(text));},
    measureText(text){return {width:String(text).length*8};},
  };
  global.document={
    fonts:{ready:Promise.resolve()},
    createElement(kind){
      assert.equal(kind,'canvas');
      return {width:0,height:0,getContext(){return context;},
        toBlob(callback){callback(new Blob(['fake-png'],{type:'image/png'}));}};
    },
  };
  try{
    const doc={id:'PF.1',partyId:'buyer',documentDate:'2026-10-24',
      validUntil:'2026-11-24',status:'sent',subtotal:3,discount:0,tax:0,total:3,
      lines:[{description:'Printing',quantity:3,unitPrice:1,total:3}]};
    const output=await buildStandaloneDocumentExport({
      kind:'proforma',doc,party:'Buyer',format:'png',
      pattern:'madar-{kind}-{id}',currency:'RIAL',
    });
    assert.equal(output.filename,'madar-proforma-PF.1.png');
    assert.equal(output.blob.type,'image/png');
    assert.ok(labels.some(v=>v==='پیش‌فاکتور فروش'));
    assert.ok(labels.some(v=>/فاقد اثر مالی/.test(v)));
    assert.ok(labels.some(v=>/۳ ریال/.test(v)));
    assert.ok(labels.some(v=>/۱۴۰۵\/۰۹\/۰۳/.test(v)));
  }finally{
    if(previous===undefined)delete global.document;else global.document=previous;
  }
});
