const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../src/clock_widget.js'),'utf8');
const jsx=fs.readFileSync(path.resolve(__dirname,'../src/clock_widget.jsx'),'utf8');
const css=fs.readFileSync(path.resolve(__dirname,'../src/clock_widget.css'),'utf8');
const values=[...source.matchAll(/id:'([^']+)'/g)].map(x=>x[1]);
test('clock widget choices explicitly cover time, date and hiding',()=>{
  assert.deepEqual(values,['both','clock','date','hidden']);
  assert.match(source,/CLOCK_WIDGET_MODES\.includes\(value\) \? value : 'both'/);
});

const Module=require('node:module');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'..');
const bundle=esbuild.buildSync({entryPoints:[path.join(root,'src/clock_widget.jsx')],
  bundle:true,platform:'node',format:'cjs',write:false,jsx:'automatic',
  loader:{'.css':'empty'},external:['react','react-dom','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
const loaded=new Module(path.join(root,'src/clock-widget-test.cjs'),module);
loaded.filename=path.join(root,'src/clock-widget-test.cjs');
loaded.paths=Module._nodeModulePaths(root);
loaded._compile(bundle,loaded.filename);
const {ClockWidget,WidgetSettings,clockPopoverPosition}=loaded.exports;

test('clock popup is a compact viewport-bounded portal, below modal stacking',()=>{
  assert.match(css,/\.clock-widget\.clock-widget__menu\s*\{/);
  assert.match(css,/position:fixed;z-index:90;display:block/);
  assert.match(css,/width:min\(272px,calc\(100vw - 16px\)\)/);
  assert.match(css,/max-height:min\(280px,calc\(100dvh - 16px\)\)/);
  assert.doesNotMatch(css,/max-height:min\(70vh,610px\)/);
  assert.match(jsx,/createPortal\(<div ref=\{menuRef\}/);
  assert.match(jsx,/document\.addEventListener\('scroll', schedule, true\)/);
  assert.match(jsx,/document\.addEventListener\('focusin', close\)/);
  assert.match(jsx,/event\.key === 'Escape'/);
  assert.match(jsx,/!menuRef\.current\?\.contains\(event\.target\)/);
});

test('popover position clamps horizontally and chooses above/below at viewport edges',()=>{
  const popup={width:272,height:245}, viewport={width:390,height:700};
  const nearRight={left:350,right:385,top:100,bottom:134};
  assert.deepEqual(clockPopoverPosition(nearRight,popup,viewport),{left:110,top:142});
  const nearBottom={left:5,right:40,top:655,bottom:691};
  assert.deepEqual(clockPopoverPosition(nearBottom,popup,viewport,false),{left:8,top:402});
  const narrow={width:170,height:160};
  const tiny=clockPopoverPosition({left:140,right:169,top:130,bottom:156},popup,narrow);
  assert(tiny.left>=0&&tiny.left<=8,'tiny viewport should clamp to viewport inset');
  assert(tiny.top>=0&&tiny.top<=8,'tiny viewport should clamp to viewport inset');
  const offset=clockPopoverPosition({left:148,right:172,top:76,bottom:104},
    {width:200,height:120},{left:20,top:40,width:180,height:150});
  assert(offset.left>=28&&offset.left<=192);
  assert(offset.top>=48&&offset.top<=182);
});

test('quick settings preserve presentation choices and optional full settings remain reachable',()=>{
  assert.match(jsx,/<SettingChoices label="نمایش" items=\{CLOCK_WIDGET_CHOICES\}/);
  assert.match(jsx,/<select value=\{value\.placement\}/);
  assert.match(jsx,/onChange=\{event => commit\(\{\.\.\.value, placement: event\.target\.value\}\)\}/);
  assert.match(jsx,/onOpenSettings\(\)/);
  assert.match(jsx,/<details className="clock-widget__more">/);
  assert.match(jsx,/<WidgetSettings settings=\{value\} onChange=\{commit\} disabled=\{disabled\} embedded\/>/);
  assert.match(jsx,/triggerRef\.current\?\.focus\(\)/);
  const html=renderToStaticMarkup(React.createElement(ClockWidget,{
    settings:{mode:'date',theme:'dark',placement:'floating',dateFormat:'compact',position:{x:.2,y:.3}},
    onChange:()=>{},onOpenSettings:()=>{},
  }));
  assert.match(html,/data-widget-theme="dark"/);
  assert.match(html,/data-widget-size="regular"/);
  assert.match(html,/aria-haspopup="dialog"/);
  const full=renderToStaticMarkup(React.createElement(WidgetSettings,{
    settings:{mode:'hidden',placement:'bottom-left'},onChange:()=>{},
  }));
  assert.match(full,/پوسته/);
  assert.match(full,/محل قرارگیری/);
});
