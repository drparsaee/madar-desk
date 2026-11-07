'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');
const root=path.resolve(__dirname,'..');
const entry=path.join(root,'src/teamplus.jsx');
const code=esbuild.buildSync({entryPoints:[entry],platform:'node',bundle:true,format:'cjs',write:false,
  loader:{'.css':'empty'},external:['react','react/jsx-runtime','react-dom','react-dom/client','lucide-react']}).outputFiles[0].text;
const mod=new Module(entry,module);mod.filename=entry;mod.paths=Module._nodeModulePaths(path.dirname(entry));mod._compile(code,entry);
const {eligibleMentionUsers,activeMentionToken}=mod.exports;
const accounts=[
 {username:'alice',role:'admin',projects:[],displayName:'مدیر'},
 {username:'bob',role:'editor',projects:['project-1'],displayName:'بابک'},
 {username:'dave',role:'viewer',projects:null,displayName:'داوود'},
 {username:'other',role:'editor',projects:['private-project'],displayName:'نباید دیده شود'},
 {username:'outsider',role:'viewer',projects:[]},
 {username:'selfuser',role:'editor',projects:['project-1']},
 {username:'fake',role:'unknown',projects:['project-1']},
 {username:'short',role:'viewer'},
 {username:'u$bad',role:'admin',projects:null},
 {username:'bob',role:'editor',projects:['project-1']}
];
test('mention candidates fail closed on missing scope; match backend role/grants and username validation',()=>{
 assert.deepEqual(eligibleMentionUsers(accounts,'project-1','selfuser').map(item=>item.username),['alice','bob','dave']);
 assert.deepEqual(eligibleMentionUsers(accounts,'private-project','selfuser').map(item=>item.username),['alice','dave','other']);
 assert.deepEqual(eligibleMentionUsers(accounts,'missing-project','selfuser').map(item=>item.username),['alice','dave']);
 assert.deepEqual(eligibleMentionUsers(accounts,'','selfuser'),[]);
 assert.deepEqual(eligibleMentionUsers(accounts,undefined,'selfuser'),[]);
 assert.deepEqual(eligibleMentionUsers(undefined,'project-1','selfuser'),[]);
});
test('mention token respects email, double-@, text boundary and caret inside username',()=>{
 assert.deepEqual(activeMentionToken('hi @bo',6),{start:3,end:6,query:'bo'});
 assert.deepEqual(activeMentionToken('hi @bob more',6),{start:3,end:7,query:'bo'});
 assert.deepEqual(activeMentionToken('@',1),{start:0,end:1,query:''});
 assert.equal(activeMentionToken('mail a@bob.com',10),null);
 assert.equal(activeMentionToken('@@bob',5),null);
 assert.equal(activeMentionToken('word@bob',8),null);
 assert.equal(activeMentionToken('hi @bo more',9),null);
});

let chromium;
try{({chromium}=require('playwright'));}
catch{try{({chromium}=require('C:/Users/Parsa/AppData/Roaming/npm/node_modules/playwright'));}catch{}}
const chrome='C:/Program Files/Google/Chrome/Application/chrome.exe';
test('card and project @mention browser: keyboard, mouse, scope, IME, Escape, submit, edit and retry',
 {skip:!chromium||!fs.existsSync(chrome),timeout:60000},async()=>{
 const fixture=`import React,{useState} from 'react';
   import{createRoot}from'react-dom/client';
   import{CardComments,ProjectConversation}from './src/teamplus.jsx';
   const accounts=${JSON.stringify(accounts)};
   window.__mentionTest={commands:[],rejectOnce:false,comments:[],projectComments:[]};
   const api={collabRead:async(kind)=>kind==='comments'?window.__mentionTest.comments:window.__mentionTest.projectComments,
     collabCommand:async command=>{window.__mentionTest.commands.push(command);
       if(window.__mentionTest.rejectOnce){window.__mentionTest.rejectOnce=false;throw Error('synthetic error');}
       const item={id:'c_'+window.__mentionTest.commands.length,author:'selfuser',text:command.text,
         createdAt:'2026-11-07T10:00:00Z',updatedAt:'2026-11-07T10:00:00Z',deletedAt:null};
       if(command.type==='comment.add'||command.type==='comment.reply')window.__mentionTest.comments.push(item);
       if(command.type==='project.comment.add')window.__mentionTest.projectComments.push(item);
       return {commentId:item.id};}};
   function Demo(){const [project,setProject]=useState(false),[scope,setScope]=useState(true);
     return <><button id='mode' onClick={()=>setProject(p=>!p)}>change conversation</button>
       <button id='scope' onClick={()=>setScope(s=>!s)}>toggle supplied users</button>
       {project?<ProjectConversation key={'project:'+scope} projectId='project-1' projectName='Testing'
         api={api} canEdit username='selfuser' users={scope?accounts:undefined} onClose={()=>{}}/>:
       <CardComments key={'card:'+scope} cardId='card-1' projectId='project-1'
         users={scope?accounts:undefined} api={api} canEdit username='selfuser'/>}</>}
   createRoot(document.getElementById('root')).render(<Demo/>);`;
 const bundled=esbuild.buildSync({stdin:{contents:fixture,resolveDir:root,sourcefile:'p2-mentions-fixture.jsx',loader:'jsx'},
   bundle:true,write:false,platform:'browser',format:'iife',loader:{'.css':'empty'}}).outputFiles[0].text;
 const browser=await chromium.launch({headless:true,executablePath:chrome});
 try{
   for(const width of [480,1440]){
     const page=await browser.newPage({viewport:{width,height:800},locale:'fa-IR'});
     const errors=[];page.on('pageerror',error=>errors.push(error.message));
     await page.setContent(`<html lang="fa" dir="rtl"><head><meta charset="utf-8"/><style>
       .overlay{position:fixed;inset:0;display:grid;place-items:center;background:#aaa}
       .dialog{background:#fff;color:#233149;width:min(580px,100%);max-height:90vh;overflow:auto}
       .dialog-body{padding:12px;overflow:auto}.team-comment-section{padding:12px;max-width:min(590px,100vw)}
       .comment-compose{margin:12px 0;display:flex;flex-wrap:wrap;gap:8px}
       textarea{min-height:65px}
       </style></head><body><div id="root"></div></body></html>`);
     await page.addStyleTag({content:fs.readFileSync(path.join(root,'src/teamplus.css'),'utf8')});
     await page.addScriptTag({content:bundled});
     const editor=page.getByRole('combobox',{name:'پیام جدید'});
     await editor.fill('مرحبا @');
     const list=page.getByRole('listbox',{name:'کاربران مجاز برای اشاره'});
     await list.waitFor();
     assert.deepEqual(await list.getByRole('option').allTextContents(),['@aliceمدیر','@bobبابک','@daveداوود']);
     assert.equal(await editor.getAttribute('aria-expanded'),'true');
     await page.keyboard.press('ArrowDown');
     assert.match(await editor.getAttribute('aria-activedescendant'),/-1$/);
     await page.keyboard.press('Enter');
     assert.equal(await editor.inputValue(),'مرحبا @bob ');
     assert.equal(await list.count(),0);
     assert.equal((await page.evaluate(()=>window.__mentionTest.commands)).length,0);
     await editor.fill('mail a@bob.com');
     assert.equal(await list.count(),0);
     await editor.fill('hello @d');
     assert.equal(await list.getByRole('option').count(),1);
     await page.keyboard.press('Escape');
     assert.equal(await list.count(),0);
     await editor.press('Enter');
     assert.match(await editor.inputValue(),/\n$/);
     await editor.fill('ime @');
     await editor.evaluate(el=>el.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true})));
     assert.equal(await list.count(),0);
     await editor.press('Control+Enter');
     assert.equal((await page.evaluate(()=>window.__mentionTest.commands)).length,0);
     await editor.evaluate(el=>el.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true})));
     await list.waitFor();
     await list.getByRole('option').filter({hasText:'@alice'}).click();
     assert.equal(await editor.inputValue(),'ime @alice ');
     await page.evaluate(()=>window.__mentionTest.rejectOnce=true);
     await editor.press('Control+Enter');
     await page.getByRole('alert').waitFor();
     await editor.press('Control+Enter');
     const commands=await page.evaluate(()=>window.__mentionTest.commands);
     assert.equal(commands.length,2);
     assert.equal(commands[0].type,'comment.add');
     assert.equal(commands[0].eventId,commands[1].eventId);
     assert.equal(commands[0].text,'ime @alice');
     await page.getByRole('button',{name:'ویرایش نظر'}).first().click();
     const editing=page.getByRole('combobox',{name:'ویرایش پیام'});
     await editing.fill('edited @bo');
     await list.getByRole('option').first().click();
     assert.equal(await editing.inputValue(),'edited @bob ');
     await page.getByRole('button',{name:'انصراف'}).first().click();
     await page.locator('#scope').click();
     const scoped=page.getByRole('combobox',{name:'پیام جدید'});
     await scoped.fill('@');
     assert.equal(await list.count(),0,'no account list means no candidates');
     await page.locator('#scope').click();
     await page.locator('#mode').click();
     const projectInput=page.getByRole('combobox',{name:'پیام جدید'});
     await projectInput.fill('شروع @bo');
     await list.getByRole('option').first().click();
     assert.equal(await projectInput.inputValue(),'شروع @bob ');
     await projectInput.press('Control+Enter');
     const last=await page.evaluate(()=>window.__mentionTest.commands.at(-1));
     assert.equal(last.type,'project.comment.add');
     assert.equal(last.projectId,'project-1');
     assert.equal(last.text,'شروع @bob');
     assert.deepEqual(errors,[]);
     await page.close();
   }
 }finally{await browser.close();}
});
