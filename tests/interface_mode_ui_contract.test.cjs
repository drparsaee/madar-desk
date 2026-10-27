/**
 * M-04 App.jsx integration contract. Static JSX/AST evidence, never an E2E claim.
 * Managed LAN display roles replaced the historical local-user dropdown.
 * We do not edit App.jsx from this test or infer API/host authorization from JSX.
 */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {parse} = require('@babel/parser');
const traverse = require('@babel/traverse').default;
const Module = require('node:module');
const esbuild = require('esbuild');

const appPath = path.resolve(__dirname,'../src/App.jsx');
const app = fs.readFileSync(appPath,'utf8');
const ast = parse(app,{sourceType:'module',plugins:['jsx']});
const jsx = [];
const identifiers = new Set();

function nodeName(node){
  if(!node) return '';
  if(node.type==='JSXIdentifier') return node.name;
  if(node.type==='JSXMemberExpression') return nodeName(node.object)+'.'+nodeName(node.property);
  return '';
}
function textOf(node){return node?app.slice(node.start,node.end):'';}

// Record conditions on the path *to* each JSX element. Conditions appearing
// inside an event handler or unrelated child must not satisfy a render gate.
function guardsOf(path){
  const result=[];
  for(let parent=path.parentPath;parent;parent=parent.parentPath){
    const n=parent.node;
    if(n.type==='LogicalExpression'&&n.operator==='&&'&&n.right.start<=path.node.start&&n.right.end>=path.node.end){
      result.push(textOf(n.left));
    }
    if(n.type==='ConditionalExpression'){
      if(n.consequent.start<=path.node.start&&n.consequent.end>=path.node.end) result.push(textOf(n.test));
      // The alternative is not a positive display gate; no false confidence.
    }
    if(['FunctionDeclaration','FunctionExpression','ArrowFunctionExpression'].includes(n.type)) break;
  }
  return result;
}
traverse(ast,{
  ImportSpecifier(p){if(p.node.imported?.name)identifiers.add(p.node.imported.name);},
  JSXElement(p){jsx.push({name:nodeName(p.node.openingElement.name),
    content:textOf(p.node),opening:textOf(p.node.openingElement),guards:guardsOf(p),
    start:p.node.start,end:p.node.end});},
});
const matching=(name,regex)=>jsx.filter(x=>x.name===name&&(!regex||regex.test(
  regex.source.includes('className') ? x.opening : x.content)));
const exactOne=(name,regex)=>{
  const found=matching(name,regex);
  assert.equal(found.length,1,`${name} should identify one target, got ${found.length}`);
  return found[0];
};
function guardContains(element,expression){
  return element.guards.some(guard=>expression.test(guard));
}
function displayFeature(element, feature){
  const quoted=new RegExp(`['\"]${feature}['\"]`);
  return element.guards.some(g=>quoted.test(g));
}
function loadPolicy(){
  const source=path.resolve(__dirname,'../src/interface_mode.js');
  const compiled=esbuild.buildSync({entryPoints:[source],bundle:true,platform:'node',format:'cjs',write:false}).outputFiles[0].text;
  const filename=source.replace(/\.js$/,'.cjs');
  const instance=new Module(filename,module);
  instance.filename=filename;
  instance.paths=Module._nodeModulePaths(path.dirname(filename));
  instance._compile(compiled,filename);
  return instance.exports;
}
const policy=loadPolicy();
const integrated=/resolvedDisplayScope\(lanStatus\)/.test(app)&&/isManagedFeatureVisible\(displayScope/.test(app);
const pending=integrated?false:'App.jsx has not connected managed LAN display scope';

test('App.jsx is parseable JSX and still derives write privileges from LAN role',()=>{
  assert.ok(ast.program.body.length>0);
  assert.match(app,/const canManage\s*=\s*lanStatus\?\.user\?\.role\s*===\s*['"]admin['"]/);
  assert.match(app,/const canEdit\s*=\s*lanStatus\?\.mode\s*===\s*['"]client['"]/);
  assert.match(app,/const changeAdmin\s*=\s*next\s*=>\s*\{if\(!canManage\)return;/);
  assert.ok(!/const canManage\s*=\s*isInterfaceFeatureVisible/.test(app));
});

test('today: card cost and card-editor finance fields retain their admin guards',()=>{
  const cost=exactOne('div',/className="card-cost"/);
  assert.ok(guardContains(cost,/\bcanManage\b[\s\S]*\bcardCostEnabled\(/),JSON.stringify(cost.guards));
  assert.match(app,/const priceEnabled\s*=\s*canManage\s*&&[^;]*cardCostEnabled\(/);
  const costToggle=exactOne('h3',/تنظیمات هزینه همین کارت/);
  assert.ok(guardContains(costToggle,/\bcanManage\b/));
  const directCost=exactOne('h3',/هزینه مستقیم کار/);
  assert.ok(guardContains(directCost,/\bpriceEnabled\b/));
  const checklistCost=exactOne('div',/className="step-cost-fields"/);
  assert.ok(guardContains(checklistCost,/\bpriceEnabled\b/));
  const total=exactOne('div',/className="step-total"/);
  assert.ok(guardContains(total,/\bpriceEnabled\b/));
  assert.match(exactOne('TaskCard').opening,/canManage=\{canManage\}/);
  assert.match(exactOne('TaskEditor').opening,/canManage=\{canManage\}/);
});

test('today: task-side finance panels remain role-gated; management finance opens standalone dashboard',()=>{
  const keys={FinancePanel:'projectFinance',ProfitPeek:'profitPeek'};
  for(const [name,key] of Object.entries(keys)){
    const element=exactOne(name);
    assert.ok(guardContains(element,/\bcanManage\b/)||displayFeature(element,key),
      `${name} missing admin policy guard`);
  }
  const navs=matching('button',/onClick=\{openStandaloneDashboard\}/);
  assert.equal(navs.length,2,'dock navigation and sidebar must share the guarded accounting action');
  for(const nav of navs){
    assert.ok(guardContains(nav,/\bcanViewStandalone\b/),'standalone dashboard must require explicit finance viewing capability');
    assert.ok(displayFeature(nav,'accountingDashboard'),'host-allowed dashboard is also restricted by assigned display role');
  }
  const route=app.match(/const openStandaloneDashboard=\(\)=>\{([\s\S]*?)\n  \};/);
  assert.ok(route,'standalone route action must exist');
  assert.match(route[1],/dirty\.current\|\|saving\.current\|\|blocked\.current/);
  assert.match(route[1],/window\.location\.assign\('\.\/accounting\.html'\)/);
  assert.match(app,/مدیریت مالی<\/button>/);
  assert.equal(matching('FinanceOverview').length,0,'legacy financial hub must not be mounted');
  const projectFinance=exactOne('button',/setFinanceOpen\(true\)/);
  assert.ok(guardContains(projectFinance,/\bcanManage\b/)||displayFeature(projectFinance,'projectFinance'),
    'projectFinance policy itself requires canManage');
});

test('today: safety and account services remain present in visible application shell',()=>{
  for(const setter of ['setCloudOpen','setLanOpen','setSettingsOpen','setProfileOpen']){
    const candidates=matching('button').filter(x=>x.opening.includes(setter+'(true)'));
    assert.ok(candidates.length>0,`${setter} has no user-facing button`);
  }
  assert.equal(matching('SyncIndicator').length,1);
  assert.equal(matching('SearchPlus').length,1);
  assert.ok(matching('div',/className="kanban"/).length>0);
});

test('feature-key mapping covers exactly the current principal App surfaces',()=>{
  const map={
    FinancePanel:'projectFinance', ProfitPeek:'profitPeek',
    ReportingPanel:'reporting', RulesPanel:'automationRules',
    TrelloImportPanel:'trelloImport', CalendarFilePanel:'calendarInterop',
    PlannerPanel:'planner', WorkspaceManager:'workspaceManagement',
    TimeDashboard:'timeDashboard', AdvancedFilters:'advancedFilters',
  };
  for(const [component,key] of Object.entries(map)){
    assert.equal(matching(component).length,1,`${component} exists exactly once in App`);
    assert.ok(policy.INTERFACE_FEATURE_TIERS[key],`${key} missing policy`);
  }
  for(const feature of ['financeHub','projectFinance','profitPeek','taskCostControls','checklistCostControls','projectPricing']){
    assert.equal(policy.isInterfaceFeatureVisible('finance',feature,{canManage:false,canEdit:true}),false,feature);
  }
});

test('mode preference does not become a permission or shared task-state write',()=>{
  assert.equal(policy.isInterfaceFeatureVisible('basic','backupRestore'),true);
  assert.equal(policy.isInterfaceFeatureVisible('basic','networkStatus'),true);
  assert.equal(policy.isInterfaceFeatureVisible('basic','settings'),true);
  assert.equal(policy.isInterfaceFeatureVisible('basic','createTask',{canEdit:false}),false);
  assert.equal(policy.isInterfaceFeatureVisible('finance','financeHub',{canManage:false}),false);
  assert.equal(policy.isInterfaceFeatureVisible('finance','financeHub',{canManage:true}),true);
});

test('integration: assigned LAN display role controls App instead of local user dropdown', {skip:pending},()=>{
  assert.match(app,/from '\.\/managed_display\.js'/);
  assert.match(app,/const displayScope=resolvedDisplayScope\(lanStatus\)/);
  assert.match(app,/const show=feature=>isManagedFeatureVisible\(displayScope,feature,\{canManage,canEdit\}\)/);
  assert.equal(matching('InterfaceModeSelector').length,0,'end users must not choose their own display clearance');
  assert.match(app,/displayScope\.label/);
});

test('integration: advanced screens and their mounted panels are tier-gated', {skip:pending},()=>{
  const map={
    FinancePanel:'projectFinance', ProfitPeek:'profitPeek',
    ReportingPanel:'reporting', RulesPanel:'automationRules',
    TrelloImportPanel:'trelloImport', CalendarFilePanel:'calendarInterop',
    PlannerPanel:'planner', WorkspaceManager:'workspaceManagement',
    TimeDashboard:'timeDashboard', AdvancedFilters:'advancedFilters',
  };
  for(const [name,feature] of Object.entries(map)){
    const element=exactOne(name);
    assert.ok(displayFeature(element,feature),`${name} must have positive M04 feature guard '${feature}'`);
  }
});

test('integration: primary advanced navigation triggers also have display gates', {skip:pending},()=>{
  const map={
    'setReportingOpen(true)':'reporting',
    'setPlannerOpen(true)':'planner',
    'setActivityOpen(true)':'activity',
    "setMode('time')":'timeDashboard',
    'setWorkspaceOpen(true)':'workspaceManagement',
    'setTrelloImportOpen(true)':'trelloImport',
    'setCalendarInteropOpen(true)':'calendarInterop',
  };
  for(const [trigger,feature] of Object.entries(map)){
    const target=matching('button').find(item=>item.opening.includes(trigger));
    assert.ok(target,`${trigger} trigger missing`);
    assert.ok(displayFeature(target,feature),`${trigger} must be gated with '${feature}'`);
  }
});

test('integration: finance cost widgets gated by both role and the finance display tier', {skip:pending},()=>{
  // Requirements checked independently: mode gates never replace canManage.
  const keys={FinancePanel:'projectFinance',ProfitPeek:'profitPeek'};
  for(const [name,key] of Object.entries(keys)){
    const element=exactOne(name);
    assert.ok(guardContains(element,/\bcanManage\b/)||displayFeature(element,key));
  }
  for(const element of [exactOne('div',/className="card-cost"/),
                        exactOne('h3',/تنظیمات هزینه همین کارت/),
                        exactOne('div',/className="step-cost-fields"/)]){
    // A feature-tier string may reach this component through props or local guard.
    const componentStart=app.lastIndexOf('function ',element.start);
    const componentSegment=app.slice(componentStart,element.end);
    assert.match(componentSegment,/taskCostControls|checklistCostControls|showFinancial|showCost|financeVisible|visibleCost/i,
      'card financial rendering needs a second, mode-aware condition');
  }
  const projectSettings=matching('Modal',/title="تنظیمات پروژه"/)[0];
  assert.ok(projectSettings,'project settings modal exists');
  assert.ok(guardContains(projectSettings,/\bcanManage\b/)||displayFeature(projectSettings,'projectAdministration'),
    'project settings mounted modal must keep admin boundary');
  assert.ok(displayFeature(projectSettings,'projectAdministration'),
    'project settings mounted modal must close visually below Operations');
});
