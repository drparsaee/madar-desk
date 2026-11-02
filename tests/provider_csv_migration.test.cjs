const assert=require('node:assert/strict');
const test=require('node:test');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const built=esbuild.buildSync({entryPoints:[path.join(__dirname,'../src/provider_csv_migration.jsx')],
  bundle:true,platform:'node',format:'cjs',write:false,
  external:['react','react-dom','lucide-react'],loader:{'.css':'empty'}}).outputFiles[0].text;
const compiled=new Module(path.join(__dirname,'../src/provider_csv_migration.jsx'),module);
compiled.filename=path.join(__dirname,'../src/provider_csv_migration.jsx');
compiled.paths=module.paths;
compiled._compile(built,compiled.filename);
const {buildProviderCsvRequest,default:Panel}=compiled.exports;

const columns={
  parties:{id:'Code',name:'Name',kind:'Role'},
  invoices:{id:'Doc',partyId:'Party',kind:'Type',date:'Day',status:'State',total:'Total'},
  transactions:{id:'Ref',partyId:'Party',documentId:'Doc',kind:'Type',date:'Day',amount:'Amount'},
};
const config=()=>({provider:'Synthetic Software',currency:'RIAL',
  files:Object.fromEntries(Object.entries(columns).map(([group,mapping])=>
    [group,{path:`C:\\fake\\${group}.csv`,encoding:'utf-8-sig',delimiter:',',
      columns:Object.values(mapping)}])),
  mappings:Object.fromEntries(Object.entries(columns).map(([group,mapping])=>
    [group,{...mapping}])),ignored:{},valueMaps:{},counts:{parties:'2',invoices:'',transactions:''},
  totals:{invoice:'100',bill:'',receipt:'',payment:''}});

test('explicit mapping builds read-only CSV contract',()=>{
  const preview=buildProviderCsvRequest(config());
  assert.equal(preview.currency,'RIAL');
  assert.equal(preview.provider,'Synthetic Software');
  assert.equal(preview.datasets.invoices.mapping.partyId,'Party');
  assert.deepEqual(preview.datasets.parties.ignoreColumns,[]);
  assert.deepEqual(preview.expectations.counts,{parties:2});
  assert.deepEqual(preview.expectations.totals,{invoice:100});
});
test('missing mapping / currency / unnoticed header are rejected',()=>{
  const first=config();first.currency='TOMAN';
  assert.throws(()=>buildProviderCsvRequest(first),/ریال/);
  const second=config();delete second.mappings.parties.id;
  assert.throws(()=>buildProviderCsvRequest(second),/نگاشت/);
  const third=config();third.files.parties.columns.push('IgnoredOffice');
  assert.throws(()=>buildProviderCsvRequest(third),/ستون‌های اضافه/);
  third.ignored={parties:['IgnoredOffice']};
  assert.deepEqual(buildProviderCsvRequest(third).datasets.parties.ignoreColumns,['IgnoredOffice']);
});
test('bad enum JSON and unbounded totals cannot be previewed',()=>{
  const bad=config();bad.valueMaps={parties:'{invalid json'};
  assert.throws(()=>buildProviderCsvRequest(bad),/JSON/);
  const unsafe=config();unsafe.totals.invoice='9007199254740993';
  assert.throws(()=>buildProviderCsvRequest(unsafe),/محدوده امن/);
});
test('standalone migration panel uses admin permission and has no import action',()=>{
  const hidden=renderToStaticMarkup(React.createElement(Panel,{canAdmin:false,api:{}}));
  assert.equal(hidden,'');
  const html=renderToStaticMarkup(React.createElement(Panel,{canAdmin:true,api:{}}));
  assert.match(html,/پیش‌نمایش CSV سایر نرم‌افزارهای حسابداری/);
  assert.match(html,/انتخاب CSV/);
  assert.match(html,/اجرای پیش‌نمایش فقط‌خواندنی/);
  assert.doesNotMatch(html,/ثبت به دفتر حسابداری|صدور فاکتور/);
});
