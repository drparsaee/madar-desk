'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const {spawnSync}=require('node:child_process');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
const compiled=esbuild.buildSync({entryPoints:[
  path.join(root,'src','accounting_structured_invoice_export.js')],
  bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
const virtual=path.join(root,'tests','structured-invoice-export-virtual.cjs');
const loaded=new Module(virtual,module);
loaded.filename=virtual;
loaded.paths=Module._nodeModulePaths(path.dirname(virtual));
loaded._compile(compiled,virtual);
const {buildAccountingStructuredExport}=loaded.exports;

const doc=()=>({
  id:'INV.1405.1',number:'SALES-1',documentDate:'2026-10-25',
  status:'issued',partyId:'P1',
  subtotal:120000,discount:1000,tax:3000,total:122000,
  lines:[{description:'کارت ویزیت & <طلاکوب> "A" \' B',
    quantity:3,unitPrice:40000,total:120000,itemId:'ITEM.1',accountId:'4000'}],
});
const args=()=>({
  kind:'invoice',doc:doc(),party:'شرکت مشتری',company:{
    legalName:'چاپ & بسته‌بندی <نمونه>',nationalId:'10101010',
    economicCode:'AC-1',postalCode:'1234567890',
    phone:'021-123456',address:'تهران \u200c خیابان تست',
  },currency:'RIAL',pattern:'madar-{kind}-{id}-{date}',format:'xlsx',
});

// Independently read a ZIP local record and its central-directory entry.
// This inspects actual archive integrity rather than searching raw bytes.
function checksum(buffer){
  let crc=0xffffffff;
  for(const byte of buffer){
    crc^=byte;
    for(let bit=0;bit<8;bit++)crc=crc&1?(crc>>>1)^0xedb88320:crc>>>1;
  }
  return (crc^0xffffffff)>>>0;
}
function unzipStored(bytes){
  const end=bytes.lastIndexOf(Buffer.from([0x50,0x4b,0x05,0x06]));
  assert.ok(end>=0,'ZIP end-of-central-directory signature');
  assert.equal(bytes.readUInt32LE(end),0x06054b50);
  const count=bytes.readUInt16LE(end+10);
  const centerSize=bytes.readUInt32LE(end+12);
  let cursor=bytes.readUInt32LE(end+16);
  assert.equal(cursor+centerSize,end);
  const output=new Map();
  for(let i=0;i<count;i++){
    assert.equal(bytes.readUInt32LE(cursor),0x02014b50);
    assert.equal(bytes.readUInt16LE(cursor+10),0,'ZIP stored entry');
    const crc=bytes.readUInt32LE(cursor+16);
    const size=bytes.readUInt32LE(cursor+20);
    assert.equal(size,bytes.readUInt32LE(cursor+24));
    const nameSize=bytes.readUInt16LE(cursor+28);
    const extraSize=bytes.readUInt16LE(cursor+30);
    const commentSize=bytes.readUInt16LE(cursor+32);
    const name=bytes.subarray(cursor+46,cursor+46+nameSize).toString('utf8');
    const localOffset=bytes.readUInt32LE(cursor+42);
    assert.equal(bytes.readUInt32LE(localOffset),0x04034b50);
    assert.equal(bytes.readUInt16LE(localOffset+8),0,'local stored method');
    assert.equal(bytes.readUInt32LE(localOffset+14),crc,'local CRC');
    const localNameSize=bytes.readUInt16LE(localOffset+26);
    const localExtraSize=bytes.readUInt16LE(localOffset+28);
    const localName=bytes.subarray(localOffset+30,localOffset+30+localNameSize)
      .toString('utf8');
    assert.equal(name,localName);
    const start=localOffset+30+localNameSize+localExtraSize;
    const data=bytes.subarray(start,start+size);
    assert.equal(data.length,size);
    assert.equal(checksum(data),crc,'stored ZIP content CRC');
    assert.ok(!output.has(name),'unique part name');
    output.set(name,data.toString('utf8'));
    cursor+=46+nameSize+extraSize+commentSize;
  }
  assert.equal(cursor,end);
  return output;
}

test('genuine XLSX ZIP has valid records, CRCs, OOXML relationships and typed money',async()=>{
  const result=await buildAccountingStructuredExport(args());
  assert.equal(result.filename,'madar-invoice-INV.1405.1-1405-08-03.xlsx');
  assert.equal(result.blob.type,
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
  const zip=Buffer.from(await result.blob.arrayBuffer());
  assert.equal(zip.readUInt32LE(0),0x04034b50);
  const parts=unzipStored(zip);
  assert.deepEqual([...parts.keys()].sort(),[
    '[Content_Types].xml','_rels/.rels','xl/_rels/workbook.xml.rels',
    'xl/styles.xml','xl/workbook.xml','xl/worksheets/sheet1.xml',
  ].sort());
  const xml=parts.get('xl/worksheets/sheet1.xml');
  assert.match(xml,/rightToLeft="1"/);
  assert.match(xml,/چاپ &amp; بسته‌بندی &lt;نمونه&gt;/);
  assert.match(xml,/کارت ویزیت &amp; &lt;طلاکوب&gt; &quot;A&quot; &apos; B/);
  assert.match(xml,/<c r="C\d+" s="2"><v>3<\/v><\/c>/);
  assert.match(xml,/<c r="D\d+" s="2"><v>40000<\/v><\/c>/);
  assert.match(xml,/<c r="E\d+" s="2"><v>122000<\/v><\/c>/);
  assert.match(xml,/ریال/);
  assert.doesNotMatch(xml,/<f(?:\s|>)/);
  assert.match(parts.get('xl/workbook.xml'),/sheet name="فاکتور فروش" sheetId="1"/);
  assert.match(parts.get('xl/_rels/workbook.xml.rels'),/styles\.xml/);
  assert.match(parts.get('[Content_Types].xml'),/spreadsheetml\.worksheet\+xml/);
});

test('Python zipfile and XML parser independently open the complete XLSX',async(t)=>{
  const result=await buildAccountingStructuredExport(args());
  const bytes=Buffer.from(await result.blob.arrayBuffer());
  const python=[
    'import sys, io, zipfile, xml.etree.ElementTree as ET',
    'archive = zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))',
    'assert archive.testzip() is None',
    'names = [n for n in archive.namelist() if n.endswith((".xml", ".rels"))]',
    'for name in names: ET.fromstring(archive.read(name))',
    'root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))',
    'ns = {"s":"http://schemas.openxmlformats.org/spreadsheetml/2006/main"}',
    'cells = root.findall(".//s:c", ns)',
    'assert any(c.attrib.get("r", "").startswith("E") and',
    '    c.find("s:v",ns) is not None and c.find("s:v",ns).text == "122000"',
    '    for c in cells)',
    'print("OK:", len(names), "OOXML parts;", len(cells), "worksheet cells")',
  ].join('\n');
  const probe=spawnSync('python',['-c',python],{
    input:bytes,timeout:10000,encoding:'utf8',maxBuffer:1024*1024,
  });
  if(probe.error?.code==='ENOENT')return t.skip('Python not installed');
  assert.equal(probe.status,0,probe.stderr||probe.error?.message);
  assert.match(probe.stdout,/OK:/);
});

test('user-controlled formula strings stay explicitly quoted inline text',async()=>{
  const testDoc=doc();
  testDoc.lines[0].description=' =HYPERLINK("http://example.invalid","x")';
  testDoc.lines[0].itemId='+CMD';
  testDoc.lines[0].accountId='@SUM(1,2)';
  const result=await buildAccountingStructuredExport({...args(),doc:testDoc,
    party:'-12 +invalid',company:{legalName:'＝2+2'}});
  const sheet=unzipStored(Buffer.from(await result.blob.arrayBuffer()))
    .get('xl/worksheets/sheet1.xml');
  assert.match(sheet,/<is><t>&apos; =HYPERLINK\(&quot;http:\/\/example\.invalid/);
  assert.match(sheet,/<is><t>&apos;\+CMD<\/t><\/is>/);
  assert.match(sheet,/<is><t>&apos;@SUM\(1,2\)<\/t><\/is>/);
  assert.match(sheet,/<is><t>&apos;-12 \+invalid<\/t><\/is>/);
  assert.match(sheet,/<is><t>&apos;＝2\+2<\/t><\/is>/);
  assert.doesNotMatch(sheet,/<f(?:\s|>)/);
});

test('RTF is structured and encodes Persian, braces and backslashes safely',async()=>{
  const dangerous=doc();
  dangerous.lines[0].description='شرح {فاتوره} \\ دستور';
  const {filename,blob}=await buildAccountingStructuredExport({
    ...args(),doc:dangerous,format:'rtf',currency:'TOMAN',
    party:'R{\\} مشتری',
  });
  assert.match(filename,/\.rtf$/);
  assert.equal(blob.type,'application/rtf');
  const rtf=await blob.text();
  assert.match(rtf,/^\{\\rtf1\\ansi\\ansicpg1252\\uc1/);
  assert.ok(rtf.endsWith('}'));
  assert.match(rtf,/\\rtlpar\\qr/);
  assert.match(rtf,/\\trowd/);
  assert.match(rtf,/\\row/);
  assert.match(rtf,/\\u-?\d+\?/,'Unicode encoded as signed UTF-16 units');
  assert.match(rtf,/R\\\{\\\\\\\}/,'RTF delimiter and slash escaping');
  const amount=[...'۱۲۲٬۰۰۰'].map(c=>'\\u'+c.charCodeAt(0)+'?').join('');
  assert.ok(rtf.includes(amount),'amount rendered without changing currency');
  assert.match(rtf,/\\cell/);
  // Escaped document text must not introduce an extra paragraph or RTF command.
  assert.doesNotMatch(rtf,/\{\\rtf1[\s\S]*\{فاتوره/);
});

test('proforma remains explicitly non-posting and unit labels are exact',async()=>{
  const d=doc();d.status='sent';
  const {blob}=await buildAccountingStructuredExport({...args(),
    kind:'proforma',doc:d,format:'rtf',currency:'RIAL'});
  const rtf=await blob.text();
  assert.match(rtf,/\\u/);
  const {blob:xlsx}=await buildAccountingStructuredExport({...args(),
    kind:'proforma',doc:d,format:'xlsx',currency:'TOMAN'});
  const sheet=unzipStored(Buffer.from(await xlsx.arrayBuffer()))
    .get('xl/worksheets/sheet1.xml');
  assert.match(sheet,/تومان/);
  assert.match(sheet,/بدون اثر مالی/);
  assert.doesNotMatch(sheet,/>ریال</);
});

test('bad totals, forged amounts, invalid identifiers and invalid format are rejected',async()=>{
  const valid=args();
  await assert.rejects(buildAccountingStructuredExport({...valid,
    doc:{...doc(),total:122001}}),/مبالغ/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    doc:{...doc(),lines:[{...doc().lines[0],total:1}]}}),/حاصل‌ضرب/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    doc:{...doc(),lines:[{...doc().lines[0],quantity:1.5}]}}),/تعداد/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    doc:{...doc(),lines:[{...doc().lines[0],description:'bad\x00line'}]}}),/نویسه/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    doc:{...doc(),documentDate:'not-a-date'}}),/تاریخ/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    currency:'USD'}),/واحد پول/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    format:'html'}),/قالب/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    pattern:'{unknown}'}),/متغیر/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    party:' '}),/طرف‌حساب/);
  await assert.rejects(buildAccountingStructuredExport({...valid,
    doc:{...doc(),lines:[]}}),/اقلام/);
});
