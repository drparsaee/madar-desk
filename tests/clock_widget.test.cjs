const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../src/clock_widget.js'),'utf8');
const values=[...source.matchAll(/id:'([^']+)'/g)].map(x=>x[1]);
test('clock widget choices explicitly cover time, date and hiding',()=>{
  assert.deepEqual(values,['both','clock','date','hidden']);
  assert.match(source,/CLOCK_WIDGET_MODES\.includes\(value\) \? value : 'both'/);
});
