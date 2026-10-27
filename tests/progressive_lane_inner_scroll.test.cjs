const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const src=fs.readFileSync(path.join(__dirname,'../src/progressive_lane.jsx'),'utf8');
test('progressive cards use the actual kanban list scrollport without page jumps',()=>{
  assert.match(src,/const nearestScroller=\(\)=>root\.current\?\.closest\('\.kanban-lane'\)/);
  assert.match(src,/\?root\.current:root\.current\?\.closest\('\.workspace-scroll'\)/);
  assert.equal((src.match(/const scroller=nearestScroller\(\)/g)||[]).length,2);
  assert.doesNotMatch(src,/container\.closest\('\.workspace-scroll'\)/);
});
