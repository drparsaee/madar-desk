'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const {spawnSync}=require('node:child_process');
const esbuild=require('esbuild');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');

const root=path.resolve(__dirname,'..');
const load=(file)=>{
  const source=path.join(root,file);
  const result=esbuild.buildSync({entryPoints:[source],bundle:true,platform:'node',format:'cjs',
    write:false,loader:{'.css':'empty'},external:['react','react-dom','lucide-react']});
  const instance=new Module(source,module);
  instance.filename=source;
  instance.paths=Module._nodeModulePaths(path.dirname(source));
  instance._compile(result.outputFiles[0].text,source);
  return instance.exports;
};
const logic=load('src/automation_wizard_logic.js');
const panel=load('src/rulespanel.jsx');
const base={id:'rule-test',projectId:'p1',trigger:'card_moved',
  actionType:'comment',message:'پایان مرحله'};

function pythonCheck(script,input){
  const result=spawnSync('python',['-c',script],{cwd:root,input:JSON.stringify(input),encoding:'utf8'});
  assert.equal(result.status,0,result.stderr||result.stdout||'Python backend did not complete');
  return result.stdout.trim();
}

test('wizard offers only triggers defined in the collaboration domain',()=>{
  const allowed=JSON.parse(pythonCheck('import collab,json;print(json.dumps(sorted(collab.TRIGGERS)))',null));
  assert.deepEqual(Object.keys(logic.TRIGGER_INFO).sort(),allowed);
  assert.deepEqual(logic.TRIGGER_GROUPS.flatMap(group=>group.triggers).sort(),allowed);
  assert.deepEqual(Object.keys(logic.ACTION_INFO).sort(),['comment','notify']);
  assert.equal(logic.TRIGGER_GROUPS.find(group=>group.id==='content').triggers.length,0);
});

test('valid wizard output passes real Python rule.upsert and executes its event',()=>{
  const cases=[
    {rule:logic.buildAutomationRule({...base,id:'move-rule',limitToList:true,listId:'list-abc'}),eventData:{toColumnId:'list-abc'}},
    {rule:logic.buildAutomationRule({...base,id:'created-rule',trigger:'card_created',limitToList:true,listId:'list-abc'}),eventData:{toColumnId:'list-abc'}},
    {rule:logic.buildAutomationRule({...base,id:'label-rule',trigger:'label_changed'}),eventData:{labelId:'label-1'}},
    {rule:logic.buildAutomationRule({...base,id:'check-rule',trigger:'checklist_completed'}),eventData:{checklistId:'check-1'}},
    {rule:logic.buildAutomationRule({...base,id:'field-rule',trigger:'custom_field_changed'}),eventData:{fieldId:'field-1'}},
    {rule:logic.buildAutomationRule({...base,id:'due-rule',trigger:'due_soon',dueDay:'1'}),eventData:{dueWithinDays:1}},
    {rule:logic.buildAutomationRule({...base,id:'notify-rule',trigger:'card_moved',actionType:'notify',recipient:'bob',message:'کارت جابه‌جا شد'}),eventData:{toColumnId:'list-abc'}},
  ];
  const script=`import sys,json,collab
cases=json.load(sys.stdin)
accounts={"admin":{"username":"admin","role":"admin","projects":None},
          "alice":{"username":"alice","role":"editor","projects":["p1"]},
          "bob":{"username":"bob","role":"viewer","projects":["p1"]}}
for index,case in enumerate(cases):
    state=collab.empty_state()
    args={"accounts":accounts,"cards":[{"id":"c1","projectId":"p1"}],
          "projects":[{"id":"p1"}],"now":"2026-10-28T08:00:00Z"}
    created=collab.apply_command(state,{"type":"rule.upsert","eventId":"rule-event","rule":case["rule"]},actor="admin",**args)
    fired=collab.apply_command(created["state"],{"type":"event.publish","eventId":"card-event",
          "cardId":"c1","trigger":case["rule"]["trigger"],"data":case["eventData"]},actor="alice",**args)
    assert fired["result"]["matchedRules"]==1,(index,fired["result"])
    if case["rule"]["actions"][0]["type"]=="comment":
        assert len(fired["state"]["comments"])==1,index
    else:
        assert len(fired["state"]["notifications"])==1,index
print("accepted "+str(len(cases)))`;
  assert.equal(pythonCheck(script,cases),'accepted 7');
});

test('wizard refuses unsupported scheduling, actions, unsafe conditions and incomplete forms',()=>{
  assert.throws(()=>logic.buildAutomationRule({...base,trigger:'scheduled_daily'}),/رویداد/);
  assert.throws(()=>logic.buildAutomationRule({...base,actionType:'move_card'}),/عمل/);
  assert.throws(()=>logic.buildAutomationRule({...base,actionType:'notify',recipient:''}),/عضو/);
  assert.throws(()=>logic.buildAutomationRule({...base,message:' '}),/متن/);
  assert.throws(()=>logic.buildAutomationRule({...base,message:'x'.repeat(4001)}),/محدودیت/);
  assert.throws(()=>logic.buildAutomationRule({...base,trigger:'label_changed',limitToList:true,listId:'abc'}),/فهرست/);
  assert.throws(()=>logic.buildAutomationRule({...base,trigger:'due_soon',dueDay:'8'}),/موعد/);
  assert.throws(()=>logic.buildAutomationRule({...base,trigger:'card_created',dueDay:'1'}),/موعد/);
  assert.deepEqual(logic.buildAutomationRule({...base,trigger:'due_soon',dueDay:'0'}).conditions,
    [{field:'dueWithinDays',equals:0}]);
});

test('responsive dialog exposes five accessible sections and keeps old rule management entry points',()=>{
  const html=renderToStaticMarkup(React.createElement(panel.RulesPanel,{
    api:{collabRead:async()=>[],collabCommand:async()=>{}},
    project:{id:'p1',name:'پروژه تست'},users:[{username:'bob',displayName:'بابک'}],
    onClose:()=>{},initialListId:'list-abc',
  }));
  for(const label of ['قوانین','زمان‌بندی‌شده','موعد کارت','دکمه‌های کارت','دکمه‌های برد',
    'اتوماسیون مدار','قوانین پروژه','تازه‌سازی قوانین']){
    assert.ok(html.includes(label),label);
  }
  assert.match(html,/role="dialog" aria-modal="true"/);
  assert.match(html,/dir="rtl"/);
  const source=fs.readFileSync(path.join(root,'src/rulespanel.jsx'),'utf8');
  assert.match(source,/api\.collabCommand\(\{type:'rule\.upsert'/);
  assert.match(source,/api\.collabCommand\(\{type:'rule\.delete'/);
  assert.match(source,/api\.collabRead\('rules',project\.id\)/);
  assert.match(source,/api\.runDueScheduler\(\)/);
  assert.match(source,/initialListId/);
  const css=fs.readFileSync(path.join(root,'src/rulespanel.css'),'utf8');
  assert.match(css,/:root\[data-theme="dark"\] \.rule-dialog/);
  assert.match(css,/@media\(max-width:750px\)/);
  assert.match(css,/@media\(max-width:480px\)/);
});

test('component interaction flows through trigger, action, review and collabCommand with list scope',async()=>{
  // A local hook harness exercises React event callbacks without claiming browser E2E.
  // Browser DOM drivers are absent from this checkout.
  let cursor=0;
  const slots=[];
  const shim={
    ...React,
    useState(initial){
      const position=cursor++;
      if(!(position in slots))slots[position]=typeof initial==='function'?initial():initial;
      return [slots[position],value=>{
        slots[position]=typeof value==='function'?value(slots[position]):value;
      }];
    },
    useRef(initial){
      const position=cursor++;
      if(!(position in slots))slots[position]={current:initial};
      return slots[position];
    },
    useCallback:callback=>callback,
    useEffect:()=>{},
  };
  const source=path.join(root,'src/rulespanel.jsx');
  const result=esbuild.buildSync({entryPoints:[source],bundle:true,platform:'node',format:'cjs',
    write:false,loader:{'.css':'empty'},external:['react','react-dom','lucide-react']});
  const instance=new Module(source,module);
  instance.filename=source;instance.paths=Module._nodeModulePaths(path.dirname(source));
  instance.require=id=>id==='react'?shim:Module.prototype.require.call(instance,id);
  instance._compile(result.outputFiles[0].text,source);
  const issued=[];
  const existing=[];
  const props={project:{id:'p1',name:'آزمون'},users:[{username:'bob',displayName:'بابک'}],
    initialListId:'list-abc',onClose:()=>{},
    api:{collabRead:async()=>existing,collabCommand:async command=>{
      issued.push(command);
      if(command.type==='rule.upsert')existing.push(command.rule);
    }}};
  const render=()=>{cursor=0;return instance.exports.RulesPanel(props);};
  const elements=(node,found=[])=>{
    if(Array.isArray(node)){node.forEach(item=>elements(item,found));return found;}
    if(node&&typeof node==='object'&&node.props){
      found.push(node);elements(node.props.children,found);
    }
    return found;
  };
  const textOf=node=>{
    if(node===null||node===undefined||typeof node==='boolean')return '';
    if(Array.isArray(node))return node.map(textOf).join(' ');
    if(typeof node==='string'||typeof node==='number')return String(node);
    return node.props?textOf(node.props.children):'';
  };
  // Available controls are not disabled; check this explicitly before dispatch.
  const click=(tree,label)=>{
    const target=elements(tree).find(item=>item.type==='button'&&textOf(item).includes(label));
    assert.ok(target,'Expected button '+label);
    assert.notEqual(target.props.disabled,true,'Button should be enabled: '+label);
    return target.props.onClick();
  };

  click(render(),'ساخت قانون');
  let tree=render();
  assert.ok(textOf(tree).includes('وقتی این اتفاق افتاد'));
  assert.ok(textOf(tree).includes('انتقال کارت به فهرست'));
  click(tree,'ادامه');
  tree=render();
  assert.ok(textOf(tree).includes('این کار را انجام بده'));
  click(tree,'ثبت نظر خودکار');
  tree=render();
  const field=elements(tree).find(item=>item.type==='textarea');
  assert.ok(field);
  field.props.onChange({target:{value:'ثبت خودکار پس از انتقال'}});
  click(render(),'ادامه');
  tree=render();
  assert.ok(textOf(tree).includes('قانون را مرور کن'));
  assert.ok(textOf(tree).includes('فقط فهرست انتخاب‌شده'));
  await click(tree,'ذخیره و فعال‌سازی');
  assert.equal(issued.length,1);
  assert.equal(issued[0].type,'rule.upsert');
  assert.deepEqual(issued[0].rule.conditions,[{field:'toColumnId',equals:'list-abc'}]);
  assert.deepEqual(issued[0].rule.actions,[{type:'comment',text:'ثبت خودکار پس از انتقال'}]);
  assert.equal(issued[0].rule.trigger,'card_moved');
  assert.ok(textOf(render()).includes('قانون در پروژه ثبت شد'));
});
