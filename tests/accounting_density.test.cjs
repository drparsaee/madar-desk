const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const app=fs.readFileSync(path.join(root,'src/standalone_accounting_workspace.jsx'),'utf8');
const css=fs.readFileSync(path.join(root,'src/accounting_density.css'),'utf8');
test('standalone accounting imports a scoped compact layout without backend changes',()=>{
  assert.match(app,/import '\.\/accounting_density\.css'/);
  assert.match(css,/\.sac-root \.sac-sidebar/);
  assert.match(css,/\.sac-root \.sac-header/);
  assert.match(css,/\.sac-root \.sac-panel/);
  assert.match(css,/@media\(max-width:850px\)/);
  assert.match(css,/@media print/);
  assert.doesNotMatch(css,/display\s*:\s*none/,'no accounting tool is removed for density');
});
