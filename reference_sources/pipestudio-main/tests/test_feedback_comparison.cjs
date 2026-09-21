const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vectorascore/static/studio.js','utf8');
const elements=new Map();
const buttons=[{dataset:{compareAnswer:'true'}},{dataset:{compareAnswer:'false'}}];
const element=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',classList:{toggle(){}},remove(){},prepend(){},querySelectorAll(selector){return selector==='[data-compare-answer]'||selector==='button'?buttons:[];}});return elements.get(id);};
const row={id:'chosen',snapshot:'original',stretch_id:7,tab:'pipes',note:'Look here'};
const original={stretches:[{id:7,points:[[1,2],[3,4]]}]};
const revised={stretches:[{id:7,points:[[100,200],[300,400]]}]};
const cases=[{feedback_id:'other',snapshot:'original',outcome:'fail'}, {feedback_id:'chosen',snapshot:'original',outcome:'pass',before:true}];
const focused=[],shown=[],reads=[],jobs=[],pages=[];
const context={setBusy(){},busyMessage(){},overview:{feedback:[row]},selectedFeedback:{review:'chosen'},comparisonSession:null,
 api:async path=>{reads.push(path);return path.startsWith('evaluation?')?{id:'test',cases}:path.startsWith('snapshot?')?original:revised;},
 notify(){},switchPage:p=>pages.push(p),name:()=> 'Expert',askName(){},act:fn=>fn(),refresh:async()=>{},render(){},job:async(path,body)=>jobs.push({path,body}),esc:x=>String(x??''),feedbackTarget:()=> 'Pipe #7',
 document:{querySelectorAll:()=>[],body:{classList:{add(){}}},createElement:()=>element('banner')},
 $:element,window:{PipeReview:{showResult:r=>shown.push(r),focusFeedback:(r,reference)=>focused.push({r,reference})}}};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('  async function startComparison('),source.indexOf('  function render() {')),context);
(async()=>{
 await vm.runInContext('startComparison("test")',context);
 assert.equal(context.comparisonSession.cases[context.comparisonSession.index].feedback_id,'chosen');
 assert.equal(focused[0].r,row);assert.equal(focused[0].reference,original);assert.equal(shown[0],revised);
 context.comparisonSession.side='before';await vm.runInContext('renderComparison()',context);
 assert.equal(focused[1].reference,original);
 assert.equal(reads.filter(p=>p==='snapshot?id=original').length,1);
 assert.match(element('banner').innerHTML,/Pipe #7/);
 assert.match(element('banner').innerHTML,/Switch to After/);
 context.comparisonSession.side='after';await vm.runInContext('renderComparison()',context);
 assert.match(element('banner').innerHTML,/id="compare-next" hidden/);
 await buttons[0].onclick();
 assert.equal(jobs[0].path,'accept-comparison');assert.equal(jobs[0].body.feedback_id,'chosen');
 assert.equal(context.comparisonSession,null);assert.equal(pages.at(-1),'redeploy');
 await vm.runInContext('startComparison("test")',context);
 await buttons[1].onclick();
 assert.ok(reads.includes('reject-comparison'));assert.equal(jobs.length,1);
 assert.equal(context.comparisonSession,null);
 console.log('Yes queues deployment and No saves a diagnosis handoff immediately, without Next/Save.');
 console.log('Comparison starts at selected feedback and highlights original geometry on both sides, even when IDs are reused.');
})().catch(e=>{console.error(e);process.exitCode=1;});
