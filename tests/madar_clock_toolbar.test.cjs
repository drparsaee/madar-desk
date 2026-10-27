const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const app=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
const css=fs.readFileSync(path.join(root,'src/vitrea_navigation.css'),'utf8');
const clockCss=fs.readFileSync(path.join(root,'src/clock_widget.css'),'utf8');
const clock=fs.readFileSync(path.join(root,'src/clock_widget.jsx'),'utf8');

test('unified header puts brand, navigation and profile in one row; search in its own row and clock on the left',()=>{
  assert.match(app,/className="vitrea-header-layout"/);
  assert.match(app,/className="vitrea-header-main"/);
  assert.match(app,/className="vitrea-brand-capsule"[\s\S]*?<strong>مدار<\/strong><i aria-hidden="true">\|<\/i>[\s\S]*?<small>در جریان کسب و کار<\/small>/);
  const topRow=app.match(/<div className="vitrea-top-row">([\s\S]*?)<\/nav>/)?.[1];
  assert.ok(topRow);
  assert.match(topRow,/<nav className="vitrea-primary-nav"/);
  const accountIndex=app.indexOf('className="vitrea-account-capsule"');
  const endNav=app.indexOf('</nav>',app.indexOf('<nav className="vitrea-primary-nav"'));
  const endTopRow=app.indexOf('</div>',endNav);
  assert.ok(accountIndex>endNav&&accountIndex<endTopRow,'profile belongs beside navigation, not search');
  const header=app.match(/<header className="topbar">([\s\S]*?)<\/header>/)?.[1];
  assert.ok(header,'topbar must exist');
  assert.match(header,/<SearchPlus\b/);
  assert.doesNotMatch(header,/className="vitrea-account-capsule"/);
  assert.doesNotMatch(header,/<SyncIndicator\b|<ClockWidget\b|<Settings2|<Cloud|<Bell|<Users|<RefreshCw/);
  assert.match(app,/className="vitrea-header-clock"><ClockWidget calendar=\{calendar\}\/>/);
  assert.equal((app.match(/<ClockWidget\b/g)||[]).length,1);
  assert.match(css,/\.vitrea-header-layout\s*\{[\s\S]*?grid-template-columns:minmax\(0,1fr\) 190px/);
  assert.match(css,/\.vitrea-header-main\s*\{[\s\S]*?border-radius:27px/);
  assert.match(clock,/clock-widget__time-card/);
  assert.match(clock,/clock-widget__date/);
  assert.match(clockCss,/\.clock-widget--fixed \.clock-widget__date\s*\{[\s\S]*?width:100%/);
});

test('connection status sits first in the left dock with refresh directly below, preserving other actions',()=>{
  const dock=app.match(/<nav className="vitrea-quickdock"([\s\S]*?)<\/nav>/)?.[1];
  assert.ok(dock,'quickdock must exist');
  assert.match(dock,/<SyncIndicator compact status=\{syncInfo\}/);
  assert.match(dock,/aria-label="تازه‌سازی اتصال"/);
  assert.ok(dock.indexOf('<SyncIndicator')<dock.indexOf('aria-label="تازه‌سازی اتصال"'));
  assert.ok(dock.indexOf('aria-label="تازه‌سازی اتصال"')<dock.indexOf('vitrea-quickdock__main'));
  for(const label of ['اعلان‌ها','تعریف کاربران','Google Drive','تنظیمات مدار']){
    assert.ok(dock.includes('aria-label="'+label+'"'),label+' action missing from dock');
  }
  assert.match(dock,/canManage&&lanStatus\.mode!=='solo'/);
  assert.doesNotMatch(dock,/aria-label="شبکه محلی"/);
  assert.equal((dock.match(/<Settings2\b/g)||[]).length,1);
  assert.match(app,/className="vitrea-account-capsule"/);
  assert.match(css,/\.vitrea-quickdock\s*\{[\s\S]*?max-height:calc\(100dvh - 28px\)/);
  assert.match(css,/\.vitrea-quickdock\s*\{[\s\S]*?overflow-y:auto/);
  assert.match(css,/@media[^{}]*\{[\s\S]*?\.vitrea-quickdock\s*\{[\s\S]*?overflow-x:auto/);
  assert.match(css,/\.vitrea-quickdock > \.sync-indicator--dock\s*\{/);
});
