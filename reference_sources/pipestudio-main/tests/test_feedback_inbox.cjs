// Exercise rendered inbox states without altering stored feedback or calling AI.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('vectorascore/static/studio.js','utf8');
const render=source.slice(source.indexOf('  function renderFeedbackResults(w){'),source.indexOf('  async function startComparison('));
const dummy={addEventListener(){},querySelectorAll(){return[];}};
const w={innerHTML:'',querySelectorAll(){return[];}};
const context={document:{activeElement:null},page:'learning',api:()=>new Promise(()=>{}),render(){},encodeURIComponent,Promise,Map,feedbackDrawing:'',feedbackPoll:null,selectedFeedback:{review:null,redeploy:null},expandedChat:new Set(),chatDrafts:new Map(),
 overview:{feedback:[],tasks:[],conversations:{},applications:[],improvements:{batches:[],candidates:[],implementation_requests:[]}},
 $:()=>dummy,esc:x=>String(x??'').replaceAll('<','&lt;'),heading:(tag,title,copy,actions)=>`<h1>${title}</h1>${actions}`,feedbackInbox:r=>r.inbox,styleName:x=>x,scopeName:()=> 'Shared feedback',w};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  function feedbackAddedAt('),source.indexOf('  function renderFeedbackResults(')),context);vm.runInContext(render,context);
const draw=()=>{vm.runInContext('renderFeedbackResults(w)',context);return w.innerHTML;};
assert.match(draw(),/All caught up/);assert.doesNotMatch(draw(),/id="feedback-drawing"/);assert.doesNotMatch(draw(),/id="open-redeploy"/);
context.overview.feedback=[1,2,3].map(n=>({id:'f'+n,inbox:'review',sheet:'one',type:'false_pipe',status:'open',note:'Comment '+n,ts:'2026-09-0'+n}));
let html=draw();assert.equal((html.match(/data-select-feedback=/g)||[]).length,3);assert.equal((html.match(/class="feedback-conversation"/g)||[]).length,1);assert.match(html,/id="conversation-f3"/);
context.overview.improvements.candidates=[{id:'candidate',evaluation:'evaluation',report:{cases:[]},feedback_ids:['f2'],workflow_status:'review_results'}];
html=draw();assert.equal((html.match(/Comparison ready/g)||[]).length,1);assert.match(html,/data-list-compare="evaluation" data-feedback-id="f2"/);
assert.equal((html.match(/Compare before & after →/g)||[]).length,1);
context.selectedFeedback.review='f1';assert.match(draw(),/id="conversation-f1"/);
context.overview.feedback[0].inbox='archive';assert.doesNotMatch(draw(),/id="conversation-f1"/);
context.feedbackDrawing='other';assert.match(draw(),/id="feedback-drawing"/);assert.match(draw(),/No open feedback for this drawing/);
context.page='redeploy';context.feedbackDrawing='';assert.match(draw(),/No updates waiting/);
console.log('Feedback inbox: empty, selected, archived and filtered states passed');
vm.runInContext(source.slice(source.indexOf('  function analysisUsageCard('),source.indexOf('  function renderFeedbackResults(')),context);
context.task={status:'done',seconds:67,usage:{tokens_total:1200,usd:.0123,usage_complete:true,calls:3}};
const receipt=vm.runInContext('analysisUsageCard(task)',context);
assert.match(receipt,/1 min 7 s/);assert.match(receipt,/1,200/);assert.match(receipt,/\$0\.0123/);
context.task={status:'done',seconds:3};assert.match(vm.runInContext('analysisUsageCard(task)',context),/Usage was not recorded/);
console.log('Analysis receipt: duration, tokens, USD and older runs passed');

context.page='learning';context.feedbackDrawing='';context.selectedFeedback.review='f2';
context.overview.conversations.f2={status:'Your answer needed',clarification:{id:'q1',status:'awaiting_answer'},messages:[{role:'app',kind:'clarification',question_id:'q1',text:'Should these remain separate? Separate pipes stay individual.',choices:['Keep separate','Join together']}]};
const questionView=draw();
assert.match(questionView,/Answer & analyse/);assert.match(questionView,/data-question="q1"/);
assert.match(questionView,/Separate pipes stay individual/);assert.match(questionView,/data-answer-choice="f2"/);
assert.doesNotMatch(questionView,/data-retry-feedback="f2"/);
console.log('Clarification: supportive explanation, answer options and analysis action passed');
context.page='redeploy';context.overview.feedback[1].inbox='redeploy';context.selectedFeedback.redeploy='f2';
context.overview.conversations.f2.clarification.origin='app_updates';context.overview.conversations.f2.messages[0].origin='app_updates';
const rebuildQuestion=draw();
assert.match(rebuildQuestion,/AI rebuilding the app/);assert.match(rebuildQuestion,/Send answer/);
assert.doesNotMatch(rebuildQuestion,/Answer & analyse/);assert.doesNotMatch(rebuildQuestion,/data-retry-feedback="f2"/);
assert.match(rebuildQuestion,/No AI call or automatic rebuild is started/);
console.log('App updates: developer questions stay in conversation without automatic synthesis');

context.created='2026-09-09T22:39:49.454358+00:00';
const added=vm.runInContext('feedbackAddedAt(created)',context);
assert.match(added,/10 Sept 2026/);assert.match(added,/00:39/);
assert.match(added,/datetime="2026-09-09T22:39:49.454Z"/);
assert.match(added,/Europe\/Warsaw/);
assert.equal(vm.runInContext('feedbackAddedAt(null)',context),'Added: date unavailable');
assert.equal(vm.runInContext('feedbackAddedAt("invalid")',context),'Added: date unavailable');
assert.match(draw(),/<time datetime=/);
console.log('Feedback timestamps: Warsaw date rollover and unavailable dates passed');

// DOM replacement must retain both scroll containers and the clicked button's focus.
context.page='learning';context.feedbackDrawing='';context.overview.feedback[1].inbox='review';
let list={scrollTop:1800,dataset:{inboxScope:JSON.stringify(['review',''])}};
let focusOptions;
const oldButton={dataset:{selectFeedback:'f2'},closest:selector=>selector==='[data-chat]'?null:oldButton};
const newButton={dataset:{selectFeedback:'f2'},focus:options=>{focusOptions=options;}};
context.document.activeElement=oldButton;context.document.scrollingElement={scrollTop:75};
w.scrollTop=320;w.querySelector=selector=>selector==='.feedback-list'?list:null;
w.querySelectorAll=selector=>selector==='[data-select-feedback], [data-open-feedback]'?[newButton]:[];
let markup='';
Object.defineProperty(w,'innerHTML',{get:()=>markup,set:value=>{markup=value;list={scrollTop:0,dataset:{inboxScope:JSON.stringify(['review',''])}};w.scrollTop=0;context.document.scrollingElement.scrollTop=0;}});
draw();
assert.equal(list.scrollTop,1800);assert.equal(w.scrollTop,320);assert.equal(context.document.scrollingElement.scrollTop,75);
assert.equal(focusOptions.preventScroll,true);
// The same behaviour holds on a background refresh, but a different filter starts at the top.
draw();assert.equal(list.scrollTop,1800);
context.feedbackDrawing='one';draw();assert.equal(list.scrollTop,0);
console.log('Inbox navigation: list/workbench/page position and focus survive selection and refresh; changed filters reset the list.');
