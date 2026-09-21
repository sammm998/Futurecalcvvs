/* FutureCalc Pipe Studio — expert workflow around the shared vector engine. */
(() => {
  const $ = s => document.querySelector(s);
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let overview=null, page='review', selectedStyle='style-1', reviewStyle='auto', lastJob=null, feedbackResolve=null, feedbackView='all', feedbackSheet='', feedbackMethod='';
  // Stable style numbers match the source PDF folders (independent of display names).
  const styleOrder=['style-1','sweco-pdfplot-text','eon-hairline','axis-bluebeam','bd-ghostscript','badskon-a3-booklet','blackhornet-2xa0','style4-heavy-dashed','style5-sewer-plan','style9-thin-dashdot','style6-single-width'];
  const styleNumber=id=>{const i=styleOrder.indexOf(id);return i<0?(overview?.styles.find(s=>s.draft.id===id)?.display_number??null):i+1;};
  let improvementStyle='', comparisonReturn=null, feedbackDrawing='', advancedLearning=false, comparisonSession=null;
  let feedbackPoll=null;
  const chatDrafts=new Map();
  const selectedFeedback={review:null,redeploy:null};
  const expandedChat=new Set();
  let uploadedDrawing=null;
  let styleDirty=false;
  const leaveStyle=()=>!styleDirty||window.confirm('Discard unsaved style changes?');
  window.addEventListener('beforeunload',e=>{if(styleDirty){e.preventDefault();e.returnValue='';}});
  const {methodOf, resultName, scopeOf, scopeName} = window.AssignmentContext;
  const methodBadge=r=>`<span class="badge method-${scopeOf(r)}">${esc(scopeName(r))}</span>`;
  const name = () => { try { return localStorage.getItem('author') || ''; } catch { return ''; } };
  const notify = (message, error=false) => { const n=$('#notification'); n.hidden=false; n.textContent=message; n.classList.toggle('error',error); };
  async function api(path, body) {
    const controller=new AbortController(), timer=path==='overview'?setTimeout(()=>controller.abort(),15000):null;
    let r;try{r=await fetch('/api/studio/'+path,{...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),signal:controller.signal});}catch(error){if(error.name==='AbortError')throw new Error('Loading feedback took too long. Please retry.');throw error;}finally{if(timer)clearTimeout(timer);}
    const j=await r.json(); if(!r.ok) throw new Error(j.error || 'Request failed'); return j;
  }
  // Every action that outlasts a click says so: a bar under the header naming what
  // runs, and the button that started it held disabled until it finishes.
  let busyCount=0, busyTimer=null, busyLabel='';
  function paintBusy(){ const box=$('#busy'); if(!box)return; $('#busy-label').textContent=busyLabel||'Working…'; box.hidden=!busyCount; }
  function setBusy(on,label){
    if(on){ busyCount++; if(label)busyLabel=label;
      if(!busyTimer)busyTimer=setTimeout(()=>{busyTimer=null;paintBusy();},150);   // a fast action must not flash
      if(!$('#busy')?.hidden)paintBusy(); return; }
    busyCount=Math.max(0,busyCount-1);
    if(!busyCount){ if(busyTimer){clearTimeout(busyTimer);busyTimer=null;} busyLabel=''; }
    paintBusy();
  }
  function busyMessage(text){ if(busyCount&&text){busyLabel=text;if(!$('#busy')?.hidden)paintBusy();} }
  async function act(fn,label) {
    if(label===false) { try { return await fn(); } catch(e) { notify(e.message,true); } return; }   // background refresh: stay quiet
    const button=document.activeElement?.closest?.('button');
    const held=button&&!button.disabled?button:null;
    if(held){held.disabled=true;held.dataset.busy='act';}
    setBusy(true,label||held?.textContent?.trim().replace(/\s+/g,' ').slice(0,60)||'Working…');
    try { return await fn(); }
    catch(e) { notify(e.message,true); }
    // a button handed on to a running job (data-busy="job") stays disabled until it ends
    finally { setBusy(false); if(held?.isConnected&&held.dataset.busy==='act'){delete held.dataset.busy;held.disabled=false;} }
  }
  // Pipe Studio's reply opens the comment's frozen drawing, so it is read for the
  // comment on screen, not for the whole inbox.
  const replyCache=new Map(), replyPending=new Set();
  function replyFor(id,status){
    const held=replyCache.get(id);
    if(held&&held.status===status)return held.reply;
    if(!replyPending.has(id)){
      replyPending.add(id);
      api('reply?id='+encodeURIComponent(id))
        .then(r=>{replyCache.set(id,{status:r.status,reply:r.reply});if(['learning','redeploy'].includes(page))render();})
        .catch(()=>replyCache.set(id,{status,reply:null}))
        .finally(()=>replyPending.delete(id));
    }
    return undefined;
  }
  async function refresh() { if(page==='styles'&&styleDirty)return overview; try{overview=await api('overview');}catch(error){if(page!=='review'&&!overview){$('#workbench').innerHTML='<section class="panel"><h2>Could not load feedback</h2><p>Your saved feedback is safe.</p><button class="btn primary" id="retry-feedback-load">Try again</button></section>';$('#retry-feedback-load').onclick=()=>act(refresh);}throw error;} overview.styles.sort((a,b)=>(styleNumber(a.draft.id)??Infinity)-(styleNumber(b.draft.id)??Infinity)||a.draft.name.localeCompare(b.draft.name)); $('#total-feedback').textContent=overview.feedback.filter(r=>feedbackInbox(r)==='review').length;$('#redeploy-count').textContent=overview.feedback.filter(r=>feedbackInbox(r)==='redeploy').length; document.querySelectorAll('#total-feedback,#redeploy-count').forEach(b=>b.hidden=b.textContent==='0'); renderStylePicker(); if(page!=='review') render(); updateFeedbackButton(); return overview; }
  function usageText(m){
    if(!m)return 'Usage unavailable';
    const tokens=typeof m.tokens_in==='number'&&typeof m.tokens_out==='number'?`${(m.tokens_in+m.tokens_out).toLocaleString('en-GB')} tokens (${m.tokens_in.toLocaleString('en-GB')} in / ${m.tokens_out.toLocaleString('en-GB')} out; ${(m.cached_tokens||0).toLocaleString('en-GB')} cached)`:'tokens unavailable';
    const cost=typeof m.usd==='number'?`≈ $${m.usd.toFixed(4)} USD`:'USD unavailable';
    return `${m.seconds??'?'} s · ${tokens} · ${cost}${m.usage_complete===false?' · incomplete accounting':''}`;
  }
  const MODES={astra:{title:'LLM',method:'llm'},flow:{title:'Dimension',method:'dimension'}};
  let selectedAssignmentMode='flow';
  const mode=()=>selectedAssignmentMode;
  const methodChecks=new Map();
  const missingLlmResults=new Map();
  let selectingAssignment=null;
  async function ensureDimension(retry=false){
    const current=window.PipeReview?.state();
    if(!current?.R||current.readonly||current.refreshingVectors||current.tab!=='bindings'||selectingAssignment)return;
    const live=assignmentJobs.get(current.sheet);
    if(live&&!live.done)return;
    const binding=mode(), key=`${binding}:${current.R.metadata?.run_id||'legacy'}`;
    if(!retry&&methodChecks.get(current.sheet)===key)return;
    methodChecks.set(current.sheet,key);
    selectingAssignment=current.sheet;
    if(binding==='astra')missingLlmResults.delete(current.sheet);
    renderMethodContext();
    // an automatic check or refresh keeps the style the drawing was analysed with:
    // only the reviewer changes a style, through Style… or Re-analyze
    const style=current.R.metadata?.style_id||reviewStyle;
    try{
      const result=await api('select-assignment',{sheet:current.sheet,style_id:style,binding});
      if(window.PipeReview?.state()?.sheet!==current.sheet)return;
      if(result.available&&result.run_id!==current.R.metadata?.run_id)await window.PipeReview.reload(true);
      const updated=window.PipeReview.state();
      if(binding==='astra'&&!result.available)missingLlmResults.set(current.sheet,updated.R?.metadata?.run_id);
      methodChecks.set(current.sheet,`${binding}:${updated.R?.metadata?.run_id||'legacy'}`);
      selectingAssignment=null;
      if(binding==='flow'&&!result.fresh&&current.role==='admin'){
        await job('replay',{sheet:current.sheet,style_id:style,draft:false,binding:'flow'});
      }else{
        renderAssignmentUsage();window.PipeReview.refreshStatus();
      }
    }catch(error){notify(error.message,true);}
    finally{selectingAssignment=null;renderMethodContext();}
  }
  function selectAssignmentMode(value){
    selectedAssignmentMode=value;
    ensureDimension(true);
    renderAssignmentUsage();
  }
  const styleEntry=id=>overview?.styles.find(s=>s.draft.id===id||s.draft.library_id===id||s.draft.merged_members?.includes(id));
  const styleName=id=>{const entry=styleEntry(id);if(!entry)return id;const n=styleNumber(entry.draft.id);return `${n===null?'':String(n).padStart(2,'0')+' - '}${entry.draft.name}`;};
  function renderStyleBadge(rv){
    // what the engine detected (the drawing-style library, vectorascore/style.py),
    // what the analysis actually used, and a picker to re-analyze with another style
    const meta=rv.metadata||{}, m=meta.style_match||{}, lib=m.library||{}, near=lib.nearest||{};
    const used=meta.style_id||'style-1', detected=m.style_id||null;
    const badge=$('#style-badge');
    let text, title;
    if(m.selection==='manual'||!m.selection){ text=`${styleName(used)}${meta.profile_state==='draft'?' · Draft':''}`; title=m.selection?'Style chosen by the reviewer':'Style of this analysis'; }
    else if(m.selection==='auto'){ text=`Detected: ${styleName(used)}`; title=`Detected automatically (${m.method}, library distance ${near.distance??'?'})`; }
    else { text=`Unknown style · analysed as ${styleName(used)}`; title=`No known style within reach (nearest ${near.id||'none'} at ${near.distance??'?'}); result uncertain`; }
    if(m.selection==='manual'&&detected&&detected!==used){ text+=` · detected ${styleName(detected)}`; title+=`. The drawing matches ${styleName(detected)}`; }
    badge.textContent=text; badge.title=`${title} · style version ${meta.style_version||'unknown'} · ${resultName(meta)}`;
    badge.dataset.state=m.selection==='fallback'?'unknown':(m.selection==='manual'&&detected&&detected!==used?'mismatch':'ok');
    renderStylePicker(detected, m.selection==='manual'?used:'auto');
  }
  // the style choice on the review page: Auto (detect from the drawing) or one
  // named style. It drives Upload, Re-analyze, the saved-result checks and the
  // assignment selection; the workbench pages keep their own concrete style
  // the drawing bar is static markup on the review page (render() only draws the
  // workbench pages), so its handlers are bound once, when the overview arrives
  function bindDrawingBar(){
    if($('#style-choice')&&!$('#style-choice').dataset.bound){$('#style-choice').dataset.bound='1';$('#style-choice').addEventListener('change',e=>{reviewStyle=e.target.value;});}
    if($('#reanalyze-style')&&!$('#reanalyze-style').dataset.bound){$('#reanalyze-style').dataset.bound='1';$('#reanalyze-style').onclick=()=>act(async()=>{const st=window.PipeReview?.state();if(!st?.sheet)throw new Error('Select a drawing first.');reviewStyle=$('#style-choice').value;await job('replay',{sheet:st.sheet,style_id:reviewStyle,draft:false,binding:'preview'});notify(reviewStyle==='auto'?'Re-analyzing; the style is detected from the drawing.':`Re-analyzing with ${styleName(reviewStyle)}.`);});}
  }
  function renderStylePicker(detected=null, value=null){
    bindDrawingBar();
    const picker=$('#style-picker'), sel=$('#style-choice');
    if(!picker||!sel||!overview)return;
    picker.hidden=true;
    sel.innerHTML=`<option value="auto">Auto · detect from the drawing</option>`+overview.styles.map(s=>`<option value="${esc(s.draft.id)}">${esc(styleName(s.draft.id))}${s.draft.id===detected?' (detected)':''}</option>`).join('');
    if(value!==null)reviewStyle=value;
    reviewStyle=styleEntry(reviewStyle)?.draft.id||'auto';
    sel.value=reviewStyle;
  }
  async function openDrawingStyle(){
    const rv=window.PipeReview?.state()?.R;if(!rv){notify('Wait for the drawing analysis to finish.',true);return;}
    const m=rv.metadata?.style_match||{},near=m.style_id||m.candidates?.[0]?.style_id||m.library?.nearest?.id,used=rv.metadata?.style_id||'style-1';
    $('#onboarding-style').innerHTML=overview.styles.map(s=>`<option value="${esc(s.draft.id)}" ${s.draft.id===used?'selected':''}>${esc(styleName(s.draft.id))}</option>`).join('');
    $('#drawing-style-explanation').textContent=m.selection==='fallback'?`No confident match. Closest style: ${near?styleName(near):'not found'}. Currently using ${styleName(used)} as a starting point. Confirm a style or create a new one.`:`This drawing is using ${styleName(used)}.${near?' Closest detected style: '+styleName(near)+'.':''} Check the pipe annotations, then keep this style or choose another.`;
    $('#drawing-style-dialog').showModal();
    const sheet=window.PipeReview.state().sheet;
    if(!$('#drawing-style-name').value){try{const suggested=await api('suggest-style-name?sheet='+encodeURIComponent(sheet));if(window.PipeReview.state().sheet===sheet&&!$('#drawing-style-name').value)$('#drawing-style-name').value=suggested.name;}catch{ /* An optional suggestion must not block style creation. */ }}
  }
  $('#drawing-style').onclick=()=>act(openDrawingStyle);
  $('#close-drawing-style').onclick=()=>$('#drawing-style-dialog').close();
  $('#apply-drawing-style').onclick=()=>act(async()=>{const sheet=window.PipeReview.state().sheet;reviewStyle=$('#onboarding-style').value;await job('replay',{sheet,style_id:reviewStyle,draft:false,binding:'preview'});$('#drawing-style-dialog').close();});
  async function createDrawingStyle(body, progress){
    const task=await api('style-from-drawing',body);
    while(true){
      const state=await api('task?id='+encodeURIComponent(task.id));
      if(state.status==='error')throw new Error(state.error||'Style inspection failed.');
      if(state.status==='done')return state.result;
      progress(state.progress||'Creating style…');
      await new Promise(resolve=>setTimeout(resolve,1500));
    }
  }
  $('#create-drawing-style').onclick=()=>act(async()=>{
    const button=$('#create-drawing-style'),status=$('#drawing-style-progress');button.disabled=true;
    status.textContent='Classifying PDF vectors…';
    try{
      const sheet=window.PipeReview.state().sheet;
      const created=await createDrawingStyle({sheet,name:$('#drawing-style-name').value,base_style:$('#onboarding-style').value,author:name()},message=>status.textContent=message);
      reviewStyle=created.id;await refresh();
      await job('replay',{sheet,style_id:created.id,draft:false,binding:'preview'});
      $('#drawing-style-dialog').close();status.textContent='';$('#drawing-style-name').value='';
    }catch(error){status.textContent=error.message;throw error;}finally{button.disabled=false;}
  });

  function renderDrawingLibrary(){const query=$('#drawing-search').value.toLowerCase();$('#drawing-library').innerHTML=[...$('#sheet').options].filter(o=>o.textContent.toLowerCase().includes(query)).map(o=>`<button class="drawing-card" data-drawing="${esc(o.value)}"><b>${esc(o.textContent)}</b><span>Open & give feedback →</span></button>`).join('')||'<p>No drawings found. Use Add PDF to upload a drawing.</p>';$('#drawing-library').querySelectorAll('[data-drawing]').forEach(b=>b.onclick=()=>act(async()=>{$('#drawings-dialog').close();await window.PipeReview.openDrawing(b.dataset.drawing);}));}
  $('#open-drawings').onclick=()=>{renderDrawingLibrary();$('#drawings-dialog').showModal();};
  $('#library-upload').onclick=()=>{$('#drawings-dialog').close();$('#file').click();};
  $('#close-drawings').onclick=()=>$('#drawings-dialog').close();
  $('#drawing-search').oninput=renderDrawingLibrary;
  function renderMethodContext(){
    const current=window.PipeReview?.state();
    const meta=current?.R ? (current.R.metadata||{}) : null;
    const c=window.AssignmentContext.context(meta,current?.tab,current?.readonly);
    const live=current&&!current.readonly?assignmentJobs.get(current.sheet):null;
    const running=live&&!live.done;
    const available=!!current?.R&&!current.readonly&&!running&&selectingAssignment!==current.sheet;
    document.querySelectorAll('[data-generate]').forEach(button=>{
      const restricted=current?.role==='review'&&button.dataset.generate==='flow';
      button.disabled=!available||restricted;
      button.title=restricted?'Dimension generation requires an administrator':button.dataset.generate==='astra'?'Generate assignments with Astra (model usage applies)':'Generate assignments from dimension and flow rules';
    });
    const displayedMode=current?.readonly?(c.actual==='llm'?'astra':'flow'):mode();
    document.querySelectorAll('[data-assignment-mode]').forEach(button=>{
      button.setAttribute('aria-checked',String(button.dataset.assignmentMode===displayedMode));
      button.tabIndex=button.dataset.assignmentMode===displayedMode?0:-1;
      button.disabled=!available;
      button.title='Show the saved '+MODES[button.dataset.assignmentMode].title+' result';
    });
    $('#run-astra').hidden=displayedMode!=='astra';
    $('#run-astra').textContent=running&&live.binding==='astra'?'Asking LLM…':'Ask LLM';
    $('#assignment-actions').hidden=current?.tab!=='bindings';
    $('#assignment-summary').hidden=current?.tab!=='bindings';
    const freshness=$('#assignment-status').dataset;
    const stale=freshness.runId===meta?.run_id&&['stale','legacy','preview','missing'].includes(freshness.state);
    const missingLlm=current?.tab==='bindings'&&displayedMode==='astra'&&c.actual!=='llm'&&!current?.readonly;
    $('#review-workspace').classList.toggle('missing-llm-preview',missingLlm);
    const confirmedMissing=missingLlm&&!!current?.R&&selectingAssignment!==current.sheet&&missingLlmResults.has(current.sheet)&&missingLlmResults.get(current.sheet)===meta?.run_id;
    $('#llm-preview-warning').hidden=!(confirmedMissing||(current?.R&&!current.readonly&&current.tab==='bindings'&&displayedMode==='astra'&&!running&&selectingAssignment!==current.sheet&&c.actual==='llm'&&stale));
    $('#llm-preview-warning-title').textContent=missingLlm&&running?'Generating LLM preview…':c.actual==='llm'?'LLM preview is out of date':'No LLM preview available';
    $('#llm-preview-warning p').hidden=missingLlm&&!!running;
    $('#llm-preview-source').textContent=missingLlm?'The preview will appear when the LLM analysis is complete.':'The drawing below shows the previous saved LLM result.';
    $('#assignment-job-state').textContent=current?.readonly?' · Saved analysis, read only'
      :selectingAssignment===current?.sheet?' · Loading saved result…':running?` · Generating ${MODES[live.binding||mode()].title}… ${live.seconds||0}s`
      :live?.done?` · ${live.message}`:!current?.R?' · Select a processed drawing':mode()==='flow'&&c.actual!=='dimension'?' · Dimension result unavailable.':'';
    const host=$('#feedback-context');host.dataset.scope=c.scope;
    const assignmentFeedback=current?.tab==='bindings';
    const llmFeedback=assignmentFeedback&&displayedMode==='astra';
    host.dataset.tone=llmFeedback?'llm':'shared';
    const feedbackTitle=assignmentFeedback?(llmFeedback?'LLM result feedback':'Dimension result feedback'):c.title;
    const assignmentPurpose=llmFeedback
      ? 'Use this feedback primarily to improve the LLM assignment prompt.'
      : 'Use this feedback primarily to improve the Dimension assignment algorithm.';
    const feedbackDetail=current?.readonly?'Saved analysis · read only':assignmentFeedback
      ? (llmFeedback&&c.actual!=='llm'?'Click Ask LLM first to review an LLM result. ':'')
        +assignmentPurpose+' It can also guide improvements to pipes, joining points, leading lines, and labels & OCR.'
      :'This feedback is shared by Dimension and LLM.';
    host.innerHTML=`<strong>${esc(feedbackTitle)}</strong><p>${esc(feedbackDetail)}</p>`;
  }
  const assignmentJobs=new Map();
  function renderAssignmentUsage(){
    renderMethodContext();
    const current=window.PipeReview?.state();
    const live=current&&!current.readonly?assignmentJobs.get(current.sheet):null;
    const saved=current?.R?.llm;
    const m=live?.usage||saved;
    const flow=current?.R?.algorithm==='flow_assign'&&!['pipe_final','full'].includes(m?.mode);
    $('#assignment-run-state').textContent=live?.message||(['pipe_final','full'].includes(m?.mode)?(m.errors?.length?'Astra completed with request errors':'Assignment completed · llm'):flow?'Assignment completed · dimension':'Assignment has not run');
    $('#assignment-usage-detail').textContent=live&&!live.done
      ? (live.binding==='astra'?`Elapsed ${live.seconds} s · Tokens and USD will be available when the run finishes.`:`Elapsed ${live.seconds} s.`)
      : ['pipe_final','full'].includes(m?.mode)||live?.usage
        ? `Astra time · ${usageText(m)}${m.errors?.length?' · '+m.errors.length+' request errors':''}`
        : flow ? `${(current.R.runs||[]).length} runs · ${(current.R.pipes||[]).length} pipes between joining points · ${current.R.bindings.length} stretches assigned by the flow rules`
        : mode()==='astra' ? 'Click Ask LLM to see time, tokens and estimated USD here.'
        : 'Dimension assignments are generated automatically when needed.';
  }
  let stylePreviewBusy=false;
  function stylePreviewLoading(body, message=null){
    const panel=$('#style-preview-loading');
    stylePreviewBusy=message!==null;
    panel.hidden=!stylePreviewBusy;
    $('#review-workspace').setAttribute('aria-busy',String(stylePreviewBusy));
    $('#review-workspace').inert=stylePreviewBusy;
    for(const id of ['drawing-style','apply-drawing-style','create-drawing-style','reanalyze-style']){
      const button=$('#'+id);if(button)button.disabled=stylePreviewBusy;
    }
    if(stylePreviewBusy){
      $('#drawing-style-dialog').close();
      $('#style-preview-title').textContent=body.style_id==='auto'?'Detecting drawing style…':'Recognising pipes with '+styleName(body.style_id)+'…';
      $('#style-preview-progress').textContent=message;
    }
  }
  const watches=new Set();
  function watchJob(j,body){
    if(watches.has(j.id))return;watches.add(j.id);
    const assign=['astra','flow'].includes(body.binding);
    const stylePreview=j.kind==='replay'&&body.binding==='preview';
    let started=Date.parse(j.created_at)||Date.now(),message=body.binding==='astra'?'Astra assignment':body.binding==='flow'?'Flow-direction assignment':'Processing';
    const button=assign?$(body.binding==='flow'?'#run-dimension':'#run-astra'):$('#rerun-vectors');
    if(j.kind==='replay'){button.disabled=true;button.dataset.busy='job';}
    const isAstra=assign;
    setBusy(true,message);
    const tick=()=>{
      const seconds=Math.floor((Date.now()-started)/1000);
      busyMessage(`${message} · ${seconds} s`);
      if(isAstra){assignmentJobs.set(body.sheet,{message,seconds,binding:body.binding});renderAssignmentUsage();}
      else $('#progress').textContent=`${message} · ${seconds} s`;
      if(stylePreview)stylePreviewLoading(body,`${message} · ${seconds} s`);
    };tick();
    const clock=setInterval(tick,1000);
    const finish=()=>{clearInterval(clock);watches.delete(j.id);button.disabled=false;delete button.dataset.busy;setBusy(false);try{localStorage.removeItem('studio-active-job');}catch{}};
    const poll=async()=>{
      try{
        const state=await api('task?id='+encodeURIComponent(j.id));
        started=Date.parse(state.started_at||state.created_at)||started;
        if(state.status==='running'||state.status==='queued'){message=state.progress||'Queued';tick();setTimeout(poll,1500);return;}
        finish();
        if(state.status==='error'){
          if(stylePreview)stylePreviewLoading(body);
          window.PipeReview?.refreshStatus?.();
          if(isAstra){assignmentJobs.set(body.sheet,{message:'Assignment failed',done:true,usage:{seconds:state.seconds}});renderAssignmentUsage();}
          else $('#progress').textContent=`Failed · ${state.seconds??0} s`;
          notify(state.error,true);await refresh();return;
        }
        const summary=body.binding==='astra'&&state.result?.usage?usageText({...state.result.usage,seconds:state.seconds??state.result.usage.seconds}):`${state.seconds??0} s`;
        if(isAstra){
          assignmentJobs.set(body.sheet,{message:state.result?.model_errors?.length?'Astra completed with request errors':body.binding==='flow'?'Flow-direction assignment completed':'Astra completed',done:true,usage:state.result?.usage||{}});
          renderAssignmentUsage();
        }else $('#progress').textContent='Completed · '+summary;
        await refresh();
        if(state.kind==='accept-comparison'){
          notify(state.result.status+(state.result.reason?' · '+state.result.reason:''));
          if(page==='redeploy'&&state.result.inbox==='archive'){
            selectedStyle=overview.feedback.find(r=>r.id===state.result.id)?.style_id||selectedStyle;
            feedbackSheet='';feedbackMethod='';switchPage('feedback');
          }
        }
        if(state.kind==='replay'&&!window.PipeReview?.state().readonly&&window.PipeReview?.state().sheet===body.sheet){await window.PipeReview.reload(true);await queue();}
        if(stylePreview)stylePreviewLoading(body);
        if(isAstra){assignmentJobs.delete(body.sheet);renderAssignmentUsage();}
      }catch(e){finish();if(stylePreview)stylePreviewLoading(body);if(isAstra){assignmentJobs.set(body.sheet,{message:'Connection lost — reload to reconnect',done:true,usage:{}});renderAssignmentUsage();}notify(e.message+' · reload to reconnect to the job',true);}
    };setTimeout(poll,500);
  }
  async function job(path,body){
    const stylePreview=path==='replay'&&body.binding==='preview';
    if(stylePreview){if(stylePreviewBusy)throw new Error('Please wait for the current style preview to finish.');stylePreviewLoading(body,'Starting pipe recognition…');}
    const assign=['astra','flow'].includes(body.binding);
    const button=assign?$(body.binding==='flow'?'#run-dimension':'#run-astra'):$('#rerun-vectors');if(path==='replay'){button.disabled=true;button.dataset.busy='job';}
    if(assign){
      window.PipeReview?.setTab('bindings');
      $('#progress').textContent='';$('#notification').hidden=true;
      assignmentJobs.set(body.sheet,{message:body.binding==='astra'?'Starting Astra':'Starting assignment',seconds:0,binding:body.binding});renderAssignmentUsage();
    }else $('#progress').textContent='Starting · 0 s';
    let j;try{j=await api(path,body);}catch(e){if(stylePreview)stylePreviewLoading(body);button.disabled=false;delete button.dataset.busy;if(assign){assignmentJobs.set(body.sheet,{message:'Could not start the assignment',done:true,usage:{}});renderAssignmentUsage();}else $('#progress').textContent='Could not start';throw e;}
    lastJob=j.id;window.PipeReview?.refreshStatus?.();try{localStorage.setItem('studio-active-job',JSON.stringify({j,body}));}catch{}
    watchJob(j,body);return j;
  }
  function switchPage(p) {
    if(page==='styles'&&!leaveStyle())return;
    styleDirty=false;
    if(p!=='review'){document.body.classList.remove('checking-correction');$('#comparison-return')?.remove();}
    page=p; $('#review-workspace').hidden=p!=='review'; $('#workbench').hidden=p==='review';
    document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===p));
    if(p!=='review'&&!overview)$('#workbench').innerHTML='<section class="panel"><p>Loading saved feedback…</p></section>';
    if(p==='review') window.dispatchEvent(new Event('resize')); else {if(overview)render();act(refresh,'Loading your feedback…');}
  }
  const heading=(tag,title,copy,actions='')=>`<div class="page-heading"><div><div class="eyebrow">${tag}</div><h1>${title}</h1><p>${copy}</p></div><div class="page-actions">${actions}</div></div>`;
  const styleOptions=()=>overview.styles.map(s=>`<option value="${esc(s.draft.id)}" ${s.draft.id===selectedStyle?'selected':''}>${esc(styleName(s.draft.id))}</option>`).join('');
  const styleSelect=()=>`<select id="workbench-style" aria-label="Style">${styleOptions()}</select>`;
  const stateBadge=s=>`<span class="badge state-${esc(s)}">${esc(s)}</span>`;
  function updateFeedbackButton(){
    const button=$('#review-improvements');if(!button||!overview)return;
    const ready=(overview.improvements?.candidates||[]).filter(c=>c.report&&c.workflow_status!=='published').length;
    button.textContent=ready?`See improvements (${ready}) →`:'See improvements →';
  }
  function openMyFeedback(){feedbackDrawing=window.PipeReview?.state()?.sheet||'';advancedLearning=false;switchPage('learning');}
  function feedbackInbox(row){return overview.conversations?.[row.id]?.inbox||(feedbackArchiveReason(row)?'archive':'review');}
  function feedbackArchiveReason(row){
    if(overview.conversations?.[row.id])return overview.conversations[row.id].inbox==='archive'?overview.conversations[row.id].status:'';
    if(['resolved','dismissed'].includes(row.status))return row.status==='resolved'?'Resolved by reviewer':'Dismissed by reviewer';
    if(row.type==='correct'&&row.status==='confirmed')return 'Confirmation saved for future checks';
    const flow=overview.improvements||{};
    const published=(flow.candidates||[]).find(c=>c.workflow_status==='published'&&(c.feedback_ids||c.training_ids||[]).includes(row.id)&&c.report?.cases?.some(k=>k.feedback_id===row.id&&k.after===true));
    if(published)return 'Applied to future analyses';
    const verified=(flow.implementation_requests||[]).find(u=>u.status==='verified'&&(u.feedback_ids||u.training_ids||[]).includes(row.id)&&u.comparisons?.some(c=>c.before===row.snapshot));
    return verified?'App update checked and accepted':'';
  }
  function analysisUsageCard(task){
    const u=task.usage,partial=u?.usage_complete===false;
    const seconds=typeof task.seconds==='number'?task.seconds:null;
    const time=seconds===null?'Unavailable':seconds<60?`${seconds.toFixed(1)} s`:`${Math.floor(seconds/60)} min ${Math.round(seconds%60)} s`;
    const tokens=typeof u?.tokens_total==='number'?`${partial?'≥ ':''}${u.tokens_total.toLocaleString('en-GB')}`:'Unavailable';
    const usd=typeof u?.usd==='number'?`${partial?'≥ ':u.usd?'≈ ':''}$${u.usd.toFixed(4)}`:'Unavailable';
    return `<section class="analysis-receipt" aria-label="Last feedback analysis"><div><strong>${task.status==='error'?'Analysis stopped':'Analysis finished'}</strong><small>${task.finished_at?esc(new Date(task.finished_at).toLocaleString()):''}</small></div><dl><div><dt>Time</dt><dd>${time}</dd></div><div><dt>AI tokens</dt><dd>${tokens}</dd></div><div><dt>USD</dt><dd>${usd}</dd></div></dl><p>${!u?'Usage was not recorded for this older run.':partial?'Partial usage: some requests did not return billing data.':u.calls?'Includes the proposal and all before-and-after AI checks. USD is estimated from the configured model rates.':'No AI requests were needed.'}</p></section>`;
  }
  function feedbackAddedAt(value){
    const date = value ? new Date(value) : null;
    if (!date || Number.isNaN(date.getTime())) return 'Added: date unavailable';
    const text = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Europe/Warsaw', day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short'
    }).format(date);
    return `Added <time datetime="${date.toISOString()}" title="Europe/Warsaw">${esc(text)}</time>`;
  }

  function feedbackTarget(row){
    const targets=[];
    for(const [key,name] of [['stretch_id','Pipe'],['node_id','Joining point'],['leader_id','Leading line'],['path_id','Path'],['label_id','Label']]){
      if(row[key]!=null)targets.push(`${name} #${row[key]}`);
    }
    if(row.designation_idx!=null&&row.label_id!=null)targets.push(`row ${row.designation_idx+1}`);
    if(!targets.length&&row.path_ids?.length)targets.push(`Paths ${row.path_ids.map(id=>`#${id}`).join(', ')}`);
    if(targets.length)return targets.join(' · ');
    const point=row.point||row.points?.[0]||row.rect?.slice(0,2);
    if(point?.length>=2&&point.slice(0,2).every(Number.isFinite)){
      const kind=row.rect?'Marked area':row.points?.length?'Marked line':'Marked point';
      return `${kind} · x ${point[0].toFixed(2)}, y ${point[1].toFixed(2)}`;
    }
    return `Feedback ${row.id}`;
  }

  function renderFeedbackResults(w){
    const focused=document.activeElement, focusedThread=focused?.closest?.('[data-chat]')?.dataset.chat, caret=focusedThread?[focused.selectionStart,focused.selectionEnd]:null;
    const redeploy=page==='redeploy', box=redeploy?'redeploy':'review';
    const inboxScope=JSON.stringify([box,feedbackDrawing]);
    const previousList=w.querySelector?.('.feedback-list');
    const preservePosition=previousList?.dataset.inboxScope===inboxScope;
    const listScroll=preservePosition?previousList.scrollTop:0;
    const pageScroll=preservePosition?document.scrollingElement?.scrollTop:null;
    const workbenchScroll=preservePosition?w.scrollTop:null;
    const focusedItem=preservePosition?focused?.closest?.('[data-select-feedback], [data-open-feedback]'):null;
    const focusKey=focusedItem?.dataset.selectFeedback?'selectFeedback':focusedItem?.dataset.openFeedback?'openFeedback':null;
    const focusId=focusKey?focusedItem.dataset[focusKey]:null;
    const flow=overview.improvements||{batches:[],candidates:[],implementation_requests:[]};
    const inboxRows=overview.feedback.filter(r=>feedbackInbox(r)===box&&(!feedbackDrawing||r.sheet===feedbackDrawing)).sort((a,b)=>(b.ts||'').localeCompare(a.ts||''));
    if(!inboxRows.some(r=>r.id===selectedFeedback[box]))selectedFeedback[box]=inboxRows[0]?.id||null;
    const rows=inboxRows.filter(r=>r.id===selectedFeedback[box]);
    const ids=new Set(rows.map(r=>r.id)), linked=x=>(x.feedback_ids||x.training_ids||[]).some(i=>ids.has(i));
    const candidates=flow.candidates.filter(linked),requests=flow.implementation_requests.filter(linked);
    const tasks=overview.tasks.filter(t=>['check-feedback','feedback-discuss','feedback-answer','accept-improvement','accept-comparison'].includes(t.kind));
    const lastAnalysis=[...tasks].reverse().find(t=>t.kind==='check-feedback'&&['done','error'].includes(t.status)&&(!feedbackDrawing||t.feedback_sheet===feedbackDrawing));
    const running=tasks.filter(t=>['running','queued'].includes(t.status));
    if(feedbackPoll)clearTimeout(feedbackPoll);
    if(running.length)feedbackPoll=setTimeout(()=>{if(['learning','redeploy'].includes(page)&&!advancedLearning)act(refresh,false);},2500);
    const pending=flow.batches.filter(linked), updateCount=overview.feedback.filter(r=>feedbackInbox(r)==='redeploy').length;
    const names={wrong_binding:'Pipe ↔ label assignment',missing_pipe:'Missing pipe',false_pipe:'Pipe detection',missing_node:'Joining point',false_node:'Joining point',wrong_join:'Pipe connection',missing_leader:'Leading line',label_text:'Wrong label text',missing_label:'Missing label',false_label:'Not a label'};
    const labelRows=redeploy?overview.feedback.filter(r=>feedbackInbox(r)==='labels').sort((a,b)=>(b.ts||'').localeCompare(a.ts||'')):[];
    const comparisonFor=new Map(inboxRows.map(r=>[r.id,[...flow.candidates].reverse().find(c=>
      c.report&&c.evaluation&&(c.feedback_ids||c.training_ids||[]).includes(r.id)&&
      !flow.implementation_requests.some(u=>u.deployment_candidate===c.id&&u.status!=='withdrawn'))]).filter(([,c])=>c));
    const currentReports=candidates.filter(c=>c.report&&!requests.some(u=>u.deployment_candidate===c.id&&u.status!=='withdrawn'));
    w.innerHTML=heading('',redeploy?'App updates':'Improvements',redeploy?'We fix and verify reported issues, then move completed feedback to the archive. We only ask for details when they are needed to proceed.':'We test improvements across all styles first. Style exceptions need evidence.')+
      (!redeploy&&updateCount?`<button class="update-notice" id="open-redeploy"><span>${updateCount} ${updateCount===1?'comment awaits':'comments await'} diagnosis or deployment</span><span>View updates →</span></button>`:'')+
      (overview.feedback.some(r=>feedbackInbox(r)===box)?`<div class="inbox-toolbar"><label class="sr-only" for="feedback-drawing">Filter by drawing</label><select id="feedback-drawing"><option value="">All drawings</option>${[...new Set(overview.feedback.filter(r=>feedbackInbox(r)===box).map(r=>r.sheet))].sort().map(sh=>`<option value="${esc(sh)}" ${sh===feedbackDrawing?'selected':''}>${esc(sh)}</option>`).join('')}</select><span>${inboxRows.length} open</span>${!redeploy&&!running.some(t=>t.kind==='check-feedback')&&(flow.batches.some(b=>(b.training_ids||[]).some(id=>inboxRows.some(r=>r.id===id)))||flow.candidates.some(c=>c.workflow_status==='ready_to_test'&&(c.feedback_ids||c.training_ids||[]).some(id=>inboxRows.some(r=>r.id===id))))?'<button class="btn primary" id="check-my-feedback">Find improvements</button><small>Uses AI credits</small>':''}</div>`:'')+
      (lastAnalysis&&!running.some(t=>t.kind==='check-feedback')?analysisUsageCard(lastAnalysis):'')+
      (inboxRows.length?`<div class="feedback-inbox"><nav class="feedback-list" data-inbox-scope="${esc(inboxScope)}" aria-label="Open feedback">${inboxRows.map(r=>{const comparison=comparisonFor.get(r.id);return `<div class="feedback-list-entry ${comparison?'comparison-ready':''}"><button class="feedback-list-item ${r.id===selectedFeedback[box]?'selected':''}" data-select-feedback="${esc(r.id)}" aria-current="${r.id===selectedFeedback[box]?'true':'false'}"><span class="feedback-list-kind">${esc(names[r.type]||r.type.replaceAll('_',' '))}</span>${comparison?'<span class="feedback-compare-status">Comparison ready</span>':''}<span class="feedback-target">${esc(feedbackTarget(r))}</span><strong>${esc(r.note||r.text||'Marked on the drawing')}</strong><span>${esc(r.sheet)}</span><small>${feedbackAddedAt(r.ts)}</small><small>${esc(overview.conversations?.[r.id]?.status||'Saved')}</small></button><div class="feedback-list-actions"><button class="text-btn feedback-location-link" data-open-feedback="${esc(r.id)}" aria-label="${esc('View on drawing: '+feedbackTarget(r)+' · '+r.sheet)}">View on drawing →</button>${comparison?`<button class="text-btn feedback-compare-link" data-list-compare="${esc(comparison.evaluation)}" data-feedback-id="${esc(r.id)}">Compare before & after →</button>`:''}</div></div>`;}).join('')}</nav><div class="feedback-detail">`:'')+
      (running.length?`<section class="panel" role="status"><h2>Working on your feedback</h2>${running.map(t=>`<p>${esc(t.progress||({'feedback-discuss':'AI is reading your message…','feedback-answer':'Saving your answer for the app update…','accept-improvement':'Applying the accepted improvement…','accept-comparison':'Saving acceptance and applying the correction…'}[t.kind])||'Preparing and testing improvements…')}</p>`).join('')}<p>You can continue giving feedback.</p></section>`:'')+
      currentReports.map(c=>{const cases=c.report.cases,manual=cases.filter(k=>k.after==null).length,fail=cases.filter(k=>k.after===false).length;return `<section class="panel result-card"><span class="result-eyebrow">${c.workflow_status==='ready_to_publish'?'Ready to apply':c.workflow_status==='ready_to_test'?'Saved comparison — validation outdated':'Ready to compare'}</span><h2>${esc(c.title)}</h2><p>${esc(c.scope_label||'')} · ${esc(c.feedback_domain==='llm'?'LLM assignments':c.feedback_domain==='dimension'?'Dimension assignments':'Shared geometry and labels')}</p>${c.global_rejection?`<p>${esc(c.global_rejection.reason)}</p>`:''}<details class="result-details"><summary>What changed</summary><p>${esc(c.rationale)}</p><p>${cases.length} checks across ${c.report.documents} drawings</p></details><button class="btn primary" data-simple-compare="${esc(c.evaluation)}">Compare before & after</button> ${c.workflow_status==='ready_to_publish'?`<button class="btn" data-simple-use="${esc(c.id)}">Accept & update drawings</button><p>${c.rule_scope==='global'?'Applies the common change to all styles and refreshes their uploaded drawings.':'Applies the tested exception to this style and refreshes its uploaded drawings.'} LLM analysis uses API credits.</p>`:`<p class="feedback-warning">${c.workflow_status==='ready_to_test'?'This saved result can be reviewed, but it must be validated against the current app before deployment.':c.report.missing_styles?.length?`Global rule pending: add correct examples for ${esc((c.report.missing_style_names||c.report.missing_styles).join(', '))}. This does not make the rule style-specific.`:fail?'The correction is not complete yet. Compare the result and tell us what still needs changing.':manual?'Check the comparison before applying this improvement.':c.report.documents<2||!c.report.holdout_cases?'One more check is needed on another drawing.':'Mark a correct example on the drawing so we can make sure it stays correct.'}</p>${!fail&&!manual?'<button class="text-btn" data-add-check>Choose a drawing to check →</button>':''}`}</section>`;}).join('')+
      requests.filter(u=>u.accepted_comparison&&['awaiting_deployment','deployment_failed'].includes(u.status)).map(u=>`<section class="panel"><span class="result-eyebrow">Solution accepted — awaiting deployment</span><h2>${esc(u.accepted_comparison.title||'Accepted correction')}</h2><p>${esc(u.reason)}</p><p>The feedback will move to the archive after the correction is applied and its drawing is updated.</p><button class="btn" data-deploy-accepted="${esc(u.id)}" ${running.some(t=>t.kind==='accept-comparison')?'disabled':''}>Retry deployment</button></section>`).join('')+
      requests.filter(u=>u.status==='review_app_update').map(u=>`<section class="panel"><h2>Updated app: results ready</h2><p>${esc(u.validation_summary)}</p><button class="btn primary" data-simple-code="${esc(u.id)}">Compare & accept app update</button></section>`).join('')+
      (overview.applications||[]).filter(a=>a.results.some(r=>r.status==='error')).map(a=>`<section class="panel"><h2>Some drawings still need updating</h2><p>The rule was published, but these drawings kept their previous results. Retry updates them with the same analysis method.</p>${a.results.filter(r=>r.status==='error').map(r=>`<p>${esc(r.sheet)}: ${esc(r.reason)}</p>`).join('')}<button class="btn" data-retry-application="${esc(a.candidate_id)}">Retry failed drawings</button></section>`).join('')+
      `<section class="panel feedback-conversations">${rows.length?'':`<div class="inbox-empty"><div class="empty-symbol" aria-hidden="true">✓</div><h2>${feedbackDrawing?'No open feedback for this drawing':redeploy?'No updates waiting':'All caught up'}</h2><p>${redeploy?'When a correction needs a change to the app, you’ll find it here.':'Mark something on a drawing to start your next improvement.'}</p><button class="text-btn" id="empty-archive">View completed feedback</button></div>`}${rows.slice().reverse().map(r=>{
        const thread=overview.conversations?.[r.id]||{},request=requests.find(u=>u.id===thread.comparison_decision?.request_id)||requests.find(u=>(u.feedback_ids||u.training_ids||[]).includes(r.id));
        const conflicts=(r.conflicting_feedback||[]).map(id=>overview.feedback.find(f=>f.id===id)).filter(Boolean);
        const question=thread.clarification?.status==='awaiting_answer'?thread.clarification:null;
        const appUpdateQuestion=question?.origin==='app_updates';
        const update=thread.developer_update?.summary||request?.developer_review?.summary;
        const messages=(thread.messages||[]).filter(m=>!m.withdrawn_at);
        const own=(typeof replyFor==='function'?replyFor(r.id,thread.status):null);const awaitingReply=own===undefined;const reply=question?'Let’s work out the intended result together. You can confirm the suggestion below or describe it in your own words.':update||own?.text||(awaitingReply?'Reading the saved drawing to answer this one…':null)||request?.reason|| (conflicts.length?'These comments describe different assignments for the same pipe. Open the drawing and remove the outdated comment.':r.review_warnings?.length?r.review_warnings.join(' '):candidates.some(c=>(c.feedback_ids||c.training_ids||[]).includes(r.id))?'A proposed improvement is linked to your feedback. Check its result above, or explain what still needs changing.':'Saved. Select Find improvements to test a possible correction. You’ll see the result here before anything is applied.');
        const chatRunning=running.some(t=>['feedback-discuss','check-feedback','feedback-answer'].includes(t.kind)&&t.feedback_id===r.id);
        const relatedIds=[...pending,...candidates].filter(x=>(x.feedback_ids||x.training_ids||[]).includes(r.id)).map(x=>x.id);
        const lastCheck=[...tasks].reverse().find(t=>t.kind==='check-feedback');
        const blocked=lastCheck?.result?.outcomes?.find(o=>relatedIds.includes(o.id)&&o.status==='needs_attention');
        return `<article class="feedback-conversation" id="conversation-${esc(r.id)}"><div class="developer-comment-heading"><h3>${esc(names[r.type]||r.type.replaceAll('_',' '))}</h3><span class="badge">${esc(thread.status||'Saved')}</span></div><p class="feedback-target">${esc(feedbackTarget(r))}</p><p class="developer-comment-meta">${esc(r.sheet)} · ${esc(scopeName(r))}<br>${feedbackAddedAt(r.ts)}</p><div class="feedback-message reviewer-message"><b>${esc(r.author||'Reviewer')}</b><p>${esc(r.note||r.text||'Correction marked on the drawing.')}</p></div><div class="feedback-message app-message"><b>Pipe Studio</b><p${awaitingReply&&!update&&!question?' class="reply-pending"':''}>${esc(reply)}</p>${!question&&!update&&own?.options?.length?`<div class="reply-options">${own.options.map(o=>`<button type="button" class="btn" data-reply-option="${esc(r.id)}" data-answer="${esc(o)}">${esc(o)}</button>`).join('')}</div>`:''}${!question&&own&&(own.detail||request?.reason)?`<details class="reply-detail"><summary>Technical detail for the developer</summary>${own.detail?`<p>Engine: ${esc(own.detail)}</p>`:''}${request?.reason?`<p>${esc(request.reason)}</p>`:''}</details>`:''}${blocked?`<p class="feedback-warning">The last group test stopped: ${esc(blocked.reason)}</p>`:''}${conflicts.map(f=>`<blockquote><b>Conflicting comment</b><p>${esc(f.note||'Confirmed saved assignment')}</p><button class="text-btn" data-open-feedback="${esc(f.id)}">View on drawing</button><button class="text-btn" data-dismiss-feedback="${esc(f.id)}">Remove outdated comment</button></blockquote>`).join('')}</div>${messages.map(m=>`<div class="feedback-message ${m.role==='expert'?'reviewer-message':'app-message'}"><b>${esc(m.role==='expert'?m.author||'Reviewer':m.origin==='app_updates'?'AI rebuilding the app':'Pipe Studio')}</b><p>${esc(m.text)}</p>${question?.id===m.question_id?(m.choices||[]).map(choice=>`<button type="button" class="btn" data-answer-choice="${esc(r.id)}" data-answer="${esc(choice)}" ${chatRunning?'disabled':''}>${esc(choice)}</button>`).join(''):''}${(m.rule_conflicts||[]).map(rule=>`<blockquote><b>Possible conflict with rule: ${esc(rule.id)}</b><p>${esc(rule.instruction)}</p><small>AI assessment — confirm the intended convention before changing this rule.</small></blockquote>`).join('')}</div>`).join('')}${!expandedChat.has(r.id)&&!messages.length?`<button class="text-btn open-chat" data-expand-chat="${esc(r.id)}">Add a detail or ask a question</button>`:''}<form class="feedback-chat" data-chat="${esc(r.id)}" data-question="${esc(question?.id||'')}" ${!expandedChat.has(r.id)&&!messages.length?'hidden':''}><label>${question?'Your answer':'Continue the conversation'}<textarea name="message" maxlength="4000" required placeholder="Optional additional information" ${chatRunning?'disabled':''}></textarea></label><button class="btn" ${chatRunning?'disabled':''}>${chatRunning?appUpdateQuestion?'Saving answer…':'Analysing…':appUpdateQuestion?'Send answer':question?'Answer & analyse':'Send'}</button><small>${appUpdateQuestion?'Your answer is saved for the AI rebuilding the app. No AI call or automatic rebuild is started.':'AI replies use API credits. Sending a message does not apply a change.'}</small></form><div class="developer-comment-actions"><button class="btn" data-open-feedback="${esc(r.id)}">View on drawing</button>${!update&&!redeploy&&!question&&r.status==='open'&&((thread.messages||[]).some(m=>m.role==='expert')||request||candidates.some(c=>(c.feedback_ids||c.training_ids||[]).includes(r.id)))?`<button class="btn" data-retry-feedback="${esc(r.id)}">Try this explanation</button>`:''}${request?`<button class="text-btn" data-simple-brief="${esc(request.id)}">Developer brief</button>`:''}<button class="text-btn" data-dismiss-feedback="${esc(r.id)}">Remove feedback</button></div></article>`;
      }).join('')}</section>`+(inboxRows.length?'</div></div>':'')+
      (redeploy?`<section class="panel label-report"><div class="section-bar"><div><span class="eyebrow">OTHER TEAM</span><h2>Label recognition</h2></div><span class="muted">${labelRows.length} open</span>${labelRows.length?'<button class="btn" id="download-label-report">Download report (.md)</button>':''}</div><p class="muted">Missing labels, marks that are not labels and misread label text are handled by the label-recognition team, not here. The report lists every open comment with its location on the drawing; downloading it changes nothing.</p>${labelRows.length?`<div class="label-list">${labelRows.map(r=>`<div class="feedback-list-entry"><div class="feedback-list-item"><span class="feedback-list-kind">${esc(names[r.type]||r.type)}</span><span class="feedback-target">${esc(feedbackTarget(r))}</span><strong>${esc(r.note||r.text||'Marked on the drawing')}</strong><span>${esc(r.sheet)}</span><small>${feedbackAddedAt(r.ts)}</small></div><div class="feedback-list-actions"><button class="text-btn feedback-location-link" data-open-feedback="${esc(r.id)}" aria-label="${esc('View on drawing: '+feedbackTarget(r)+' · '+r.sheet)}">View on drawing →</button></div></div>`).join('')}</div>`:'<p>No open label feedback.</p>'}</section>`:'');
    w.querySelectorAll('[data-select-feedback]').forEach(b=>b.onclick=()=>{selectedFeedback[box]=b.dataset.selectFeedback;render();});
    $('#empty-archive')?.addEventListener('click',()=>switchPage('feedback'));
    if($('#feedback-drawing'))$('#feedback-drawing').onchange=e=>{feedbackDrawing=e.target.value;render();};
    w.querySelectorAll('[data-add-check]').forEach(b=>b.onclick=()=>{switchPage('review');renderDrawingLibrary();$('#drawings-dialog').showModal();});
    $('#open-redeploy')?.addEventListener('click',()=>{feedbackDrawing='';switchPage('redeploy');});
    $('#check-my-feedback')?.addEventListener('click',()=>act(async()=>{await job('check-feedback',{sheet:feedbackDrawing||null});await refresh();}));
    w.querySelectorAll('[data-expand-chat]').forEach(b=>b.onclick=()=>{expandedChat.add(b.dataset.expandChat);render();[...w.querySelectorAll('[data-chat]')].find(f=>f.dataset.chat===b.dataset.expandChat)?.elements.message.focus();});
    w.querySelectorAll('[data-chat]').forEach(form=>{const input=form.elements.message;input.value=chatDrafts.get(form.dataset.chat)||'';input.oninput=()=>chatDrafts.set(form.dataset.chat,input.value);form.onsubmit=e=>{e.preventDefault();act(async()=>{if(!name()){askName();return;}const message=input.value;await job(form.dataset.question?'feedback-answer':'feedback-discuss',{id:form.dataset.chat,question_id:form.dataset.question,message,author:name()});chatDrafts.delete(form.dataset.chat);await refresh();});};});
    w.querySelectorAll('[data-reply-option]').forEach(b=>b.onclick=()=>{const id=b.dataset.replyOption;if(!expandedChat.has(id)){expandedChat.add(id);render();}const input=[...$('#workbench').querySelectorAll('[data-chat]')].find(f=>f.dataset.chat===id)?.elements.message;if(input){input.value=b.dataset.answer;chatDrafts.set(id,input.value);input.focus();}});
    w.querySelectorAll('[data-answer-choice]').forEach(b=>b.onclick=()=>{const input=[...w.querySelectorAll('[data-chat]')].find(f=>f.dataset.chat===b.dataset.answerChoice)?.elements.message;if(input){input.value=b.dataset.answer;chatDrafts.set(b.dataset.answerChoice,input.value);input.focus();}});
    if(focusedThread){const input=[...w.querySelectorAll('[data-chat]')].find(f=>f.dataset.chat===focusedThread)?.elements.message;if(input&&!input.disabled){input.focus({preventScroll:true});input.setSelectionRange(...caret);}}
    w.querySelectorAll('[data-dismiss-feedback]').forEach(b=>b.onclick=()=>act(async()=>{if(!name()){askName();return;}await api('feedback/status',{id:b.dataset.dismissFeedback,status:'dismissed',author:name()});await refresh();}));
    w.querySelectorAll('[data-retry-feedback]').forEach(b=>b.onclick=()=>act(async()=>{await api('feedback-retry',{id:b.dataset.retryFeedback});await job('check-feedback',{sheet:overview.feedback.find(r=>r.id===b.dataset.retryFeedback).sheet});await refresh();}));
    w.querySelectorAll('[data-list-compare]').forEach(b=>b.onclick=()=>act(async()=>{selectedFeedback[box]=b.dataset.feedbackId;await startComparison(b.dataset.listCompare);}));
    w.querySelectorAll('[data-simple-compare]').forEach(b=>b.onclick=()=>act(()=>startComparison(b.dataset.simpleCompare)));
    w.querySelectorAll('[data-retry-application]').forEach(b=>b.onclick=()=>act(async()=>{await job('retry-application',{id:b.dataset.retryApplication,author:name()});await refresh();}));
    w.querySelectorAll('[data-deploy-accepted]').forEach(b=>b.onclick=()=>act(async()=>{if(!name()){askName();return;}const request=requests.find(u=>u.id===b.dataset.deployAccepted);b.disabled=true;b.dataset.busy='job';await job('accept-comparison',{evaluation:request.accepted_comparison.evaluation,feedback_id:request.feedback_ids[0],author:name()});await refresh();}));
    w.querySelectorAll('[data-simple-use]').forEach(b=>b.onclick=()=>act(async()=>{if(!name()){askName();return;}await job('accept-improvement',{id:b.dataset.simpleUse,author:name()});await refresh();}));
    w.querySelectorAll('[data-simple-code]').forEach(b=>b.onclick=()=>act(()=>startCodeComparison(b.dataset.simpleCode)));
    w.querySelectorAll('[data-simple-brief]').forEach(b=>b.onclick=()=>act(async()=>download(b.dataset.simpleBrief+'.json',await api('implementation-brief?id='+b.dataset.simpleBrief))));
    const labelReport=w.querySelector?.('#download-label-report');if(labelReport)labelReport.onclick=()=>act(async()=>{const report=await api('label-report');downloadText(report.filename,report.markdown,'text/markdown');},'Preparing the label report…');
    w.querySelectorAll('[data-open-feedback]').forEach(b=>b.onclick=()=>act(async()=>{const row=overview.feedback.find(r=>r.id===b.dataset.openFeedback),returnPage=page;selectedFeedback[box]=row.id;await openSnapshot(row.snapshot);window.PipeReview.focusFeedback(row);const bar=document.createElement('div');bar.id='comparison-return';bar.className='comparison-banner';bar.innerHTML=`<p><strong>${esc(feedbackTarget(row))}</strong> · ${esc(row.note||row.type.replaceAll('_',' '))}</p><button class="btn" id="back-to-conversation">Back to conversation</button>`;$('#review-workspace').prepend(bar);$('#back-to-conversation').onclick=()=>{switchPage(returnPage);};}));
    // Replacing the inbox DOM must not reset the user's place or keyboard focus.
    const nextList=w.querySelector?.('.feedback-list');
    if(nextList)nextList.scrollTop=listScroll;
    if(focusId){
      const target=[...w.querySelectorAll('[data-select-feedback], [data-open-feedback]')].find(b=>b.dataset[focusKey]===focusId);
      target?.focus({preventScroll:true});
    }
    if(workbenchScroll!=null)w.scrollTop=workbenchScroll;
    if(pageScroll!=null&&document.scrollingElement)document.scrollingElement.scrollTop=pageScroll;
  }
  async function startComparison(id){
    setBusy(true,'Opening the before and after drawings…');
    try{ return await startComparisonInner(id); } finally { setBusy(false); }
  }
  async function startComparisonInner(id){
    const report=await api('evaluation?id='+encodeURIComponent(id));
    if(!report.cases.length){notify('No drawing comparisons are available yet.');return;}
    const reviewCases=report.cases.filter(c=>['manual','fixed','regression','fail'].includes(c.outcome));
    const selectedId=selectedFeedback.review;
    const cases=reviewCases.length?reviewCases:report.cases.slice(0,1);
    const selectedCase=report.cases.find(c=>c.feedback_id===selectedId);
    if(selectedCase){
      const index=cases.indexOf(selectedCase);
      if(index>=0)cases.splice(index,1);
      cases.unshift(selectedCase);
    }
    comparisonSession={report,cases,index:0,side:'after',answers:{}};await renderComparison();
  }
  async function startCodeComparison(id){
    const item=overview.improvements.implementation_requests.find(u=>u.id===id);
    comparisonSession={implementation:item,index:0,side:'after',answers:{}};await renderComparison();
  }
  async function renderComparison(){
    const session=comparisonSession, code=session.implementation;
    const cases=code?code.comparisons:session.cases, c=cases[session.index];
    const sid=code?c[session.side]:c.snapshot;
    const rv=await api(code?'snapshot?id='+encodeURIComponent(sid):`evaluation-result?id=${encodeURIComponent(session.report.id)}&snapshot=${encodeURIComponent(sid)}&side=${session.side}`);
    switchPage('review');document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===(code?'redeploy':'learning')));document.body.classList.add('checking-correction');window.PipeReview.showResult(rv,'/api/studio/snapshot-bg?id='+encodeURIComponent(sid));
    const row=overview.feedback.find(r=>r.id===c.feedback_id);
    if(row){
      session.referenceResults ||= {};
      const referenceId=row.snapshot||sid;
      const reference=session.referenceResults[referenceId] ||= await api('snapshot?id='+encodeURIComponent(referenceId));
      window.PipeReview.focusFeedback(row,reference);
    }
    $('#comparison-return')?.remove();const bar=document.createElement('div');bar.id='comparison-return';bar.className='comparison-banner simple-comparison';
    const needsAnswer=!!code||session.side==='after';
    if(!session.answers[session.index])session.answers[session.index]=!code&&typeof c.before==='boolean'?{before:c.before}:{};
    const answers=session.answers[session.index];
    bar.innerHTML=`<div><b>Correction ${session.index+1} of ${cases.length} · ${esc(c.sheet)}</b><p>${row?`<strong>${esc(feedbackTarget(row))}</strong> · `:''}${esc(row?.note||row?.type?.replaceAll('_',' ')||'Compare the original and revised result.')}</p>${row?'<small>Blue outline marks the feedback location on both views.</small>':''}${!code?'<small>On After: Yes applies the solution or queues deployment. No sends it for diagnosis. Your decision is saved immediately. Updating drawings may use AI credits.</small>':''}</div><div class="toggle"><button class="toggle-opt" id="compare-before" aria-checked="${session.side==='before'}">Before</button><button class="toggle-opt" id="compare-after" aria-checked="${session.side==='after'}">After</button></div>${needsAnswer?`<div><b>${session.side==='before'?'Was the original result correct?':'Is this improvement correct?'}</b><div><button class="btn ${answers[session.side]===true?'primary':''}" data-compare-answer="true">Yes</button> <button class="btn ${answers[session.side]===false?'primary':''}" data-compare-answer="false">No</button></div></div>`:`<span>Original result. Switch to After to accept the solution or send it for diagnosis.</span>`}<button class="btn primary" id="compare-next" ${!code?'hidden':''} ${answers.before===undefined||answers.after===undefined?'disabled':''}>${session.index+1<cases.length?'Next correction →':'Save review'}</button><button class="text-btn" id="compare-exit">← Back to review</button>`;
    $('#review-workspace').prepend(bar);
    $('#compare-before').onclick=()=>act(async()=>{session.side='before';await renderComparison();});
    $('#compare-after').onclick=()=>act(async()=>{session.side='after';await renderComparison();});
    bar.querySelectorAll('[data-compare-answer]').forEach(b=>b.onclick=()=>act(async()=>{
      if(session.saving)return;
      if(!code&&session.side==='after'){
        if(!name()){askName();return;}
        session.saving=true;
        bar.querySelectorAll('button').forEach(button=>button.disabled=true);
        try{
          const body={evaluation:session.report.id,feedback_id:c.feedback_id,author:name()};
          if(b.dataset.compareAnswer==='true')await job('accept-comparison',body);
          else await api('reject-comparison',body);
          bar.remove();comparisonSession=null;
          selectedFeedback.redeploy=c.feedback_id;switchPage('redeploy');await refresh();
          notify(b.dataset.compareAnswer==='true'?'Acceptance saved for processing. Applying the correction when validation passes.':'Feedback sent to App updates for developer diagnosis.');
        }catch(error){await renderComparison();throw error;}
        finally{session.saving=false;}
        return;
      }
      session.answers[session.index]={...answers,[session.side]:b.dataset.compareAnswer==='true'};
      if(session.side==='after'&&session.answers[session.index].before===undefined)session.side='before';
      else if(session.side==='before')session.side='after';
      await renderComparison();
    }));
    $('#compare-exit').onclick=()=>{bar.remove();advancedLearning=false;switchPage(code?'redeploy':'learning');};
    $('#compare-next').onclick=()=>act(async()=>{
      const answer=session.answers[session.index]||{};
      if(needsAnswer&&(answer.before===undefined||answer.after===undefined))throw new Error('Check Before and After and answer Yes or No for each.');
      if(needsAnswer&&!code){if(!name()){askName();return;}await api('review-case',{evaluation:session.report.id,feedback_id:c.feedback_id,before:answer.before,after:answer.after,author:name()});}
      if(session.index+1<cases.length){session.index++;session.side='after';await renderComparison();return;}
      if(code){if(!name()){askName();return;}await api('review-implementation',{id:code.id,accepted:cases.every((_,i)=>session.answers[i]?.after===true),author:name()});}
      bar.remove();comparisonSession=null;advancedLearning=false;switchPage(code?'redeploy':'learning');
    });
  }
  function render() {
    const w=$('#workbench'); if(!overview)return;
    if(['learning','redeploy'].includes(page)&&!advancedLearning){renderFeedbackResults(w);return;}
    if(page==='feedback') {
      const allRows=overview.feedback.filter(r=>r.style_id===selectedStyle&&feedbackArchiveReason(r));
      const rows=allRows.filter(r=>(!feedbackSheet||r.sheet===feedbackSheet)&&(!feedbackMethod||scopeOf(r)===feedbackMethod)&&(feedbackView==='all'||(feedbackView==='open'&&r.status==='open')||(feedbackView==='clarify'&&r.status!=='dismissed'&&r.review_warnings?.length)));
      const byMethod=m=>allRows.filter(r=>scopeOf(r)===m).length;
      const expected=r=>{const b=r.type==='correct'?r.evidence?.expected_bindings?.[0]:r.type==='wrong_binding'?{label:r.label_id,designation_idx:r.designation_idx}:undefined;return b?b.label===null?'No label':`Label ${b.label} · designation ${(b.designation_idx??0)+1}`:r.type==='correct'&&r.tab==='bindings'?'No label':'—';};
      w.innerHTML=heading('FEEDBACK','Feedback archive','Completed feedback and saved confirmations. These examples remain available for future regression checks.',styleSelect()+`<button class="btn primary" id="feedback-improvements">Current Feedback →</button>`)+
        `<div class="metric-grid"><article><small>CAPTURED EXAMPLES</small><strong>${allRows.length}</strong><p>With immutable analysis context</p></article><article><small>POSITIVE CONFIRMATIONS</small><strong>${allRows.filter(r=>r.type==='correct').length}</strong><p>Behaviour future rules must preserve</p></article><article><small>OCR EXAMPLES</small><strong>${allRows.filter(r=>r.track==='ocr').length}</strong><p>For the label-reading training queue</p></article><article><small>ASSIGNMENT EXAMPLES</small><strong>${byMethod('dimension')} <small>Dimension</small> · ${byMethod('llm')} <small>LLM</small></strong><p>${byMethod('shared')} shared vector & OCR examples · previews and unknown methods kept separate</p></article></div>`+
        ((overview.vector_previews||[]).length?`<details class="panel"><summary>Saved vector update comparisons · ${(overview.vector_previews||[]).length} drawings</summary><p>Inspect the saved geometry before and after the update. After is a vector preview; run Dimension or LLM to review final assignments.</p>${overview.vector_previews.map(p=>`<div class="section-bar"><b>${esc(p.sheet)}</b><button class="btn" data-snapshot="${esc(p.before)}">Before update</button><button class="btn" data-snapshot="${esc(p.after)}">After · vector preview</button></div>`).join('')}</details>`:'')+
        `<div class="section-bar"><label>Drawing<select id="feedback-sheet"><option value="">All drawings</option>${[...new Set(allRows.map(r=>r.sheet))].sort().map(sh=>`<option value="${esc(sh)}" ${sh===feedbackSheet?'selected':''}>${esc(sh)}</option>`).join('')}</select></label><label>Feedback scope<select id="feedback-method">${[['','All feedback'],['shared','Shared feedback'],['dimension','Dimension assignments'],['llm','LLM assignments'],['preview','Preview assignments'],['unknown','Assignment method unknown']].map(([v,t])=>`<option value="${v}" ${v===feedbackMethod?'selected':''}>${t}</option>`).join('')}</select></label><label>Show<select id="feedback-view">${[['all','All archived records']].map(([v,t])=>`<option value="${v}" ${v===feedbackView?'selected':''}>${t}</option>`).join('')}</select></label><p>${rows.length} of ${allRows.length} records</p></div>`+
        `<div class="section-bar"><h2>Archived feedback</h2><button class="btn" id="export-ocr">Export OCR evidence ↗</button></div>`+
        `<div class="table-wrap"><table class="data-table"><thead><tr><th>Feedback scope</th><th>Drawing & evidence</th><th>Expected assignment</th><th>Expert note</th><th>Status</th><th></th></tr></thead><tbody>`+
        rows.map(r=>`<tr><td><span class="track">${esc(r.track)}</span><b>${esc(r.type.replaceAll('_',' '))}</b>${methodBadge(r)}<small>Result: ${esc(resultName(r))}</small></td><td>${esc(r.sheet)}<b>${r.stretch_id!==undefined?'Pipe '+esc(r.stretch_id):r.node_id!==undefined?'Joining point '+esc(r.node_id):esc(r.type.replaceAll('_',' '))}</b><small>${esc(r.author)} · ${feedbackAddedAt(r.ts)}</small><small>Analysis ${esc(r.snapshot.slice(0,8))} · ${esc(r.id)}</small><button class="text-btn" data-snapshot="${esc(r.snapshot)}">Open saved analysis ↗</button></td><td>${esc(expected(r))}</td><td>${esc(r.note||r.text||'—')}${r.duplicate_of?`<small>Repeated assertion · counted once in evaluation · ${esc(r.duplicate_of)}</small>`:''}${(r.review_warnings||[]).map(w=>`<small class="feedback-warning">Needs clarification: ${esc(w)}</small>`).join('')}</td><td>${esc(feedbackArchiveReason(r))}</td><td>${stateBadge(r.status)}<button class="text-btn" data-archived-chat="${esc(r.id)}">Read conversation</button>${r.status==='dismissed'?`<button class="text-btn" data-restore-feedback="${esc(r.id)}">Restore feedback</button>`:''}</td></tr>`).join('')+
        `</tbody></table>${!rows.length?'<div class="empty-card">No feedback matches these filters.</div>':''}</div>`+
        `<details class="panel"><summary>Historical feedback · ${overview.legacy.length} records</summary><p>These records have no frozen analysis. Recheck their geometry and record a new example before using them for evaluation.</p>`+
        overview.legacy.map(r=>`<div class="legacy-row"><b>${esc(r.sheet)} · ${esc(r.type)}</b><p>${esc(r.note||'No note')}</p></div>`).join('')+'</details>';
      w.querySelectorAll('[data-archived-chat]').forEach(b=>b.onclick=()=>{const r=overview.feedback.find(r=>r.id===b.dataset.archivedChat),thread=overview.conversations?.[r.id];const dialog=document.createElement('dialog');dialog.innerHTML=`<h2>Archived conversation</h2><p>${esc(r.sheet)} · ${esc(feedbackArchiveReason(r))}</p><div class="feedback-message reviewer-message"><b>${esc(r.author)}</b><p>${esc(r.note||r.text||'Feedback marked on drawing.')}</p></div>${(thread?.messages||[]).map(m=>`<div class="feedback-message ${m.role==='expert'?'reviewer-message':'app-message'}"><b>${esc(m.role==='expert'?m.author:'Pipe Studio')}</b><p>${esc(m.text)}</p></div>`).join('')}<button class="btn">Close</button>`;document.body.append(dialog);dialog.querySelector('button').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();dialog.showModal();});
      w.querySelectorAll('[data-restore-feedback]').forEach(b=>b.onclick=()=>act(async()=>{if(!name()){askName();return;}const r=overview.feedback.find(r=>r.id===b.dataset.restoreFeedback);await api('feedback/status',{id:r.id,status:r.type==='correct'?'confirmed':'open',author:name()});await refresh();}));
      $('#feedback-improvements').onclick=()=>{improvementStyle=selectedStyle;switchPage('learning');};
      $('#feedback-sheet').onchange=e=>{feedbackSheet=e.target.value;render();};
      $('#feedback-view').onchange=e=>{feedbackView=e.target.value;render();};
      $('#feedback-method').onchange=e=>{feedbackMethod=e.target.value;render();};
      $('#export-ocr').onclick=()=>act(async()=>{ const data=await api('ocr-export'); download('ocr-evidence.json',data); });
      w.querySelectorAll('[data-status]').forEach(s=>s.onchange=()=>act(async()=>{await api('feedback/status',{id:s.dataset.status,status:s.value,author:name()});await refresh();}));
      w.querySelectorAll('[data-snapshot]').forEach(b=>b.onclick=()=>act(()=>openSnapshot(b.dataset.snapshot)));
    }
    if(page==='styles') {
      const entry=overview.styles.find(s=>s.draft.id===selectedStyle)||overview.styles[0], p=entry.draft;
      selectedStyle=p.id;
      styleDirty=false;
      w.innerHTML=heading('STYLE LIBRARY','Styles & rules','Edit an existing drawing style or create a new one. A style defines how pipe geometry is interpreted across drawings.',`<button id="delete-style" class="btn" ${p.id==='style-1'?'disabled title="The default fallback style is required"':''}>Delete style</button><button id="open-new-style" class="btn primary">＋ Create new style</button>`)+
        `<section class="panel style-toolbar"><label>Editing style${styleSelect()}</label><div>${stateBadge(entry.active?'Active version '+entry.active:'Draft only')}<p>${entry.active?'Analyses use the active version. The form below edits a separate draft.':'This style has not been published. Save and test it before using it in analyses.'}</p></div></section>`+
        `<div class="style-steps"><span><b>1</b> Edit settings</span><span><b>2</b> Save draft</span><span><b>3</b> Test in Improvements</span><span><b>4</b> Publish after review</span></div>`+
        `<section class="panel"><div class="section-bar"><div><div class="eyebrow">EDIT DRAFT</div><h2>${esc(styleName(p.id))}</h2></div><span id="style-save-state" class="muted" role="status">Saved draft</span></div><div class="two-columns"><label>Style name<input id="style-name" value="${esc(p.name)}"></label><label>Description<textarea id="style-description">${esc(p.description)}</textarea></label></div></section>`+
        `<section class="panel"><div class="section-bar"><div><h2>Pipe assignment rules</h2><p>Instructions for LLM assignment: how labels relate to pipes. These do not change the Dimension assignment algorithm.</p></div><button id="add-rule" class="btn">＋ Add rule</button></div><div id="rule-cards" class="rule-grid">`+
        p.rules.map((r,i)=>`<article class="panel rule-card" data-rule="${esc(r.id)}"><span class="rule-number">Rule ${i+1}</span><h3>${esc(r.id.replaceAll('-',' '))}</h3><textarea aria-label="Rule instruction">${esc(r.instruction)}</textarea><button class="text-btn" data-remove-rule>Remove rule</button></article>`).join('')+`</div></section>`+
        (p.stroke_policy?`<details class="panel"><summary><b>AI vector inspection</b> · saved in this style</summary><p>Only families classified as pipes are pipe candidates. Mixed, uncertain and unseen families stay unclassified.</p>${p.stroke_policy.families.map(f=>`<p><b>${esc(f.role)}</b> · relative width ${esc(f.key.width)} · ${esc(f.key.layer||'no layer')} — ${esc(f.reason)}</p>`).join('')}</details>`:'')+
        `<details class="panel"><summary><b>Advanced geometry settings</b> · joining pipes, gaps and label reach</summary><p>These values affect both assignment methods. Distances are multiples of the drawing’s leader line width. Leave a field blank to use the engine default.</p>`+
        Object.entries(overview.parameters).map(([key,[lo,hi,label]])=>`<label class="parameter">${esc(label)}<input data-param="${esc(key)}" type="number" step="any" min="${lo}" max="${hi}" value="${p.calibration[key]??''}" placeholder="Default"><small>${lo}–${hi}</small></label>`).join('')+`</details>`+
        `<details class="panel"><summary><b>Automatic style recognition</b> · ${p.signatures.length} saved examples</summary><p>Add an already analysed drawing as a recognition example. This helps identify similar drawings; it does not learn new rules or publish changes.</p><label>Example drawing<select id="calibration-sheet"></select></label><button class="btn" id="calibrate-style">Save draft & add recognition example</button><p id="recognition-help" class="muted"></p></details>`+
        `<div class="panel style-save-bar"><div><b>Apply your changes in two steps</b><p>Save keeps a draft. Testing opens Improvements, where you evaluate it on feedback and publish an approved version.</p></div><button id="save-style" class="btn">Save draft</button><button id="draft-candidate" class="btn primary">Save & test changes →</button></div>`+
        `<details class="panel"><summary><b>Version history</b> · ${entry.releases.length} versions</summary><p>Activating an earlier version changes the version used by new analyses.</p>${entry.releases.map(r=>`<div class="release-row"><div><b>Version ${r.version}</b>${r.source_style_id?`<p>${esc(r.name)} · original version ${r.source_version}</p>`:''}<p>${esc(r.published_at||'Migrated baseline · quality not yet measured')}</p></div>${r.version===entry.active?stateBadge('active'):`<button class="btn" data-activate="${r.version}">Use this version</button>`}</div>`).join('')||'<p>No published versions yet.</p>'}</details>`+
        `<dialog id="create-style-dialog" aria-labelledby="create-style-title"><form id="create-style-form"><div class="eyebrow">NEW DRAWING STYLE</div><h2 id="create-style-title">Create a style</h2><p>Start with an existing style’s rules and geometry settings. The new style has its own draft and history.</p><label>New style name<input id="new-style-name" required maxlength="150" placeholder="e.g. Design office - PDF exporter 2026"></label><label>Copy settings from<select id="new-style-base">${styleOptions()}</select></label><p class="muted">Recognition examples are not copied. After creating the draft, review its rules, add a drawing example and test it in Improvements.</p><p id="create-style-error" role="alert"></p><div class="dialog-actions"><button type="button" id="cancel-new-style" class="btn">Cancel</button><button type="submit" class="btn primary">Create draft</button></div></form></dialog>`;
      const select=$('#calibration-sheet'); document.querySelectorAll('#sheet option').forEach(o=>select.add(new Option(o.textContent,o.value))); select.value=window.PipeReview?.state()?.sheet||select.value;
      const markDirty=()=>{styleDirty=true;$('#style-save-state').textContent='Unsaved changes';};
      w.querySelectorAll('#style-name,#style-description,[data-param],[data-rule] textarea').forEach(e=>e.addEventListener('input',markDirty));
      $('#rule-cards').addEventListener('click',e=>{if(e.target.closest('[data-remove-rule]')){e.target.closest('[data-rule]').remove();markDirty();}});
      const save=async()=>{
        if(!$('#style-name').value.trim())throw new Error('Enter a style name.');
        for(const field of w.querySelectorAll('[data-param]'))if(!field.checkValidity()){field.closest('details').open=true;field.reportValidity();throw new Error('Check the geometry settings marked in the form.');}
        const calibration={};w.querySelectorAll('[data-param]').forEach(e=>{if(e.value!=='')calibration[e.dataset.param]=Number(e.value)});
        const rules=[...w.querySelectorAll('[data-rule]')].map(e=>({id:e.dataset.rule,stage:'binding',instruction:e.querySelector('textarea').value}));
        const result=await api('style',{style_id:selectedStyle,name:$('#style-name').value.trim(),description:$('#style-description').value,calibration,rules});
        styleDirty=false;$('#style-save-state').textContent='Saved draft';return result;
      };
      $('#delete-style').onclick=()=>act(async()=>{
        if(!window.confirm(`Delete “${p.name}” from the style library? Saved analyses and version history will be preserved.`))return;
        await api('delete-style',{style_id:p.id,author:name()});
        styleDirty=false;selectedStyle='style-1';if(reviewStyle===p.id)reviewStyle='auto';
        await refresh();notify('Style deleted from the library. Saved analyses are preserved.');
      });
      $('#save-style').onclick=()=>act(async()=>{await save();notify('Draft saved. The published service release is unchanged.');await refresh();});
      $('#draft-candidate').onclick=()=>act(async()=>{await save();await api('candidate',{style_id:selectedStyle,title:'Review changes to '+p.name});switchPage('learning');});
      $('#add-rule').onclick=()=>{const el=document.createElement('article');el.className='panel rule-card';el.dataset.rule='convention-'+Date.now().toString(36);el.innerHTML='<h3>New rule</h3><textarea aria-label="Rule instruction" placeholder="Describe how pipes and labels relate in this style…"></textarea><button class="text-btn" data-remove-rule>Remove rule</button>';$('#rule-cards').append(el);el.querySelector('textarea').addEventListener('input',markDirty);el.querySelector('textarea').focus();markDirty();};
      $('#calibrate-style').disabled=!select.options.length;
      $('#recognition-help').textContent=select.options.length?'Uses the drawing’s existing analysis.':'No analysed drawings available. Upload and analyse a PDF in Drawing review first.';
      $('#calibrate-style').onclick=()=>act(async()=>{await save();await api('calibrate',{style_id:selectedStyle,sheets:[select.value]});notify('Recognition example saved to this draft.');await refresh();});
      const dialog=$('#create-style-dialog');
      $('#open-new-style').onclick=()=>dialog.showModal();
      $('#cancel-new-style').onclick=()=>dialog.close();
      $('#create-style-form').onsubmit=async e=>{
        e.preventDefault();const button=e.submitter;const title=$('#new-style-name').value.trim();
        if(!title){$('#create-style-error').textContent='Enter a style name.';return;}
        if(overview.styles.some(s=>s.draft.name.toLowerCase()===title.toLowerCase())){$('#create-style-error').textContent='A style with this name already exists. Choose another name.';return;}
        if(!leaveStyle())return;
        const base=overview.styles.find(s=>s.draft.id===$('#new-style-base').value).draft;
        const id='style-'+crypto.randomUUID();button.disabled=true;$('#create-style-error').textContent='';
        try{
          await api('style',{style_id:id,name:title,description:base.description,calibration:base.calibration,rules:base.rules});
          styleDirty=false;selectedStyle=id;dialog.close();await refresh();notify('New draft created. Review its settings, then save and test it.');
        }catch(error){$('#create-style-error').textContent=error.message;button.disabled=false;}
      };
      w.querySelectorAll('[data-activate]').forEach(b=>b.onclick=()=>act(async()=>{if(!leaveStyle())return;await api('activate',{style_id:selectedStyle,version:Number(b.dataset.activate)});notify('Published release activated.');await refresh();}));
    }
    if(page==='learning') {
      const flow=overview.improvements||{batches:[],candidates:[],implementation_requests:[]};
      const visible=x=>!improvementStyle||x.style_id===improvementStyle;
      const batches=flow.batches.filter(visible), cs=flow.candidates.filter(visible), updates=flow.implementation_requests.filter(visible);
      const feedbackTitles={'missing node':'Missing joining point','false node':'Incorrect joining point','missing leader':'Missing leading line','missing pipe':'Missing pipe','false pipe':'Incorrect pipe detection','wrong binding':'Incorrect label assignment','uncertain':'Assignments to verify','wrong join':'Incorrect pipe connection'};
      const labels={feedback_received:'Feedback received',ready_to_test:'Ready to test',ready_to_publish:'Ready to publish',review_results:'Compare results',needs_more_evidence:'More evidence needed',published:'Published',requires_app_update:'Requires app update',technical_review:'Technical review needed',review_app_update:'Compare app update',verified:'Update verified',needs_expert_answer:'Your answer needed',answer_received:'Answer saved — ready for developer'};
      const scopeText={shared:'Pipes, joining points & leading lines · both methods',labels:'Label reading · both methods',dimension:'Dimension assignments',llm:'LLM assignments',unknown:'Assignment method needs checking',preview:'Preview assignments'};
      w.innerHTML=heading('FROM FEEDBACK TO RESULTS','Improvements','Keep giving feedback on Review drawings. This queue groups your examples and shows the next step. Feedback alone does not change an analysis.',`<button class="btn" id="go-review">← Review drawings</button>`)+
        `<div class="style-steps"><span><b>1</b> Give feedback on a drawing</span><span><b>2</b> Prepare an improvement</span><span><b>3</b> Compare before & after</span><span><b>4</b> Publish or update the app</span></div>`+
        `<section class="panel improvement-filter"><label>Drawing style<select id="improvement-style"><option value="">All styles</option>${overview.styles.map(s=>`<option value="${esc(s.draft.id)}" ${s.draft.id===improvementStyle?'selected':''}>${esc(styleName(s.draft.id))}</option>`).join('')}</select></label><p>Examples are collected across styles. Configuration changes currently publish to one style; broader reuse needs cross-style validation. <b>No rule may depend on one specific drawing.</b></p></section>`+
        `<div class="section-bar"><h2>Feedback waiting for an improvement</h2><span class="muted">${batches.length} groups</span></div>`+
        batches.map(b=>`<section class="panel improvement-card"><div><span class="eyebrow">${esc(styleName(b.style_id))}</span><h3>${esc(feedbackTitles[b.title]||b.title)}</h3><p>${b.count} ${b.count===1?'example':'examples'} · ${esc(scopeText[b.scope]||b.scope)}</p><p class="muted">${['labels','unknown','preview'].includes(b.scope)?'Technical diagnosis is needed before choosing a fix.':'Prepare a proposed fix and determine whether it needs code changes. Uses Astra; API charges apply.'}</p></div><button class="btn primary" data-prepare-improvement="${esc(b.id)}">${['labels','unknown','preview'].includes(b.scope)?'Prepare technical review':'Prepare improvement'}</button></section>`).join('')+
        (!batches.length?'<section class="panel"><p>No unhandled feedback in this view. Corrections from Review drawings appear here automatically. Positive confirmations are retained as checks for future changes.</p></section>':'')+
        `<div class="section-bar"><h2>Test and apply improvements</h2></div>`+
        cs.map(c=>`<section class="panel candidate"><div class="section-bar"><div><span class="eyebrow">${esc(styleName(c.style_id))}</span><h2>${esc(c.title)}</h2></div>${stateBadge(labels[c.workflow_status])}</div><p>${esc(c.rationale)}</p><p>${esc(c.scope_label)}</p><p class="muted">${c.workflow_status==='published'?'This version is published. Existing drawings keep their saved results until you re-analyse them.':c.workflow_status==='ready_to_publish'?'The current checks passed. Publish makes this version available for new analyses.':c.workflow_status==='review_results'?'Open the comparison, inspect the highlighted feedback and confirm the results.':c.workflow_status==='needs_more_evidence'?'Some checks failed, lack evidence or no longer match this candidate. Inspect the report and add corrections or confirmations on other drawings.':'Test the proposed change against saved feedback. Nothing is published yet.'}</p><div class="section-bar">${c.test_binding&&c.workflow_status!=='published'?`<button class="btn" data-evaluate="${esc(c.id)}" data-mode="${esc(c.test_binding)}">${c.workflow_status==='ready_to_test'?'Test improvement':'Run tests again'}${c.test_binding==='astra'?' · LLM / API charges':''}</button>`:''}${c.evaluation?`<button class="btn" data-report="${esc(c.evaluation)}">Compare before & after</button>`:''}${c.workflow_status==='ready_to_publish'?`<button class="btn primary" data-publish-improvement="${esc(c.id)}">Approve & publish</button>`:''}${c.workflow_status==='published'?'<button class="btn" data-return-review>Review updated drawings →</button>':''}</div><details><summary>Technical details</summary><pre>${esc(JSON.stringify({calibration:c.profile.calibration,rules:c.profile.rules},null,2))}</pre></details><div id="report-${esc(c.id)}"></div></section>`).join('')+
        (!cs.length?'<section class="panel"><p>No proposed changes yet. Prepare an improvement above; the application will either create a testable candidate or explain why technical work is needed.</p></section>':'')+
        `<div class="section-bar"><h2>Technical work</h2></div>`+
        updates.map(u=>`<section class="panel improvement-card"><div><span class="eyebrow">${esc(styleName(u.style_id))}</span><h3>${esc(labels[u.status])}</h3><p>${esc(u.reason)}</p><p class="muted">${u.status==='verified'?'The expert confirmed this update.':u.status==='review_app_update'?'An implementation and saved comparison are available below.':u.status==='requires_app_update'?'The proposed fix needs a code change.':'It is not yet clear whether settings are enough. A technical diagnosis is needed.'} Download the brief and attach it to Codex. This does not start a task or update the app automatically. After implementation, tests and saved before/after results are required.</p>${u.developer_review?`<div class="feedback-message app-message"><b>Update</b><p>${esc(u.developer_review.summary)}</p></div>`:''}</div><div>${(u.comparisons||[]).map(pair=>`<p>${esc(pair.sheet)} <button class="btn" data-update-snapshot="${esc(pair.before)}">Before</button> <button class="btn" data-update-snapshot="${esc(pair.after)}">After</button></p>`).join('')}${u.status==='review_app_update'?`<p>${esc(u.validation_summary)}</p><button class="btn primary" data-review-update="${esc(u.id)}" data-accepted="true">Confirm improvement</button> <button class="btn" data-review-update="${esc(u.id)}" data-accepted="false">Needs more work</button>`:''}<button class="btn" data-implementation-brief="${esc(u.id)}">Download brief for Codex</button></div></section>`).join('')+
        (!updates.length?'<section class="panel"><p>No technical handoffs yet.</p></section>':'')+
        `<details class="panel"><summary>Recent processing tasks</summary>${overview.tasks.slice().reverse().map(t=>`<div class="release-row"><b>${esc(t.kind.replaceAll('_',' '))}</b>${stateBadge(t.status)}<span>${esc(t.error||t.progress||'')}</span></div>`).join('')||'<p>No tasks yet.</p>'}</details>`;
      $('#improvement-style').onchange=e=>{improvementStyle=e.target.value;render();};
      $('#go-review').onclick=()=>switchPage('review');
      w.querySelectorAll('[data-return-review]').forEach(b=>b.onclick=()=>{switchPage('review');notify('Choose a drawing and re-analyse it with the published style to see the change.');});
      w.querySelectorAll('[data-prepare-improvement]').forEach(b=>b.onclick=()=>act(async()=>{b.disabled=true;b.dataset.busy='job';try{await job('prepare-improvement',{id:b.dataset.prepareImprovement});}catch(e){b.disabled=false;throw e;}}));
      w.querySelectorAll('[data-implementation-brief]').forEach(b=>b.onclick=()=>act(async()=>download(b.dataset.implementationBrief+'.json',await api('implementation-brief?id='+encodeURIComponent(b.dataset.implementationBrief))),'Preparing the developer brief…'));
      w.querySelectorAll('[data-update-snapshot]').forEach(b=>b.onclick=()=>act(async()=>{await openSnapshot(b.dataset.updateSnapshot);notify('Saved implementation comparison. Return to Improvements to confirm or request more work.');}));
      w.querySelectorAll('[data-review-update]').forEach(b=>b.onclick=()=>act(async()=>{if(!name()){askName();return;}await api('review-implementation',{id:b.dataset.reviewUpdate,accepted:b.dataset.accepted==='true',author:name()});await refresh();}));
      w.querySelectorAll('[data-publish-improvement]').forEach(b=>b.onclick=()=>act(async()=>{if(!name()){askName();return;}await api('publish',{id:b.dataset.publishImprovement,author:name()});notify('Published. Re-analyse drawings to see the effect.');await refresh();}));
      const sources=[...new Map(overview.feedback.filter(f=>f.style_id===selectedStyle&&f.snapshot).map(f=>[f.snapshot,f])).values()];
      const experiments=(overview.experiments||[]);
      const panel=document.createElement('details');panel.className='panel';
      panel.innerHTML=`<summary>Advanced developer experiments</summary><h2>Controlled experiments</h2><p>Compare the original and compact request formats on identical frozen geometry, candidates, batch order and model settings. Preparation is local and free. Saved trials are audit records, never a response cache.</p><label>Saved analysis <select id="experiment-source">${sources.map(f=>`<option value="${esc(f.snapshot)}">${esc(f.sheet)} · ${esc(f.snapshot.slice(0,8))}</option>`).join('')}</select></label><button class="btn admin" id="prepare-experiment" ${sources.length?'':'disabled'}>Prepare format comparison</button>`+
        experiments.map(e=>`<article class="panel"><h3>${esc(e.title)}</h3><p>${esc(e.status)} · ${esc(e.split)} · ${esc(e.model)}</p><p>${e.documents.map(d=>`${esc(d.sheet)}: ${d.chars.baseline.toLocaleString('en-GB')} → ${d.chars.compact.toLocaleString('en-GB')} characters; ${d.calls_per_variant} calls per variant`).join('<br>')}</p><small>Frozen input ${esc(e.input_digest.slice(0,12))} · Engine ${esc(e.engine_version)}</small><p>A paired trial sends drawing geometry, label text and topology to the OpenAI Astra API and incurs charges for both variants. Each repeat makes fresh calls.</p><label class="admin"><input type="checkbox" data-paid-ack="${esc(e.id)}"> I authorize this paid paired trial</label> <button class="btn admin" data-run-experiment="${esc(e.id)}">Run paired Astra trial</button>${e.runs.map(r=>`<button class="btn" data-experiment-report="${esc(e.id)}" data-trial="${esc(r)}">Inspect trial ${esc(r.slice(-8))}</button>`).join('')}<div id="experiment-report-${esc(e.id)}"></div></article>`).join('');
      w.append(panel);
      $('#prepare-experiment').onclick=()=>act(()=>job('experiment-prepare',{snapshots:[$('#experiment-source').value],title:'Original vs compact request format'}));
      w.querySelectorAll('[data-run-experiment]').forEach(b=>b.onclick=()=>act(async()=>{const ack=w.querySelector(`[data-paid-ack="${b.dataset.runExperiment}"]`);if(!ack.checked)throw new Error('Acknowledge the API data transfer and charges before starting.');b.disabled=true;try{await job('experiment-run',{id:b.dataset.runExperiment,paid_run_acknowledged:true});}finally{b.disabled=false;}}));
      w.querySelectorAll('[data-experiment-report]').forEach(b=>b.onclick=()=>act(()=>showExperiment(b.dataset.experimentReport,b.dataset.trial)));
      w.querySelectorAll('[data-evaluate]').forEach(b=>b.onclick=()=>act(()=>job('evaluate',{id:b.dataset.evaluate,binding:b.dataset.mode})));
      w.querySelectorAll('[data-report]').forEach(b=>b.onclick=()=>act(()=>showReport(b.dataset.report)));
    }
    if(page==='service') {
      w.innerHTML=heading('SHARED ANALYSIS SERVICE','From a PDF to structured pipe data.','The application consumes the same engine that Studio evaluates. Only published profiles are available to production.')+
        `<div class="two-columns"><section class="panel"><span class="badge">API v2</span><h2>Submit a vector PDF</h2><pre>POST /v2/analyses?style=style-1\nX-API-Key: YOUR_API_KEY\nContent-Type: application/pdf\n\n&lt;PDF bytes&gt;</pre><p>Response: <b>202 Accepted</b>, analysis_id and status_url. Poll the status URL, then fetch /v2/analyses/{id}/result.</p><p>Use <b>style=auto</b> for vector-signature matching. An unknown style returns an explicit job error for calibration rather than an invented match.</p><p><b>assignmentMethod</b> is required: <b>llm</b> (Astra) or <b>dimension</b> (flow direction from the label dimensions, one pipe between joining points; no model is called). No default and no fallback between the two. Example: <code>?style=style-1&amp;assignmentMethod=dimension</code>.</p><h3>Local example</h3><pre>curl -X POST \\\n  'http://localhost:5005/v2/analyses?style=style-1' \\\n  -H 'X-API-Key: YOUR_API_KEY' \\\n  -H 'Content-Type: application/pdf' \\\n  --data-binary @drawing.pdf</pre></section><section class="panel"><h2>The result contract</h2><ul class="feature-list"><li>Pipe stretch geometry with one label or null</li><li>Joining points with types and connectivity</li><li>Leading lines and detected labels</li><li>OCR text, parsed designations and graphic notation</li><li>Final Astra assignments and unresolved cases</li><li>Source hash, style release and engine version</li></ul><p>Coordinates are PDF points, origin at the top left; y increases downward. One assignment unit is a stretch, not a whole main-and-branches group.</p><h3>Release discipline</h3><p>The service reads active published style packages. Drafts and expert text corrections never become hidden production overrides. Deploy the shared engine with the tested release data.</p><p class="muted">The legacy /predict contract remains available for existing callers. Integrate /v2/analyses to use the Studio engine.</p></section></div>`;
    }
    $('#workbench-style')?.addEventListener('change',e=>{if(page==='styles'&&!leaveStyle()){e.target.value=selectedStyle;return;}selectedStyle=e.target.value;render();});
  }
  async function showExperiment(id,trial){
    const r=await api(`experiment-report?id=${encodeURIComponent(id)}&trial=${encodeURIComponent(trial)}`),host=$('#experiment-report-'+id);
    host.innerHTML=`<h4>${esc(r.status)}</h4><p>${esc(r.note)}</p><p>${Object.entries(r.counts).map(([k,v])=>`${esc(k)}: ${v}`).join(' · ')}</p><p>${Object.entries(r.usage).map(([k,u])=>`${esc(k)}: ${esc(usageText(u))}`).join('<br>')}</p><p>${r.assignment_changes.length} changed assignments · ${r.errors.length} request errors</p><table class="data-table"><thead><tr><th>Drawing / feedback</th><th>Baseline → compact</th><th>Inspect</th></tr></thead><tbody>${r.cases.map(c=>`<tr><td>${esc(c.sheet)}<br>${esc(c.feedback_id)}</td><td>${esc(c.baseline)} → ${esc(c.compact)} · ${esc(c.outcome)}</td><td>${['baseline','compact'].map(v=>`<button class="text-btn" data-experiment-snapshot="${esc(c.snapshot)}" data-variant="${v}">${v}</button>`).join(' / ')}</td></tr>`).join('')}</tbody></table><details><summary>All changed assignments</summary><pre>${esc(JSON.stringify(r.assignment_changes,null,2))}</pre></details>`;
    host.querySelectorAll('[data-experiment-snapshot]').forEach(b=>b.onclick=()=>act(async()=>{const sid=b.dataset.experimentSnapshot,rv=await api(`experiment-result?id=${encodeURIComponent(id)}&trial=${encodeURIComponent(trial)}&snapshot=${encodeURIComponent(sid)}&variant=${b.dataset.variant}`);switchPage('review');window.PipeReview.showResult(rv,`/api/studio/snapshot-bg?id=${encodeURIComponent(sid)}`);notify('Read-only experiment result.');}));
  }
  async function showReport(id) {
    const r=await api('evaluation?id='+encodeURIComponent(id)),host=$('#report-'+r.candidate_id);
    host.innerHTML=`<div class="evaluation-summary"><p class="badge">Evaluation: ${esc(resultName({binding_mode:r.binding}))}</p><h3>${r.eligible?'Ready for expert publication approval':'More evidence or changes needed'}</h3><p>${esc(r.gate_note)}</p><p><b>${r.documents}</b> independent documents · <b>${r.holdout_cases}</b> held-out checks</p><div class="badge-row">${Object.entries(r.counts).map(([k,n])=>stateBadge(k+' '+n)).join('')}</div></div><table class="data-table"><thead><tr><th>Drawing</th><th>Set</th><th>Before → after</th><th>Inspect</th></tr></thead><tbody>${r.cases.map(c=>`<tr><td>${esc(c.sheet)}</td><td>${c.holdout?'Held out':'Training'}</td><td>${esc(c.before)} → ${esc(c.after)} ${stateBadge(c.outcome)}${c.outcome==='manual'?`<div class="manual-assessment" data-case="${esc(c.feedback_id)}"><select aria-label="Before meets feedback"><option value="">Before…</option><option value="true">Correct</option><option value="false">Incorrect</option></select><select aria-label="After meets feedback"><option value="">After…</option><option value="true">Correct</option><option value="false">Incorrect</option></select><button class="btn" data-assess="${esc(c.feedback_id)}">Save expert assessment</button></div>`:''}</td><td><button class="text-btn" data-diff="${esc(c.snapshot)}" data-side="before">Before</button> / <button class="text-btn" data-diff="${esc(c.snapshot)}" data-side="after">After</button></td></tr>`).join('')}</tbody></table><button class="btn primary admin" id="publish-candidate" ${r.eligible?'':'disabled'}>Approve & publish tested rule</button>`;
    host.querySelectorAll('[data-diff]').forEach(b=>b.onclick=()=>act(async()=>{const rv=await api(`evaluation-result?id=${encodeURIComponent(id)}&snapshot=${encodeURIComponent(b.dataset.diff)}&side=${b.dataset.side}`);switchPage('review');window.PipeReview.showResult(rv,`/api/studio/snapshot-bg?id=${encodeURIComponent(b.dataset.diff)}`);comparisonReturn=id;const banner=document.createElement('div');banner.id='comparison-return';banner.className='comparison-banner';banner.innerHTML=`<b>${b.dataset.side==='before'?'BEFORE':'AFTER'} · saved test result</b><span>Inspect the drawing, then return to assess the improvement.</span><button class="btn" id="back-to-improvement">← Back to comparison</button>`;$('#comparison-return')?.remove();$('#review-workspace').prepend(banner);$('#back-to-improvement').onclick=()=>act(async()=>{switchPage('learning');await refresh();await showReport(comparisonReturn);banner.remove();});notify('Read-only test result.');}));
    host.querySelectorAll('[data-assess]').forEach(b=>b.onclick=()=>act(async()=>{const selects=b.parentElement.querySelectorAll('select');if([...selects].some(s=>!s.value))throw new Error('Inspect Before and After, then assess both results.');await api('review-case',{evaluation:id,feedback_id:b.dataset.assess,before:selects[0].value==='true',after:selects[1].value==='true',author:name()});await showReport(id);}));
    $('#publish-candidate').onclick=()=>act(async()=>{if(!name()){askName();return;}await api('publish',{id:r.candidate_id,author:name()});notify('Style release published.');await refresh();});
  }
  async function openSnapshot(id) {
    setBusy(true,'Opening the saved drawing…');
    try{ return await openSnapshotInner(id); } finally { setBusy(false); }
  }
  async function openSnapshotInner(id) {const rv=await api('snapshot?id='+encodeURIComponent(id));switchPage('review');window.PipeReview.showResult(rv,'/api/studio/snapshot-bg?id='+encodeURIComponent(id));notify('Saved analysis · read-only. Historical geometry is preserved.');}
  function downloadText(filename,text,type){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function download(filename,data){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function queue(){const s=window.PipeReview?.state();if(!s?.sheet||s.readonly)return;const rows=await api('queue?sheet='+encodeURIComponent(s.sheet));const host=$('#review-queue');host.innerHTML=rows.map((r,i)=>`<button class="queue-item" data-queue="${i}"><span>${r.reason==='sample'?'VERIFY SAMPLE':'NEEDS A LOOK'}</span><b>Pipe ${r.stretch_id}</b><small>${r.label_id===null?'No assignment':'Label '+r.label_id} ↗</small></button>`).join('')||'<p class="muted">No candidates in this queue. Review the drawing freely.</p>';host.querySelectorAll('[data-queue]').forEach(b=>b.onclick=()=>{host.querySelectorAll('[data-queue]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b));});window.PipeReview.focus(rows[Number(b.dataset.queue)].point,'bindings',rows[Number(b.dataset.queue)].stretch_id);});}
  function askName(){ $('#reviewer-name').value=name();if(!$('#name-dialog').open)$('#name-dialog').showModal(); }
  $('#name-form').onsubmit=e=>{e.preventDefault();try{localStorage.setItem('author',$('#reviewer-name').value.trim());}catch{}$('#who').textContent=name()||'Reviewer';$('#name-dialog').close();};
  $('#cancel-feedback').onclick=()=>{feedbackResolve?.(null);feedbackResolve=null;$('#feedback-dialog').close();};
  $('#feedback-dialog').addEventListener('cancel',()=>{feedbackResolve?.(null);feedbackResolve=null;});
  $('#feedback-form').onsubmit=e=>{e.preventDefault();const rec={note:$('#feedback-note').value};if(!$('#expected-label-wrap').hidden){const v=$('#expected-label').value;const pair=v==='none'?[null,null]:v.split(':').map(Number);rec.label_id=pair[0];rec.designation_idx=pair[1];}if(!$('#expected-text-wrap').hidden)rec.text=$('#expected-text').value;if(!$('#expected-kind-wrap').hidden)rec.expected_kind=$('#expected-kind').value;feedbackResolve?.(rec);feedbackResolve=null;$('#feedback-dialog').close();};
  async function editFeedback(rec, rv){
    $('#feedback-title').textContent=rec.type.replaceAll('_',' ');$('#expected-label-wrap').hidden=rec.type!=='wrong_binding';$('#expected-text-wrap').hidden=rec.type!=='label_text';$('#expected-kind-wrap').hidden=!['node_type','missing_node'].includes(rec.type);
    $('#expected-label').required=rec.type==='wrong_binding';$('#expected-label').disabled=rec.type!=='wrong_binding';
    const current=rv.bindings?.find(b=>b.stretch===rec.stretch_id);
    const c=window.AssignmentContext.context(rv.metadata,rec.tab);
    $('#feedback-scope').dataset.scope=c.scope;
    $('#feedback-scope').innerHTML=`<span class="eyebrow">SAVING FEEDBACK FOR</span><strong>${esc(c.title)}</strong><p>${esc(c.detail)}</p>`;
    $('#feedback-selection').textContent=rec.stretch_id!==undefined?`Selected pipe ${rec.stretch_id} · Current assignment: ${current?'label '+current.label:'no label'}`:'';
    $('#feedback-note').value=$('#note').value;$('#expected-text').value=rv.labels.find(l=>l.id===rec.label_id)?.text||'';
    $('#expected-label').innerHTML='<option value="" selected disabled>Choose the expected label…</option><option value="none">No label — leave unassigned</option>'+rv.labels.flatMap(l=>l.designations.map((d,i)=>`<option value="${l.id}:${i}">${l.id} · ${esc(d.raw)}${l.level?' · '+esc(l.level.raw):''}</option>`)).join('');
    $('#feedback-dialog').showModal();return new Promise(resolve=>feedbackResolve=resolve);
  }
  // Native disclosure menus stay keyboard accessible and dismiss predictably.
  document.querySelectorAll('.options-menu').forEach(menu=>{
    menu.addEventListener('toggle',()=>{if(menu.open)document.querySelectorAll('.options-menu').forEach(other=>{if(other!==menu)other.open=false;});});
  });
  document.addEventListener('pointerdown',event=>document.querySelectorAll('.options-menu[open]').forEach(menu=>{if(!menu.contains(event.target))menu.open=false;}));
  document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.options-menu[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary').focus();});});
  document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{if(['learning','redeploy'].includes(b.dataset.page)){advancedLearning=false;feedbackDrawing='';}switchPage(b.dataset.page);if(b.dataset.page==='review'&&window.PipeReview?.state()?.readonly)act(()=>window.PipeReview.reload(true));});
  $('#refresh-queue').onclick=()=>act(queue);
  window.Studio={api,act,notify,refresh,queue,job,usageText,busy:setBusy,busyMessage,styleBadge:renderStyleBadge,renderAssignmentUsage,renderMethodContext,ensureDimension,scopeName,askName,editFeedback,style:()=>reviewStyle,workbenchStyle:()=>selectedStyle,name,mode,
    uploaded:sheet=>{uploadedDrawing=sheet;},
    loaded:rv=>{if(!window.PipeReview.state().readonly){document.body.classList.remove('checking-correction');$('#comparison-return')?.remove();}const meta=rv.metadata||{};$('#canvas-empty').hidden=true;renderStyleBadge(rv);renderMethodContext();act(queue);ensureDimension();$('#open-drawings').textContent=window.PipeReview.state().sheet+' ▾';if(uploadedDrawing===window.PipeReview.state().sheet&&!window.PipeReview.state().readonly){uploadedDrawing=null;openDrawingStyle();}},
    saveFeedback:async(sheet,rv,rec)=>{if(!name()){askName();throw new Error('Enter your reviewer name, then save the example.');}const result=await api('feedback',{sheet,run_id:rv.metadata?.run_id,record:{...rec,author:name()}});await refresh();updateFeedbackButton();return result;}
  };
  const progressButton=document.createElement('button');progressButton.id='review-improvements';progressButton.className='btn';progressButton.textContent='See improvements →';$('#review-result-controls').append(progressButton);progressButton.onclick=openMyFeedback;
  if(typeof MutationObserver!=='undefined'){
    const updateSelection=()=>{const text=$('#info').textContent||'',empty=/^(Select |Saved analysis|nothing here)/i.test(text),object=text.match(/^(STRETCH|NODE|LABEL|LEADER|PATH|SELECTED PIPE)\s+(\d+)/);$('#selection-summary').textContent=empty?'Select an item on the drawing':object?({STRETCH:'Pipe',NODE:'Joining point',LABEL:'Label',LEADER:'Leading line',PATH:'Line','SELECTED PIPE':'Pipe'}[object[1]]+' '+object[2]):'Selected item';document.querySelectorAll('.confirm-row button').forEach(b=>b.disabled=empty||!!window.PipeReview?.state()?.readonly);};
    new MutationObserver(updateSelection).observe($('#info'),{childList:true,characterData:true,subtree:true});updateSelection();
  }
  act(refresh,'Loading your feedback…');
  try{const active=JSON.parse(localStorage.getItem("studio-active-job"));if(active?.j)watchJob(active.j,active.body);}catch{}
  document.querySelectorAll('[data-assignment-mode]').forEach(button=>{
    button.onclick=()=>selectAssignmentMode(button.dataset.assignmentMode);
    button.onkeydown=event=>{
      if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
      event.preventDefault();
      const value=event.key==='Home'?'flow':event.key==='End'?'astra':button.dataset.assignmentMode==='flow'?'astra':'flow';
      const target=document.querySelector(`[data-assignment-mode="${value}"]`);
      if(!target.disabled){selectAssignmentMode(value);target.focus();}
    };
  });
  renderAssignmentUsage();
})();
