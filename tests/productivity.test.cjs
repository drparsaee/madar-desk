const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
const output=esbuild.buildSync({
  entryPoints:[path.join(root,'src/productivity.jsx')],
  bundle:true,platform:'node',format:'cjs',write:false,
  jsx:'automatic',external:['react','react/jsx-runtime','lucide-react']
}).outputFiles[0].text;
const compiled=new Module(path.join(root,'src','productivity-compiled.cjs'),module);
compiled.filename=path.join(root,'src','productivity-compiled.cjs');
compiled.paths=Module._nodeModulePaths(root);
compiled._compile(output,compiled.filename);
const {fromJalali,jalaliDigits,displayDate,similarTasks,searchText,durationText,pathValid}=compiled.exports;
const featureText=esbuild.buildSync({
  entryPoints:[path.join(root,'src/features.jsx')],
  bundle:true,platform:'node',format:'cjs',write:false,
  loader:{'.css':'empty'},
  jsx:'automatic',external:['react','react/jsx-runtime','lucide-react']
}).outputFiles[0].text;
const featureModule=new Module(path.join(root,'src','features-compiled.cjs'),module);
featureModule.filename=path.join(root,'src','features-compiled.cjs');
featureModule.paths=Module._nodeModulePaths(root);
featureModule._compile(featureText,featureModule.filename);
const {cardCostEnabled}=featureModule.exports;

test('Persian calendar conversion round trip does not shift the day',()=>{
  const iso='2026-10-20';
  assert.equal(jalaliDigits(new Date(iso+'T12:00:00Z')),'1405/07/28');
  assert.equal(fromJalali('۱۴۰۵/۰۷/۲۸'),iso);
  assert.equal(fromJalali('1405/13/28'),null);
  assert.equal(fromJalali('1405/07/40'),null);
  assert.match(displayDate(iso,'jalali',true),/۱۴۰۵/);
  assert.match(displayDate(iso,'gregorian',true),/۲۰۲۶/);
});
test('similarity suggestions work with Persian and Arabic spelling variants',()=>{
  const tasks=[
    {id:'1',title:'طراحی جعبه مقوایی'},
    {id:'2',title:'طراحي جعبه كاغذي'},
    {id:'3',title:'خرید و نصب دوربین امنیتی'}
  ];
  const suggestions=similarTasks('طراحی جعبه بسته بندی',tasks);
  assert(suggestions.some(item=>item.task.id==='1'));
  assert(suggestions.some(item=>item.task.id==='2'));
  assert(!suggestions.some(item=>item.task.id==='3'));
});
test('search includes checklist reports, projects, and shared file links',()=>{
  const task={title:'نوشتن طرح',description:'شرح',status:'active',
    labels:['کار فوری'],checklist:[{text:'چاپ آزمایشی'}],
    reports:[{summary:'خروجی آماده شد',agent:'کدکس'}],
    fileLinks:[{name:'فایل قالب',path:'\\SERVER\Jobs\shape.ai'}]};
  const corpus=searchText(task,{name:'پروژه چاپ'});
  for(const fragment of ['چاپ آزمایشی','کدکس','فایل قالب','shape.ai','پروژه چاپ']){
    assert(corpus.includes(fragment),fragment);
  }
});
test('duration aggregation formatting does not invent missing values',()=>{
  assert.equal(durationText(0),'ثبت نشده');
  assert.match(durationText(125),/۲ ساعت/);
  assert.match(durationText(125),/۵ دقیقه/);
});
test('only UNC network share paths can be added as file links',()=>{
  assert.equal(pathValid('\\\\OFFICE-PC\\Projects\\design file.pdf'),true);
  assert.equal(pathValid('https://example.com/file.pdf'),false);
  assert.equal(pathValid('C:\\Users\\file.pdf'),false);
  assert.equal(pathValid('\\\\SERVER\\Shared\\..\\secret.pdf'),false);
});
test('per-card cost preference overrides the project default',()=>{
  assert.equal(cardCostEnabled({costEnabled:null},{costEnabled:true}),true);
  assert.equal(cardCostEnabled({costEnabled:null},{costEnabled:false}),false);
  assert.equal(cardCostEnabled({costEnabled:true},{costEnabled:false}),true);
  assert.equal(cardCostEnabled({costEnabled:false},{costEnabled:true}),false);
});
