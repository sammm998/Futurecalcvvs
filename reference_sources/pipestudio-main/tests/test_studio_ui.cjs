const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements=new Map(),timers=[],intervals=new Map(),storage=new Map();
let clock=Date.now(),seq=0,reloads=0,activeTab='pipes',sheet='drawing',readonly=false,result={};
const element=id=>{if(!elements.has(id))elements.set(id,{append(){},textContent:'',disabled:false,hidden:false,classList:{toggle(){}},addEventListener(){},parentElement:{append(){}},dataset:{},querySelectorAll(){return[];}});return elements.get(id);};
class Clock extends Date {static now(){return clock;}}
const overview={counts:{open:0},styles:[],feedback:[],improvements:{candidates:[]}};
let jobState={id:'job-test',kind:'replay',status:'running',created_at:new Date(clock).toISOString(),progress:'Running Astra'};
const context={AbortController,clearTimeout(){},Date:Clock,document:{addEventListener(){},createElement:()=>({}),querySelector:element,querySelectorAll:()=>[]},window:{addEventListener(){},AssignmentContext:require('../vectorascore/static/assignment-context.js'),PipeReview:{setTab:t=>{activeTab=t;},state:()=>({sheet,readonly,R:result}),reload:async()=>{reloads++;result={llm:{mode:'pipe_final',...jobState.result.usage}};}}},
 localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
 setTimeout:(fn,ms)=>ms===15000?0:timers.push(fn),setInterval:fn=>{const id=++seq;intervals.set(id,fn);return id;},clearInterval:id=>intervals.delete(id),
 fetch:async url=>({ok:true,json:async()=>url.endsWith('overview')?overview:url.includes('queue?')?[]:jobState})};
vm.createContext(context);vm.runInContext(fs.readFileSync('vectorascore/static/studio.js','utf8'),context);
(async()=>{
 const studio=context.window.Studio;
 const pending=studio.job('replay',{sheet:'drawing',binding:'astra'});
 assert.equal(activeTab,'bindings');
 await pending;
 assert.equal(element('#run-astra').disabled,true);
 clock+=5000;for(const tick of intervals.values())tick();
 assert.match(element('#assignment-usage-detail').textContent,/5 s/);
 sheet='another';studio.renderAssignmentUsage();
 assert.doesNotMatch(element('#assignment-usage-detail').textContent,/Elapsed/);
 sheet='drawing';readonly=true;studio.renderAssignmentUsage();
 assert.doesNotMatch(element('#assignment-usage-detail').textContent,/Elapsed/);
 readonly=false;studio.renderAssignmentUsage();
 assert.match(element('#assignment-usage-detail').textContent,/5 s/);
 await timers.shift()(); // Running poll schedules the next poll.
 jobState={...jobState,status:'done',seconds:8.2,result:{usage:{seconds:7,tokens_in:1000,tokens_out:100,cached_tokens:500,usd:.0105,usage_complete:true}}};
 await timers.shift()();
 assert.equal(intervals.size,0);assert.equal(element('#run-astra').disabled,false);
 assert.match(element('#assignment-usage-detail').textContent,/7 s/);
 assert.match(element('#assignment-usage-detail').textContent,/1,100 tokens/);
 assert.match(element('#assignment-usage-detail').textContent,/0.0105 USD/);
 assert.equal(reloads,1);
 assert.equal(element('#progress').textContent,'');
 assert.equal(element('#notification').hidden,true);
 sheet='another';result={};studio.renderAssignmentUsage();
 assert.doesNotMatch(element('#assignment-usage-detail').textContent,/1,100/);
 readonly=true;result={llm:{mode:'full',seconds:3,tokens_in:10,tokens_out:2,usd:.001}};studio.renderAssignmentUsage();
 assert.match(element('#assignment-usage-detail').textContent,/12 tokens/);
 assert.match(studio.usageText({seconds:1}),/USD unavailable/);
 console.log('Studio UI: live seconds, completion totals, button state and reload passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
