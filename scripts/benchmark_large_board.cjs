'use strict';
/**
 * M03 synthetic Node benchmark: NO browser/FPS, APPDATA, user data or writes.
 * Run: node --expose-gc scripts/benchmark_large_board.cjs
 * stdout: metadata and a JSON line for 1000, 5000 and 10000 synthetic cards.
 */
const path = require('node:path');
const Module = require('node:module');
const esbuild = require('esbuild');
const {performance} = require('node:perf_hooks');
const root = path.resolve(__dirname,'..');
const filepath = path.join(root,'src','board_performance.js');
const compiled = esbuild.buildSync({
  entryPoints:[filepath],bundle:true,platform:'node',format:'cjs',write:false,
}).outputFiles[0].text;
const loader = new Module(filepath+'.benchmark.cjs',module);
loader.filename = filepath+'.benchmark.cjs';
loader.paths = Module._nodeModulePaths(path.dirname(filepath));
loader._compile(compiled,loader.filename);
const {createBoardPerformanceIndex} = loader.exports;
const SIZES=[1000,5000,10000];
const SAMPLES=9;
const BYTES=1024*1024;
const round=n=>Math.round(n*1000)/1000;
const mib=n=>round(n/BYTES);
function median(input) {
  const values=[...input].sort((a,b)=>a-b);
  return values[Math.floor(values.length/2)];
}
function data(count) {
  const stages=['inbox','active','review','done'].map(id=>({id,label:id}));
  const projects=Array.from({length:3},(_,i)=>({id:'project-'+i,
    price:7500000+i*1000000}));
  const workspaces=[{id:'workspace-0',archived:false},
                    {id:'workspace-1',archived:false}];
  const boards=Array.from({length:24},(_,i)=>({
    id:'board-'+i,workspaceId:'workspace-'+(i%2),
    projectId:'project-'+(i%3),archived:false,stages,
  }));
  const tasks=Array.from({length:count},(_,i)=>{
    // 60% of tasks land on one single large board. Remaining cards are
    // distributed over the other 23 boards to exercise both bucket types.
    const index=i%10<6?0:1+((i*7)%23);
    const listId=stages[i%4].id;
    return {
      id:'benchmark-card-'+i,
      boardId:'board-'+index,projectId:'project-'+(index%3),
      listId,status:listId,
      priority:i%13===0?'high':'medium',
      title:'ساختگی تست عملکرد '+i,
      description:'No confidential details '+(i%100),
      // A few non-empty reports/checklists to model realistic card payload.
      reports:i%11===0?[{summary:'Synthetic update'}]:[],
      checklist:[{id:'step-'+i,text:'synthetic',done:i%3===0,cost:3100}],
      cardOrder:i,deleted:i%37===0,archived:i%43===0,cost:26000,
    };
  });
  return {version:1,projects,workspaces,boards,stages,tasks,
          finance:{invoices:[],ledger:[]}};
}
function timed(fn) {
  const begin=performance.now();
  const result=fn();
  return {ms:performance.now()-begin,result};
}
console.log(JSON.stringify({kind:'environment',node:process.version,
  platform:process.platform,architecture:process.arch,
  machine:process.env.COMPUTERNAME?'local Windows benchmark':'runtime',
  gcExposed:typeof global.gc==='function',
  samples:SAMPLES,note:'Synthetic Node CPU measurements, NOT UI FPS or render timing'}));
for (const size of SIZES) {
  if (global.gc) global.gc();
  const fixture=data(size);
  if (global.gc) global.gc();
  const before=process.memoryUsage();
  const timings={index:[],workspaceQuery:[],groupBoard:[],lanePage:[]};
  let index;
  let visible=0;
  for (let i=0;i<SAMPLES;i++) {
    const build=timed(()=>createBoardPerformanceIndex(fixture,{
      permittedProjectIds:['project-0','project-1'],
    }));
    index=build.result;
    timings.index.push(build.ms);
    const workspace=timed(()=>index.selectActiveCards({
      workspaceId:'workspace-0',projectId:'project-0',priority:'high',
    }));
    timings.workspaceQuery.push(workspace.ms);
    const group=timed(()=>index.groupActiveCards({boardId:'board-0'}));
    timings.groupBoard.push(group.ms);
    const page=timed(()=>index.getLanePage('board-0','inbox',{limit:60}));
    timings.lanePage.push(page.ms);
    visible=index.visibleCount;
    if (page.result.cards.length>60 ||
        page.result.cards.length>page.result.total ||
        group.result.size>4 ||
        workspace.result.some(t=>t.projectId!=='project-0')) {
      throw new Error('Benchmark fixture invariant broken');
    }
  }
  const after=process.memoryUsage();
  console.log(JSON.stringify({
    kind:'synthetic',cards:size,boards:24,workspaces:2,
    maxCardsInBoard:fixture.tasks.filter(t=>t.boardId==='board-0').length,
    permittedProjectIds:2,activeVisibleCards:visible,
    samples:SAMPLES,
    medianMs:Object.fromEntries(Object.entries(timings).map(([k,v])=>[k,round(median(v))])),
    maxMs:Object.fromEntries(Object.entries(timings).map(([k,v])=>[k,round(Math.max(...v))])),
    memoryMiB:{
      heapBefore:mib(before.heapUsed),heapAfter:mib(after.heapUsed),
      heapDelta:mib(after.heapUsed-before.heapUsed),
      rssBefore:mib(before.rss),rssAfter:mib(after.rss),
    },
    caveat:'Heap delta includes GC/JIT/benchmark overhead, not measured index size; no FPS claims',
  }));
}
