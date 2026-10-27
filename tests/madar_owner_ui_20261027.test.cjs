const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=file=>fs.readFileSync(path.join(__dirname,'..',file),'utf8');

test('decorative old sidebar promo is fully absent from JSX and CSS',()=>{
  assert.doesNotMatch(read('src/App.jsx'),/یک قدم، هر بار|sidebar-help|help-icon/);
  assert.doesNotMatch(read('src/styles.css'),/\.sidebar-help|\.help-icon/);
});

test('one finance management link goes to verified standalone dashboard, not old finance hub',()=>{
  const source=read('src/App.jsx');
  assert.equal((source.match(/مدیریت مالی<\/button>/g)||[]).length,1);
  assert.match(source,/canViewStandalone&&show\('accountingDashboard'\)&&<button/);
  assert.match(source,/window\.location\.assign\('\.\/accounting\.html'\)/);
  assert.doesNotMatch(source,/setFinanceHubOpen\(true\)|<FinanceOverview\b/);
  assert.match(read('src/standalone_accounting_workspace.jsx'),/useState\('overview'\)/);
});

test('fixed clock uses calendar only and legacy preferences preserve calendar changes',()=>{
  const app=read('src/App.jsx');
  const backend=read('native_app.py');
  assert.match(app,/<ClockWidget calendar=\{calendar\}\/>/);
  assert.doesNotMatch(app,/<ClockWidget[^>]*\b(?:settings|onChange|onOpenSettings)=/);
  assert.match(app,/setPreferences\(\{calendar:choice,widgetSettings\}\)/);
  assert.match(backend,/"widgetSettings": widget/);
});

test('floating labels initialize in both tasks and standalone accounting',()=>{
  for(const name of ['src/main.jsx','src/standalone_main.jsx']){
    const source=read(name);
    assert.match(source,/import \{installFloatingLabels\} from '\.\/floating_labels\.js'/);
    assert.match(source,/installFloatingLabels\(document\)/);
    assert.match(source,/floating_labels\.css/);
  }
});
