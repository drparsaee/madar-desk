'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {parse}=require('@babel/parser');
const postcss=require('postcss');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
const css=fs.readFileSync(path.join(root,'src/vitrea_navigation.css'),'utf8');
const tokens=fs.readFileSync(path.join(root,'src/vitrea_design_tokens.css'),'utf8');
const tree=postcss.parse(css);

const rulesFor=selector=>{
  const result=[];
  tree.walkRules(rule=>{if(rule.selector===selector)result.push(rule);});
  return result;
};
test('Vitrea layout uses accessible real navigation, not fake placeholder links',()=>{
  assert.ok(parse(source,{sourceType:'module',plugins:['jsx']}).program.body.length);
  assert.match(source,/className="vitrea-top-row"/);
  assert.match(source,/className="vitrea-quickdock" aria-label="میان‌برهای مدار"/);
  assert.match(source,/className="vitrea-primary-nav" aria-label="بخش‌های اصلی مدار"/);
  assert.match(source,/className="vitrea-brand-capsule"/);
  assert.match(source,/className="vitrea-account-capsule"/);
  assert.match(source,/aria-controls="madar-sidebar"/);
  assert.match(source,/inert=\{!mobileNavOpen&&!desktopNavOpen\}/);
  assert.match(source,/setDesktopNavOpen\(false\);quickDockTrigger\.current\?\.focus\(\)/);
  assert.match(source,/window\.location\.assign\('\.\/accounting\.html'\)/);
  assert.match(source,/changeAdmin\(state=>\(\{\.\.\.state,settings:/);
});

test('capsule and rail have keyboard focus and a mobile bottom-dock layout',()=>{
  for(const selector of ['.vitrea-primary-nav','.vitrea-quickdock','.vitrea-top-row',
      '.vitrea-brand-capsule,.vitrea-account-capsule','.vitrea-nav-backdrop']){
    assert.ok(rulesFor(selector).length,selector+' required');
  }
  assert.match(css,/\.vitrea-quickdock button:hover,\.vitrea-quickdock button:focus-visible/);
  assert.match(css,/@media \(max-width:860px\)/);
  assert.match(css,/\.vitrea-quickdock\s*\{\s*z-index:299;[\s\S]*?flex-direction:row/);
  assert.match(css,/\.app-shell\.vitrea-layout > \.sidebar\.sidebar--vitrea-open/);
  assert.match(css,/\.app-shell\.vitrea-layout > \.sidebar\s*\{[\s\S]*?pointer-events:none/);
});

test('theme tokens correspond to verified dark graphite and support reduced transparency',()=>{
  for(const item of ['--vs-bg:#111113','--vs-glass:#1e1e226b','--vs-accent:#7aaef0',
     '--vs-round:26px','prefers-reduced-transparency:reduce'])assert.ok(tokens.includes(item),item);
  assert.doesNotMatch(tokens,/@import\s+url\(/);
  assert.doesNotMatch(tokens,/fonts\.googleapis/);
});

test('accounting bootstrap keeps explicit light preference, defaults to graphite and shares no finance data',()=>{
  const accounting=fs.readFileSync(path.join(root,'src/standalone_main.jsx'),'utf8');
  assert.match(source,/localStorage\.setItem\('madar-ui-theme'/);
  assert.match(accounting,/localStorage\.getItem\('madar-ui-theme'\)/);
  assert.match(accounting,/choice==='light'\?'light':'dark'/);
  assert.match(accounting,/document\.documentElement\.dataset\.theme='dark'/);
  assert.doesNotMatch(source,/localStorage\.setItem\('madar-.*(?:ledger|finance)/);
});
