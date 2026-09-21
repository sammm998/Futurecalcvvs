const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vectorascore/static/studio.js','utf8');
const elements=new Map();const $=id=>{if(!elements.has(id))elements.set(id,{hidden:true,disabled:false,dataset:{},setAttribute(){},close(){this.closed=true;}});return elements.get(id);};
let timers=[],reloadResolve;
const context={$,styleName:id=>id,Date,Set,JSON,Error,localStorage:{setItem(){},removeItem(){}},setInterval:()=>1,clearInterval(){},setTimeout:fn=>timers.push(fn),lastJob:null,notify(){},setBusy(){},busyMessage(){},refresh:async()=>{},queue:async()=>{},window:{PipeReview:{refreshStatus(){},state:()=>({sheet:'drawing'}),reload:()=>new Promise(resolve=>reloadResolve=resolve)}},api:async path=>path==='replay'?{id:'test',kind:'replay'}:{kind:'replay',status:'done'}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  let stylePreviewBusy='),source.indexOf('  function switchPage(')),context);
(async()=>{
 await vm.runInContext("job('replay',{sheet:'drawing',style_id:'chosen',binding:'preview'})",context);
 assert.equal($('#style-preview-loading').hidden,false);assert.equal($('#apply-drawing-style').disabled,true);assert.match($('#style-preview-title').textContent,/chosen/);
 await assert.rejects(vm.runInContext("job('replay',{sheet:'drawing',binding:'preview'})",context),/wait/);
 const completion=timers.shift()();await new Promise(resolve=>setImmediate(resolve));
 assert.equal($('#style-preview-loading').hidden,false,'loading remains until drawing reload finishes');reloadResolve();await completion;
 assert.equal($('#style-preview-loading').hidden,true);assert.equal($('#review-workspace').inert,false);
 context.api=async()=>{throw new Error('offline');};
 await assert.rejects(vm.runInContext("job('replay',{sheet:'drawing',binding:'preview'})",context),/offline/);
 assert.equal($('#style-preview-loading').hidden,true);assert.equal($('#apply-drawing-style').disabled,false);
 console.log('Style preview: immediate loading, duplicate prevention, reload completion and request failure passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
