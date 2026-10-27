const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const app=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
const css=fs.readFileSync(path.join(root,'src/vitrea_navigation.css'),'utf8');

test('header keeps visible sync state and one fixed clock, without duplicate settings or profile',()=>{
  const header=app.match(/<header className="topbar">([\s\S]*?)<\/header>/)?.[1];
  assert.ok(header,'topbar must exist');
  assert.match(header,/<SyncIndicator\b/);
  assert.match(header,/<ClockWidget calendar=\{calendar\}\/>/);
  assert.doesNotMatch(header,/className="top-icon"|mini-profile|<Settings2|<Cloud|<Bell|<Users|<RefreshCw/);
  assert.equal((app.match(/<ClockWidget\b/g)||[]).length,1);
});

test('clock-adjacent actions live in the accessible left dock, with only one settings icon',()=>{
  const dock=app.match(/<nav className="vitrea-quickdock"([\s\S]*?)<\/nav>/)?.[1];
  assert.ok(dock,'quickdock must exist');
  for(const label of ['تازه‌سازی','اعلان‌ها','شبکه محلی','Google Drive','تنظیمات مدار']){
    assert.ok(dock.includes('aria-label="'+label+'"'),label+' action missing from dock');
  }
  assert.equal((dock.match(/<Settings2\b/g)||[]).length,1);
  assert.match(app,/className="vitrea-account-capsule"/);
  assert.match(css,/\.vitrea-quickdock\s*\{[\s\S]*?max-height:calc\(100dvh - 28px\)/);
  assert.match(css,/\.vitrea-quickdock\s*\{[\s\S]*?overflow-y:auto/);
  assert.match(css,/@media[^{}]*\{[\s\S]*?\.vitrea-quickdock\s*\{[\s\S]*?overflow-x:auto/);
});
