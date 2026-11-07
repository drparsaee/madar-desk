'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Module=require('node:module');
const esbuild=require('esbuild');

const root=path.resolve(__dirname,'..');
const file=path.join(root,'src/board_table_preferences.js');
const bundled=esbuild.buildSync({entryPoints:[file],bundle:true,platform:'node',
  format:'cjs',write:false}).outputFiles[0].text;
const loader=new Module(file+'.test.cjs',module);
loader.filename=file+'.test.cjs';
loader.paths=Module._nodeModulePaths(path.dirname(file));
loader._compile(bundled,loader.filename);
const {boardTableColumns,readBoardViewPreferences,saveBoardViewPreferences,
  normalizeBoardViewPreferences}=loader.exports;

function storage(){
  const values=new Map();
  return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,String(value))};
}

test('Gantt view survives reload while remaining isolated by board and user',()=>{
  const db=storage(),columns=boardTableColumns(null);
  const initial=readBoardViewPreferences(db,'owner','board-a',columns);
  assert.equal(initial.mode,'board');
  saveBoardViewPreferences(db,'owner','board-a',{mode:'gantt'},columns);
  assert.equal(readBoardViewPreferences(db,'owner','board-a',columns).mode,'gantt');
  assert.equal(readBoardViewPreferences(db,'owner','board-b',columns).mode,'board');
  assert.equal(readBoardViewPreferences(db,'viewer','board-a',columns).mode,'board');
  saveBoardViewPreferences(db,'owner','board-a',{mode:'table'},columns);
  assert.equal(readBoardViewPreferences(db,'owner','board-a',columns).mode,'table');
  saveBoardViewPreferences(db,'owner','board-a',{mode:'gantt'},columns);
  assert.equal(readBoardViewPreferences(db,'owner','board-a',columns).mode,'gantt');
  assert.equal(normalizeBoardViewPreferences({mode:'unexpected'},columns).mode,'board');
});

test('App restores the scoped Gantt view, checks role visibility, and remounts for another board',()=>{
  const app=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
  assert.match(app,/switchBoardDisplay\('gantt'\)/);
  assert.match(app,/const allowedGantt=isManagedFeatureVisible\(displayScope,'timelineView'/);
  assert.match(app,/const next=saved.mode==='gantt'&&!allowedGantt\?'board':saved.mode;/);
  assert.match(app,/setMode\(previous=>previous==='time'\?previous:next\)/);
  assert.match(app,/<GanttView key=\{boardViewScope\} tasks=\{filtered\}/);
});
