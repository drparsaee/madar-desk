'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');
const {spawnSync} = require('node:child_process');
const {pathToFileURL} = require('node:url');
const esbuild = require('esbuild');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

const root = path.resolve(__dirname, '..');
const candidates = process.platform === 'win32'
  ? ['C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe']
  : ['/usr/bin/chromium', '/usr/bin/google-chrome', '/usr/bin/chromium-browser'];
const chrome = candidates.find(file => fs.existsSync(file));

function component() {
  const code = esbuild.buildSync({entryPoints:[path.join(root,'src/priorities.jsx')],bundle:true,
    format:'cjs',platform:'node',write:false,jsx:'automatic',loader:{'.css':'empty'},
    external:['react','react/jsx-runtime','lucide-react']}).outputFiles[0].text;
  const moduleInstance = new Module(path.join(root,'__priorities_theme_test__.cjs'),module);
  moduleInstance.filename = path.join(root,'__priorities_theme_test__.cjs');
  moduleInstance.paths = Module._nodeModulePaths(root);
  moduleInstance._compile(code,moduleInstance.filename);
  return moduleInstance.exports.PrioritySettings;
}

test('Chromium renders light/dark priority rows, editors, swatches, previews and warning coherently',
  {skip:!chrome}, () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(),'madar-priority-theme-'));
    try {
      const PrioritySettings = component();
      const html = renderToStaticMarkup(React.createElement(PrioritySettings, {
        settings:{priorityDefinitions:[
          {id:'low',label:'کم',color:'#94a3b8',effect:'none'},
          {id:'medium',label:'متوسط',color:'#628dde',effect:'none'},
          {id:'high',label:'بالا',color:'#eb6976',effect:'none'},
          {id:'p-neon',label:'فوری',color:'#e64980',effect:'neon'},
          {id:'p-solid',label:'بحرانی',color:'#efad54',effect:'solid'},
        ]},onChange:()=>{},canManage:true,
      }));
      const css = ['src/styles.css','src/priorities.css','src/settings_density.css']
        .map(file => fs.readFileSync(path.join(root,file),'utf8')).join('\n');
      const fixture = `<!doctype html><html lang="fa" dir="rtl" data-theme="light">
<head><meta charset="utf-8"><style>${css}\nbody{overflow:auto!important;padding:20px;}
.settings-density{max-width:920px;margin:auto}.priority-settings{padding:20px}</style></head>
<body><div class="settings-density">${html}<p role="alert" class="priority-warning" id="warning" style="display:none"></p></div>
<script>
const row=document.querySelector('.priority-definition');
const label=row.querySelector('label');
const field=row.querySelector('input:not([type=color])');
const selector=row.querySelector('select');
const colorPicker=row.querySelector('input[type=color]');
const add=document.querySelector('.priority-new input');
const warning=document.getElementById('warning');
warning.remove();
document.querySelector('.priority-settings').append(warning);
warning.style.display='';
warning.textContent='این اولویت روی کارت استفاده می‌شود.';
const neon=document.querySelector('.priority-demo.priority-effect-neon');
const solid=document.querySelector('.priority-demo.priority-effect-solid');
const read=()=>{
  const style=node=>getComputedStyle(node);
  return {row:style(row).backgroundColor, border:style(row).borderTopColor,
    label:style(label).color,field:style(field).backgroundColor,
    fieldInk:style(field).color,select:style(selector).backgroundColor,
    option:style(selector.options[0]).backgroundColor,add:style(add).backgroundColor,
    pickerBorder:style(colorPicker).borderTopColor,
    warning:style(warning).backgroundColor,warningInk:style(warning).color,
    neon:style(neon).backgroundImage,solid:style(solid).backgroundColor};
};
const light=read();
document.documentElement.dataset.theme='dark';
field.focus();
const dark=read();
const focused={target:document.activeElement===field,
  outline: getComputedStyle(field).outlineStyle,
  color:getComputedStyle(field).outlineColor};
document.body.dataset.results=encodeURIComponent(JSON.stringify({light,dark,focused}));
</script></body></html>`;
      const file = path.join(directory,'priority-theme.html');
      fs.writeFileSync(file,fixture,'utf8');
      const profile = path.join(directory,'profile');
      const flags = ['--headless=new','--disable-gpu','--no-first-run',
        '--no-default-browser-check','--disable-extensions','--virtual-time-budget=2500',
        '--window-size=1280,1000',`--user-data-dir=${profile}`];
      const result = spawnSync(chrome,[...flags,'--dump-dom',pathToFileURL(file).href],
        {timeout:20000,maxBuffer:5*1024*1024,encoding:'utf8'});
      assert.equal(result.error,undefined,`Browser launch: ${result.error?.message}`);
      assert.equal(result.status,0,`Browser exit ${result.status}: ${result.stderr?.slice(0,400)}`);
      const encoded = result.stdout.match(/data-results="([^"]+)"/);
      assert.ok(encoded,`Browser missed theme sample: ${result.stdout.slice(-800)}`);
      const report = JSON.parse(decodeURIComponent(encoded[1]));
      const rgb = color => (color.match(/[\d.]+/g)||[]).slice(0,3).map(Number);
      const lightness = color => rgb(color).reduce((sum,v)=>sum+v,0)/3;
      for(const key of ['row','field','select','option','add','warning']) {
        assert.ok(lightness(report.light[key]) > 210 || key==='warning',
          `light ${key} should stay a light surface: ${report.light[key]}`);
        assert.ok(lightness(report.dark[key]) < 100,
          `dark ${key} must not be white: ${report.dark[key]}`);
      }
      for(const key of ['border','pickerBorder']) {
        assert.ok(lightness(report.dark[key]) < 130,`dark ${key} must not be pale`);
      }
      assert.ok(lightness(report.dark.label)>140,'dark native label must be readable');
      assert.ok(lightness(report.dark.fieldInk)>160,'dark field text must be readable');
      assert.ok(lightness(report.dark.warningInk)>150,'dark error must be readable');
      assert.notEqual(report.light.neon,report.dark.neon,'neon preview must use dark backing');
      assert.notEqual(report.light.solid,report.dark.solid,'solid preview must use dark backing');
      assert.deepEqual(report.focused.target,true);
      assert.notEqual(report.focused.outline,'none','keyboard focus must remain visible');
      assert.ok(lightness(report.focused.color)>140,'focus ring must remain visible');
      console.log(`Priority surfaces (Chromium computed): light row=${report.light.row}, field=${report.light.field}, add=${report.light.add}; dark row=${report.dark.row}, field=${report.dark.field}, select=${report.dark.select}, add=${report.dark.add}, warning=${report.dark.warning}`);

      // Optional synthetic screenshot, from the same browser/profile used for the
      // computed-style test. Never reads real APPDATA or opens the live app.
      if (process.env.MADAR_PRIORITY_SCREENSHOT) {
        const screenshot = path.resolve(process.env.MADAR_PRIORITY_SCREENSHOT);
        const capture = spawnSync(chrome,[...flags,`--screenshot=${screenshot}`,
          pathToFileURL(file).href],{timeout:20000,encoding:'utf8'});
        assert.equal(capture.error,undefined);
        assert.equal(capture.status,0,`Browser screenshot: ${capture.stderr?.slice(0,400)}`);
        assert.ok(fs.existsSync(screenshot),'dark theme screenshot must exist');
      }
    } finally {
      fs.rmSync(directory,{recursive:true,force:true});
    }
  });
