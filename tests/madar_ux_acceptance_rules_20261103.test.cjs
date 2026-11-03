'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {UX_IDS,observation,assessAxe,assessContrast,assessTouch,summarize}=
  require('../scripts/madar_ux_acceptance_rules_20261103.cjs');

test('all ten UX identifiers are explicit and verdicts cannot invent successes',()=>{
  assert.deepEqual(UX_IDS,['UX-01','UX-02','UX-03','UX-04','UX-05',
    'UX-06','UX-07','UX-08','UX-09','UX-10']);
  assert.throws(()=>observation('UX-11','PASS','not allowed'));
  assert.throws(()=>observation('UX-01','PASS',''));
  assert.equal(summarize([]).overall,'BLOCKED');
});

test('axe 4.14 serious/critical violations fail; missing scan blocks',()=>{
  assert.equal(assessAxe(null).status,'BLOCKED');
  assert.equal(assessAxe({version:'4.13.0',violations:[]}).status,'BLOCKED');
  const scan={version:'4.14.0',violations:[{id:'color-contrast',impact:'serious'}],incomplete:[]};
  assert.equal(assessAxe(scan).status,'FAIL');
  assert.equal(assessAxe({...scan,violations:[{id:'minor',impact:'moderate'}]}).status,'PASS');
});

test('project contrast threshold is 4.5 even if axe considers large text exempt',()=>{
  assert.equal(assessContrast([]).status,'BLOCKED');
  assert.equal(assessContrast([{ratio:4.49}]).status,'FAIL');
  assert.equal(assessContrast([{ratio:4.5}]).status,'PASS');
  assert.equal(assessContrast([{ratio:5},{ratio:null}]).status,'BLOCKED');
});

test('44 by 44 applies to both dimensions of critical controls',()=>{
  assert.equal(assessTouch([]).status,'BLOCKED');
  assert.equal(assessTouch([{width:44,height:44}]).status,'PASS');
  assert.equal(assessTouch([{width:60,height:43}]).status,'FAIL');
});

test('a missing feature or unmeasured viewport never produces overall pass',()=>{
  const checks=UX_IDS.map(id=>observation(id,'PASS','synthetic contract fixture'));
  assert.equal(summarize(checks).overall,'PASS');
  checks[7]=observation('UX-08','MISSING','No authorized record search');
  assert.equal(summarize(checks).statusByUX['UX-08'].status,'MISSING');
  assert.equal(summarize(checks).overall,'FAIL');
  checks[7]=observation('UX-08','BLOCKED','No viewer role fixture');
  assert.equal(summarize(checks).overall,'BLOCKED');
});
