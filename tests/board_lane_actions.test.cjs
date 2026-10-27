'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const esbuild=require('esbuild');
const Module=require('node:module');
const root=path.resolve(__dirname,'..');
const app=fs.readFileSync(path.join(root,'src/App.jsx'),'utf8');
const source=fs.readFileSync(path.join(root,'src/board_lane_actions.jsx'),'utf8');
const bundled=esbuild.buildSync({entryPoints:[path.join(root,'src/board_lane_actions.jsx')],bundle:true,platform:'node',format:'cjs',external:['react','react-dom','lucide-react'],write:false}).outputFiles[0].text;
const loaded=new Module('board_lane_actions',module);loaded.filename=path.join(root,'src/board_lane_actions.jsx');loaded.paths=Module._nodeModulePaths(root);loaded._compile(bundled,loaded.filename);
const {lanePopupPosition}=loaded.exports;

test('popup is clamped to the viewport and moves above a low button',()=>{
  const point=lanePopupPosition({left:940,top:700,bottom:732},{width:290,height:260},1024,768);
  assert.equal(point.left,726);
  assert.equal(point.top,435);
  assert.ok(point.left>=8&&point.left+290<=1024);
  const upper=lanePopupPosition({left:12,top:8,bottom:44},{width:290,height:180},1024,768);
  assert.equal(upper.top,49);
});
test('all lane actions are scoped by saved stage id and admin grants',()=>{
  assert.match(app,/import \{LaneActionsMenu\} from '\.\/board_lane_actions\.jsx'/);
  assert.match(app,/canManage=\{canManage&&show\('boardAdministration'\)\}/);
  assert.match(app,/onSave=\{fields=>updateStagePresentation\(stage\.id,fields\)\}/);
  assert.match(app,/onArchive=\{activeBoard\?/);
  assert.match(app,/updateBoardListArchive\(stage\.id\)/);
  assert.match(source,/role="dialog"/);
  assert.match(source,/onSave\?\.\(\{color:e\.target\.value\}\)/);
  assert.match(source,/document\.addEventListener\('pointerdown',close,true\)/);
});
test('inline add-list UI stays inside the board and validates input',()=>{
  assert.ok(app.indexOf('const [workspaceId,setWorkspaceId]') <
    app.indexOf('},[selected,boardId,workspaceId])'),
    'workspaceId must initialize before entering any hook dependency array');
  assert.match(app,/className="kanban-add-list"/);
  assert.match(app,/className="kanban-add-list__trigger"/);
  assert.match(app,/className="kanban-add-list__form"/);
  assert.match(app,/maxLength=\{100\}/);
  assert.match(app,/if\(!canManage\|\|!label\|\|label\.length>100\)return/);
  assert.match(app,/stages:\[\.\.\.board\.stages,nextStage\]/);
  assert.match(app,/setAddingLane\(false\)/);
  assert.match(app,/className="lane-add-card"/);
});
