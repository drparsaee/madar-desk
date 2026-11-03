'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const esbuild=require('esbuild');
let playwright;
try {playwright=require('playwright');}
catch {playwright=require(path.join(process.env.USERPROFILE||process.env.HOME,
  'AppData','Roaming','npm','node_modules','playwright'));}
const root=path.resolve(__dirname,'..');
const built=esbuild.buildSync({stdin:{contents:`
import React from 'react';
import {createRoot} from 'react-dom/client';
import {TrelloImportPanel} from './src/trello_import.jsx';
window.synthetic={closed:false,state:{version:1,
  workspaces:[{id:'w',name:'Workspace'}],
  projects:[{id:'p',name:'Original',color:'#556677',costEnabled:false,price:0}],
  boards:[],stages:[{id:'inbox',label:'Inbox',color:'#888888'}],
  tasks:[{id:'keep',projectId:'p',title:'Existing',status:'inbox',priority:'medium',checklist:[],reports:[]}],
  settings:{theme:'dark'}}};
createRoot(document.getElementById('root')).render(React.createElement(TrelloImportPanel,{
  onClose:()=>{window.synthetic.closed=true},
  onImport:fn=>{window.synthetic.state=fn(window.synthetic.state)}
}));`,
  resolveDir:root,sourcefile:'board-import-fixture.jsx',loader:'jsx'},
  platform:'browser',format:'iife',bundle:true,write:false,
  outdir:'board-import-test-build',loader:{'.css':'css'}}).outputFiles;
const js=built.find(file=>file.path.endsWith('.js')).text;
const css=built.find(file=>file.path.endsWith('.css')).text;
async function fixture(browser){
  const page=await browser.newPage();
  await page.setContent('<html lang="fa" dir="rtl"><meta charset="utf-8"><div id="root"></div></html>');
  await page.addStyleTag({content:css});
  await page.addScriptTag({content:js});
  const dialog=page.locator('section.trello-import-dialog');
  await dialog.waitFor();
  return {page,dialog,source:dialog.locator('select'),upload:dialog.locator('input[type=file]'),
    confirm:dialog.locator('.trello-import-actions .btn.primary')};
}

test('Notion CSV dialog previews import and retains all existing task IDs',async t=>{
  const browser=await playwright.chromium.launch({channel:'msedge',headless:true});
  t.after(()=>browser.close());
  const {page,dialog,source,upload,confirm}=await fixture(browser);
  await source.selectOption('notion');
  assert.equal(await confirm.isDisabled(),true);
  await upload.setInputFiles({name:'tasks.csv',mimeType:'text/csv',
    buffer:Buffer.from('Name,Status,Client\nA,Doing,ACME\nB,Done,Test')});
  await dialog.locator('[role=status]').waitFor();
  assert.equal(await confirm.isEnabled(),true);
  await confirm.click();
  const state=await page.evaluate(()=>window.synthetic);
  assert.equal(state.state.tasks.length,3);
  assert.equal(state.state.tasks[2].id,'keep');
  assert.equal(state.state.boards[0].customFields.length,1);
  assert.equal(state.closed,true);
});

test('Notion CSV mode rejects wrong file extension without mutating state',async t=>{
  const browser=await playwright.chromium.launch({channel:'msedge',headless:true});
  t.after(()=>browser.close());
  const {page,dialog,source,upload,confirm}=await fixture(browser);
  await source.selectOption('notion');
  await upload.setInputFiles({name:'wrong.json',mimeType:'application/json',
    buffer:Buffer.from('{}')});
  await dialog.locator('[role=alert]').waitFor();
  assert.equal(await confirm.isDisabled(),true);
  assert.equal(await page.evaluate(()=>window.synthetic.state.tasks.length),1);
});
