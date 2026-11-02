'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const esbuild=require('esbuild');
const Module=require('node:module');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'..');
const code=esbuild.buildSync({
  entryPoints:[path.join(root,'src/cover_color_picker.jsx')],
  bundle:true,platform:'node',format:'cjs',jsx:'automatic',
  loader:{'.css':'empty'},write:false,
  external:['react','react/jsx-runtime','lucide-react']
}).outputFiles[0].text;
const moduleRef=new Module(path.join(root,'cover-color-picker.cjs'),module);
moduleRef.filename=path.join(root,'cover-color-picker.cjs');
moduleRef.paths=Module._nodeModulePaths(root);
moduleRef._compile(code,moduleRef.filename);
const {hsvToHex,hexToHsv,CoverColorPicker}=moduleRef.exports;
test('picker HSV conversion stays bounded and rejects malicious invalid colors',()=>{
  assert.equal(hsvToHex(0,1,1),'#FF0000');
  assert.equal(hsvToHex(120,1,1),'#00FF00');
  assert.equal(hsvToHex(240,1,1),'#0000FF');
  assert.equal(hsvToHex(359,0,1),'#FFFFFF');
  assert.throws(()=>hsvToHex(NaN,1,1),/finite/);
  assert.throws(()=>hexToHsv('red;url(x)'),/Invalid HEX/);
  for(const hex of ['#5672CA','#ffffff','#FF0000','#152238','#45BCA3']){
    const {h,s,v}=hexToHsv(hex);
    assert.equal(hsvToHex(h,s,v),hex.toUpperCase());
  }
});
test('color picker exposes 16 accessible presets, a keyboard spectrum and a hue slider',()=>{
  const html=renderToStaticMarkup(React.createElement(CoverColorPicker,{
    value:'#5672CA',disabled:false,onChange:()=>{}
  }));
  assert.equal((html.match(/madar-common-colors__swatch/g)||[]).length,16);
  assert.match(html,/role="slider"/);
  assert.match(html,/aria-label="اشباع و روشنایی رنگ کاور"/);
  assert.match(html,/cover-picker__spectrum/);
  assert.match(html,/طیف رنگ کاور/);
  assert.match(html,/کد شش رقمی رنگ/);
  assert.match(html,/aria-label="رنگ‌های مرسوم کاور"/);
  assert.match(html,/ساخت رنگ دلخواه/);
  assert.doesNotMatch(html,/url\(/i);
});
test('disabled and malformed colors are safe to display',()=>{
  const html=renderToStaticMarkup(React.createElement(CoverColorPicker,{
    value:'red;url(javascript:alert(1))',disabled:true,onChange:()=>{}
  }));
  assert.match(html,/aria-disabled="true"/);
  assert.match(html,/tabindex="-1"/);
  assert.match(html,/value="#5672CA"/);
  assert.doesNotMatch(html,/javascript:|url\(/i);
});
