'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
const source=name=>fs.readFileSync(path.join(root,'src',name),'utf8');

test('board card avoids repeated board/project labels and separate cover overlay',()=>{
  const app=source('App.jsx');
  const taskCard=app.slice(app.indexOf('function TaskCard('),app.indexOf('function WalletIcon('));
  assert.doesNotMatch(taskCard,/project-tiny/);
  assert.match(taskCard,/task-card--cover-full/);
  assert.match(taskCard,/task-card--cover-strip/);
  assert.match(taskCard,/coverTextColor\(cover.color\)/);
  const css=source('kanban_compact.css');
  assert.match(css,/\.task-card--cover-strip \.task-card-head/);
  assert.match(css,/\.task-card--cover-full\s*\{/);
});

test('inline add-card control retains a keyboard target without permanent vertical spacer',()=>{
  const app=source('App.jsx');
  const css=source('kanban_compact.css');
  assert.match(app,/className="lane-insert-slot"/);
  assert.match(app,/className="lane-insert-before"/);
  assert.match(css,/\.lane-insert-slot \{ block-size: 0; min-block-size: 0/);
  assert.match(css,/\.lane-insert-slot:is\(:hover, :focus-within\)/);
  assert.match(css,/\.lane-insert-before:focus-visible/);
});
