const state={csrf:'',view:'home',conversations:[],projects:[],currentThread:null,lastGoal:'',pendingInstruction:null,busy:false,currentMode:'chat',activeBuildStage:null};
const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const api=async(path,options={})=>{
  options.headers={'Content-Type':'application/json',...(options.headers||{})};
  if(state.csrf)options.headers['X-CSRF-Token']=state.csrf;
  const r=await fetch(path,options);let data={};try{data=await r.json();}catch{}
  if(!r.ok)throw new Error(data.error||'request_failed');return data;
};
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmt(v){if(!v)return '—';try{return new Date(v).toLocaleString('ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});}catch{return v;}}
function storageGet(key,fallback=''){try{const v=localStorage.getItem(key);return v===null?fallback:v;}catch{return fallback;}}
function storageSet(key,value){try{localStorage.setItem(key,value);}catch{}}
function storageRemove(key){try{localStorage.removeItem(key);}catch{}}
function draftKey(){return 'aivy-draft:'+(state.currentThread?.thread_id||'new');}
function saveDraft(){
  const prompt=$('#prompt');if(!prompt)return;
  storageSet(draftKey(),prompt.value||'');
  const status=$('#draftStatus');if(status)status.textContent=prompt.value?'保存済み':'下書き保存';
}
function restoreDraft(){
  const prompt=$('#prompt');if(!prompt)return;
  prompt.value=storageGet(draftKey(),'');
  autoGrow();
  const status=$('#draftStatus');if(status)status.textContent=prompt.value?'下書きを復元':'下書き保存';
}
function clearDraft(){
  storageRemove(draftKey());
  const prompt=$('#prompt');if(prompt){prompt.value='';autoGrow();}
  const status=$('#draftStatus');if(status)status.textContent='下書き保存';
}
function toast(text,type='info'){
  const region=$('#toastRegion');if(!region)return;
  const node=document.createElement('div');node.className='toast '+type;node.textContent=text;
  region.append(node);setTimeout(()=>node.remove(),3200);
}
function setTaskProgress(visible,label='',detail='',percent=0){
  const root=$('#taskProgress');if(!root)return;
  root.hidden=!visible;
  if(!visible)return;
  const safe=Math.max(0,Math.min(100,Number(percent)||0));
  $('#taskProgressLabel').textContent=label||'Aivyが作業中';
  $('#taskProgressDetail').textContent=detail||'処理しています…';
  $('#taskProgressPercent').textContent=Math.round(safe)+'%';
  $('#taskProgressBar').style.width=safe+'%';
}
function renderResume(){
  const box=$('#resumeWork');if(!box)return;
  const preferred=storageGet('aivy-last-thread','');
  const thread=state.conversations.find(x=>x.thread_id===preferred)||state.conversations[0]||null;
  const project=(thread?.project_slug?state.projects.find(x=>x.slug===thread.project_slug):null)||state.projects[0]||null;
  if(!thread&&!project){box.hidden=true;return;}
  box.hidden=false;
  const title=thread?.title||project?.name||'前回の続き';
  $('#resumeTitle').textContent=title;
  $('#resumeMeta').textContent=thread?('最終更新 '+fmt(thread.updated_at)+(thread.project_slug?' · 制作物あり':'')):(project?('制作物 '+fmt(project.updated_at)):'');
  const conversationButton=$('#resumeConversation');
  const projectButton=$('#resumeProject');
  conversationButton.hidden=!thread;
  projectButton.hidden=!project;
  conversationButton.onclick=()=>thread&&openConversation(thread.thread_id);
  projectButton.onclick=()=>{if(!project)return;setView('projects');showProject(project.slug);};
}
function openSidebar(){ $('#sidebar').classList.add('open');$('#overlay').classList.add('show');}
function closeSidebar(){ $('#sidebar').classList.remove('open');$('#overlay').classList.remove('show');}
function setView(name){
  state.view=name;
  $$('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+name));
  document.querySelectorAll('.nav-item[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
  document.querySelectorAll('[data-mobile-view]').forEach(b=>b.classList.toggle('active',b.dataset.mobileView===name));
  const titles={home:state.currentThread?.title||'新しいチャット',conversations:'最近の会話',projects:'制作物',missions:'ミッション',lab:'IVY LAB',downloads:'ダウンロード',settings:'設定'};
  $('#topbarTitle').textContent=titles[name]||'Aivy';
  closeSidebar();
  if(name==='conversations')loadConversations();
  if(name==='projects')loadProjects();
  if(name==='missions')loadMissions();
  if(name==='lab')loadGrowthLab();
  if(name==='downloads')loadDownloads();
  if(name==='settings'){loadModelRoutes();loadEvolutionSummary();loadKnowledgeSummary();loadLearningSummary();loadSquadSummary();loadHealthSummary();loadBenchmarkSummary();}
}
function message(role,text){
  $('#welcome').hidden=true;
  const wrap=document.createElement('div');wrap.className='message '+role;
  const bubble=document.createElement('div');bubble.className='bubble';bubble.textContent=text;
  wrap.append(bubble);
  if(role==='assistant'){
    const actions=document.createElement('div');actions.className='message-actions';
    const copy=document.createElement('button');copy.type='button';copy.textContent='コピー';
    copy.onclick=async()=>{
      try{await navigator.clipboard.writeText(String(text||''));copy.textContent='コピー済み';setTimeout(()=>copy.textContent='コピー',1200);}
      catch{copy.textContent='コピー失敗';setTimeout(()=>copy.textContent='コピー',1200);}
    };
    actions.append(copy);wrap.append(actions);
  }
  $('#messages').append(wrap);wrap.scrollIntoView({behavior:'smooth',block:'end'});
}
function showThinking(){
  removeThinking();
  $('#welcome').hidden=true;
  const wrap=document.createElement('div');wrap.className='message assistant thinking';wrap.id='aivyThinking';
  const bubble=document.createElement('div');bubble.className='bubble';
  bubble.innerHTML='<span>Aivyが考えています</span><i></i><i></i><i></i>';
  wrap.append(bubble);$('#messages').append(wrap);wrap.scrollIntoView({behavior:'smooth',block:'end'});
}
function removeThinking(){const row=$('#aivyThinking');if(row)row.remove();}
function renderRecent(){
  $('#recentChats').innerHTML=state.conversations.slice(0,8).map(x=>`<button class="recent-item" data-thread="${esc(x.thread_id)}">${x.pinned?'★ ':''}${esc(x.title)}</button>`).join('')||'<div class="empty">まだ会話はありません。</div>';
  $$('#recentChats [data-thread]').forEach(b=>b.onclick=()=>openConversation(b.dataset.thread));
}
async function loadConversations(query=''){
  const data=await api('/api/v1/conversations'+(query?'?q='+encodeURIComponent(query):''));
  state.conversations=data.conversations||[];renderRecent();renderResume();
  $('#conversationGrid').innerHTML=state.conversations.map(x=>`
    <article class="data-card" data-thread="${esc(x.thread_id)}">
      <h3>${x.pinned?'★ ':''}${esc(x.title)}</h3>
      <div class="meta"><span>${x.project_slug?'アプリ: '+esc(x.project_slug):'会話のみ'}</span><span>${x.message_count} messages</span><span>${fmt(x.updated_at)}</span></div>
    </article>`).join('')||'<div class="empty">該当する会話はありません。</div>';
  $$('#conversationGrid [data-thread]').forEach(c=>c.onclick=()=>openConversation(c.dataset.thread));
}
async function openConversation(id){
  saveDraft();
  const row=state.conversations.find(x=>x.thread_id===id)||{thread_id:id,title:'会話'};
  state.currentThread=row;storageSet('aivy-last-thread',id);$('#messages').innerHTML='';$('#welcome').hidden=true;
  const data=await api('/api/v1/conversations/'+encodeURIComponent(id)+'/messages');
  (data.messages||[]).forEach(x=>message(x.role,x.content));
  setView('home');$('#topbarTitle').textContent=row.title;restoreDraft();
}
async function loadMissions(){
  const projectSelect=$('#missionProject');
  const strategicSelect=$('#strategicProject');
  try{
    if(!state.projects.length){
      const p=await api('/api/v1/projects');state.projects=p.projects||[];
    }
    const options=state.projects.map(row=>`<option value="${esc(row.slug)}">${esc(row.name||row.slug)}</option>`).join('')||'<option value="">作成済みアプリがありません</option>';
    if(projectSelect)projectSelect.innerHTML=options;
    if(strategicSelect)strategicSelect.innerHTML=options;

    const [data,strategic]=await Promise.all([
      api('/api/v1/missions'),
      api('/api/v1/strategic-goals')
    ]);
    const rows=data.missions||[];
    const goals=strategic.goals||[];

    $('#strategicGoalGrid').innerHTML=goals.map(g=>{
      const terminal=['completed','cancelled'].includes(g.status);
      const active=g.status==='active';
      const waiting=Boolean(g.current_mission_id);
      return `<article class="strategic-goal-row">
        <div class="strategic-goal-row-head">
          <div><span class="chip">${esc(g.status)}</span><h4>${esc(g.objective)}</h4></div>
          <span class="chip">${esc(g.project_slug)}</span>
        </div>
        <p>${esc(g.last_decision||'')}</p>
        <div class="strategic-goal-meta">
          <span class="chip">Mission ${g.missions_created||0}/${g.max_auto_missions||12}</span>
          <span class="chip">${waiting?'Mission待機中':'次Mission作成可能'}</span>
          <span class="chip">${fmt(g.updated_at)}</span>
        </div>
        <div class="strategic-goal-actions">
          ${!terminal&&active?`<button data-goal-action="pause" data-id="${esc(g.goal_id)}">一時停止</button>`:''}
          ${!terminal&&!active?`<button data-goal-action="resume" data-id="${esc(g.goal_id)}">再開</button>`:''}
          ${!terminal?`<button data-goal-action="cancel" data-id="${esc(g.goal_id)}">終了</button>`:''}
        </div>
      </article>`;
    }).join('')||'<div class="empty">長期目標はまだありません。</div>';

    document.querySelectorAll('[data-goal-action]').forEach(b=>b.onclick=()=>updateStrategicGoal(b.dataset.id,b.dataset.goalAction));

    $('#missionGrid').innerHTML=rows.map(m=>{
      const terminal=['completed','failed','cancelled'].includes(m.status);
      const canRun=!terminal&&m.status!=='running';
      const approve=m.status==='approval_required';
      return `<article class="mission-card">
        <div class="mission-head"><div><span class="chip">${esc(m.status)}</span><strong>${esc(m.project_slug)}</strong></div><span>cycle ${m.cycle}/${m.max_cycles}</span></div>
        <h3>${esc(m.goal)}</h3>
        <p>${esc(m.message||'')}</p>
        <div class="meta"><span>phase: ${esc(m.phase)}</span><span>${fmt(m.updated_at)}</span><span>evidence ${(m.evidence_refs||[]).length}</span></div>${(((m.plan||{}).squad||{}).roles||[]).length?`<p class="mission-team">Team: ${(((m.plan||{}).squad||{}).roles||[]).map(esc).join(' / ')}</p>`:''}${((((m.plan||{}).task_graph||{}).waves||[]).length)?`<p class="mission-team">Task Waves: ${(((m.plan||{}).task_graph||{}).waves||[]).map((w,i)=>'W'+(i+1)+'['+w.join(', ')+']').join(' → ')}</p>`:''}
        <div class="mission-actions">
          ${canRun?`<button class="route-save mission-run" data-id="${esc(m.mission_id)}" data-approved="${approve?'true':'false'}">${approve?'承認して続行':'安全確認を続行'}</button>`:''}
          ${!terminal&&m.status!=='running'? `<button class="agent-action secondary mission-pause" data-id="${esc(m.mission_id)}">一時停止</button>`:''}
          ${!terminal&&m.status!=='running'? `<button class="agent-action secondary mission-cancel" data-id="${esc(m.mission_id)}">終了</button>`:''}
        </div>
      </article>`;
    }).join('')||'<div class="empty">まだミッションはありません。</div>';

    document.querySelectorAll('.mission-run').forEach(b=>b.onclick=()=>runMission(b.dataset.id,b.dataset.approved==='true'));
    document.querySelectorAll('.mission-pause').forEach(b=>b.onclick=()=>pauseMission(b.dataset.id));
    document.querySelectorAll('.mission-cancel').forEach(b=>b.onclick=()=>cancelMission(b.dataset.id));

    if(rows.some(m=>m.status==='running')&&state.view==='missions'){
      setTimeout(()=>{if(state.view==='missions')loadMissions();},1800);
    }
  }catch(e){
    $('#missionGrid').innerHTML='<div class="empty">Mission Controlを読み込めませんでした: '+esc(e.message)+'</div>';
    if($('#strategicGoalGrid'))$('#strategicGoalGrid').innerHTML='<div class="empty">長期目標を読み込めませんでした。</div>';
  }
}
async function createStrategicGoal(){
  const slug=$('#strategicProject')?.value||'';
  const objective=$('#strategicObjective')?.value.trim()||'';
  if(!slug||!objective){
    toast('対象アプリと長期目標を入力してください。','info');
    return;
  }
  const button=$('#createStrategicGoal');button.disabled=true;button.textContent='登録中…';
  try{
    await api('/api/v1/strategic-goals',{
      method:'POST',
      body:JSON.stringify({project_slug:slug,objective,max_auto_missions:12})
    });
    $('#strategicObjective').value='';
    toast('長期目標を登録しました。Daily Evolutionが次Missionを考えます。','success');
    await loadMissions();
  }catch(e){
    toast('長期目標を登録できませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='長期目標を登録';}
}
async function runStrategicGoal(){
  const button=$('#runStrategicGoal');if(!button)return;
  button.disabled=true;button.textContent='考え中…';
  try{
    const data=await api('/api/v1/strategic-goals/run',{method:'POST',body:'{}'});
    const mission=data.mission||{};
    toast(data.mission_created
      ? '次のMissionを作成しました。Build前で承認停止します。'
      : '長期目標を確認しました: '+(data.status||'確認済み'),
      data.mission_created?'success':'info');
    await loadMissions();
  }catch(e){
    toast('次のMissionを作れませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='次のMissionを考える';}
}
async function updateStrategicGoal(id,action){
  try{
    await api('/api/v1/strategic-goals/'+encodeURIComponent(id)+'/'+encodeURIComponent(action),{method:'POST',body:'{}'});
    await loadMissions();
  }catch(e){
    toast('長期目標を更新できませんでした: '+e.message,'error');
  }
}
async function createMission(){
  const slug=$('#missionProject')?.value||'';
  const goal=$('#missionGoal')?.value.trim()||'';
  if(!slug||!goal)return;
  const button=$('#createMission');button.disabled=true;button.textContent='作成中…';
  try{
    await api('/api/v1/missions',{method:'POST',body:JSON.stringify({project_slug:slug,goal})});
    $('#missionGoal').value='';
    await loadMissions();
  }catch(e){alert('ミッションを作成できませんでした: '+e.message);}
  finally{button.disabled=false;button.textContent='ミッションを作成';}
}
async function runMission(id,approved){
  try{
    await api('/api/v1/missions/'+encodeURIComponent(id)+'/run',{
      method:'POST',
      body:JSON.stringify({approved_build:approved})
    });
    await loadMissions();
  }catch(e){alert('ミッションを続行できませんでした: '+e.message);}
}
async function pauseMission(id){
  try{
    await api('/api/v1/missions/'+encodeURIComponent(id)+'/pause',{method:'POST',body:'{}'});
    await loadMissions();
  }catch(e){alert('一時停止できませんでした: '+e.message);}
}
async function cancelMission(id){
  try{
    await api('/api/v1/missions/'+encodeURIComponent(id)+'/cancel',{method:'POST',body:'{}'});
    await loadMissions();
  }catch(e){alert('終了できませんでした: '+e.message);}
}

async function loadProjects(){
  const data=await api('/api/v1/projects');state.projects=data.projects||[];renderResume();
  $('#projectGrid').innerHTML=state.projects.map(x=>`
   <article class="project-card" data-slug="${esc(x.slug)}">
    <div class="project-top"><div><h3>${esc(x.name)}</h3><div class="meta"><span class="chip">${esc(x.app_type)}</span>${(x.targets||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join('')}</div></div><strong class="${x.quality==='PASS'?'quality-pass':'quality-blocked'}">${esc(x.quality)}</strong></div>
    <div class="meta" style="margin-top:14px"><span>${esc(x.status)}</span><span>${fmt(x.updated_at)}</span><span>${x.artifact_count} artifacts</span>${x.evaluation_score!=null?`<span>AI評価 ${x.evaluation_score}/100</span>`:''}</div>
   </article>`).join('')||'<div class="empty">まだアプリはありません。</div>';
  $$('#projectGrid [data-slug]').forEach(c=>c.onclick=()=>showProject(c.dataset.slug));
}
async function showProject(slug){
  const data=await api('/api/v1/projects/'+encodeURIComponent(slug));
  const card=data.card||{};const readiness=data.readiness||{};const gaps=(data.gaps||{}).items||[];const evaluation=data.evaluation||{};const release=data.release_manager||{};const visual=data.visual_design||{};const certificate=data.development_certificate||{};const integrity=data.certificate_integrity||{};const latestRun=data.latest_build_trace||(data.agent_runs||[])[0]||null;
  const guardians=data.guardians||{};const projectMemory=data.project_memory||[];
  const visualBlock=visual.status==='reviewed'
    ? `<div class="visual-review-card"><div class="visual-review-head"><strong>Vision Design</strong><span>${visual.score}/100</span></div><p>${esc(visual.summary||'')}</p><div class="visual-shots">
        ${['mobile.png','tablet.png','desktop.png'].map(name=>`<figure><img src="/api/v1/projects/${encodeURIComponent(slug)}/screenshots/${name}" alt="${name} screenshot"><figcaption>${name.replace('.png','')}</figcaption></figure>`).join('')}
      </div>${(visual.findings||[]).length?`<div class="visual-findings"><strong>指摘</strong><p>${(visual.findings||[]).map(esc).join('<br>')}</p></div>`:''}</div>`
    : `<div class="plan-step"><div class="step-no">◉</div><div><strong>Vision Design</strong><p>${esc(visual.summary||'スクリーンショット評価はまだありません')}</p></div></div>`;
  const traceBlock=latestRun
    ? `<div class="execution-trace"><div class="execution-trace-head"><strong>最新Aivy Execution Trace</strong><span>${esc(latestRun.status||'')}</span></div>${(latestRun.steps||[]).map(x=>`<div class="trace-row ${esc(x.status||'')}"><b>${esc(x.step_id||x.action||'step')}</b><span>${esc(x.status||'')}</span><p>${esc(x.summary||'')}</p></div>`).join('')}</div>`
    : '<div class="plan-step"><div class="step-no">◎</div><div><strong>Execution Trace</strong><p>まだBuild実行履歴はありません。</p></div></div>';
  const regression=guardians.regression||{};const requirements=guardians.requirements||{};const dependencies=guardians.dependencies||{};const accessibility=guardians.accessibility||{};const performance=guardians.performance||{};
  const guardianBlock=`<div class="data-card"><h3>Aivy Guardians</h3>
    <div class="meta"><span>Regression: ${esc(regression.status||'未実行')}</span><span>Requirements: ${esc(requirements.status||'未実行')}</span><span>Dependencies: ${esc(dependencies.status||'未実行')}</span><span>Accessibility: ${esc(accessibility.status||'未実行')}</span><span>Performance: ${esc(performance.status||'未実行')}</span></div>
    ${(regression.critical_regressions||[]).length?`<p class="certificate-blockers">Regression: ${regression.critical_regressions.map(esc).join(' / ')}</p>`:''}
    ${(dependencies.findings||[]).length?`<p>Dependency: ${dependencies.findings.slice(0,4).map(f=>esc(f.dependency||'')+' · '+esc(f.reason||'')).join('<br>')}</p>`:''}
    ${(accessibility.issues||[]).length?`<p>Accessibility: ${accessibility.issues.slice(0,4).map(f=>esc(f.rule||'')+' · '+esc(f.detail||'')).join('<br>')}</p>`:''}
    ${performance.source_bytes!=null?`<p>Performance: source ${Math.round((performance.source_bytes||0)/1024)} KB · assets ${performance.asset_count||0}</p>`:''}
    <p>Project Memory: ${projectMemory.length} verified item(s)</p>
  </div>`;
  const certificateBlock=certificate.status
    ? `<div class="certificate-card ${esc(certificate.status)}"><div class="certificate-head"><strong>Aivy Development Certificate</strong><span>${esc(certificate.status)}</span></div><p>Integrity: ${integrity.valid?'VERIFIED':'NG'} · Preflight: ${certificate.preflight_verified===true?'VERIFIED':certificate.preflight_verified===false?'NG':'N/A'} · Postflight: ${certificate.postflight_verified===true?'VERIFIED':certificate.postflight_verified===false?'NG':'N/A'} · Tests: ${certificate.tests_passed?'PASS':'NG'} · Design: ${certificate.design_passed?'PASS':'NG'} · Security: ${certificate.security_passed?'PASS':'NG'} · Trace: ${certificate.execution_trace_verified?'VERIFIED':'NG'}</p><p>Evidence: ${(certificate.evidence||[]).length}件 · 外部公開: ${esc(certificate.external_actions||'approval_required')}</p>${(certificate.blockers||[]).length?`<p class="certificate-blockers">${(certificate.blockers||[]).map(esc).join('<br>')}</p>`:''}${(!integrity.valid&&(integrity.missing||[]).length)?`<p class="certificate-blockers">Missing: ${(integrity.missing||[]).map(esc).join('<br>')}</p>`:''}${(!integrity.valid&&(integrity.mismatched||[]).length)?`<p class="certificate-blockers">Changed: ${(integrity.mismatched||[]).map(esc).join('<br>')}</p>`:''}</div>`
    : '<div class="plan-step"><div class="step-no">◇</div><div><strong>Development Certificate</strong><p>まだ証明書はありません。</p></div></div>';
  $('#agentPlan').innerHTML=`
    <div class="data-card"><h3>${esc(card.name||slug)}</h3><div class="meta"><span>${esc(card.status)}</span><span>${esc(card.quality)}</span>${evaluation.score!=null?`<span>AI評価 ${evaluation.score}/100</span>`:''}</div></div>
    <div class="health-actions"><button class="agent-action secondary" id="runHealthCheck" type="button">Aivy再点検</button><button class="agent-action secondary" id="runParallelSandbox" type="button">並列Sandbox</button><button class="agent-action secondary" id="runExecutionCouncil" type="button">専門AI＋実測</button><button class="agent-action secondary" id="runReleaseGuardian" type="button">公開前チェック</button><span id="healthStatus" class="meta">Tests / Design / Securityを再確認</span></div>
    <div id="executionCouncilResult"></div>
    ${visualBlock}
    ${traceBlock}
    ${certificateBlock}
    ${guardianBlock}
    <div class="plan-step"><div class="step-no">✓</div><div><strong>プレビュー</strong><p>${readiness.preview_ready?'可能':'まだ準備が必要'}</p></div></div>
    <div class="plan-step"><div class="step-no">⇩</div><div><strong>配布状態</strong><p>${(release.targets||[]).length?(release.targets||[]).map(x=>esc(x.target)+': '+esc(x.artifact_status)+' / '+esc(x.distribution_status)).join('<br>'):'Release Manager未実行'}</p></div></div>
    <div class="plan-step"><div class="step-no">!</div><div><strong>未完了</strong><p>${gaps.length?gaps.map(x=>esc(x.reason||'')).join('<br>'):'大きな未完了項目なし'}</p></div></div>`;
  $('#inspector').classList.add('open');
  const healthButton=$('#runHealthCheck');
  if(healthButton)healthButton.onclick=()=>runProjectHealth(slug);
  const parallelButton=$('#runParallelSandbox');
  if(parallelButton)parallelButton.onclick=()=>runParallelSandbox(slug);
  const councilButton=$('#runExecutionCouncil');
  if(councilButton)councilButton.onclick=()=>runProjectExecutionCouncil(slug);
  const releaseButton=$('#runReleaseGuardian');
  if(releaseButton)releaseButton.onclick=()=>runReleaseGuardian(slug);
}
async function runReleaseGuardian(slug){
  const button=$('#runReleaseGuardian');const target=$('#executionCouncilResult');
  if(!button||!target)return;
  button.disabled=true;button.textContent='公開前確認中…';
  try{
    const report=await api('/api/v1/projects/'+encodeURIComponent(slug)+'/release-guardian',{
      method:'POST',body:'{}'
    });
    const blockers=report.blockers||[];const warnings=report.warnings||[];
    target.innerHTML='<div class="council-report"><div class="council-head"><strong>Release Guardian</strong><span>'+esc(report.status||'')+'</span></div>'+
      '<p>Blockers: '+blockers.length+' · Warnings: '+warnings.length+'</p>'+
      (blockers.length?'<p class="certificate-blockers">'+blockers.map(esc).join('<br>')+'</p>':'')+
      (warnings.length?'<p>'+warnings.slice(0,8).map(esc).join('<br>')+'</p>':'')+
      '<p>外部公開・ストア提出は引き続き人の承認が必要です。</p></div>';
  }catch(e){
    target.innerHTML='<div class="council-note error">公開前チェックを完了できませんでした: '+esc(e.message)+'</div>';
  }finally{
    button.disabled=false;button.textContent='公開前チェック';
  }
}
async function runParallelSandbox(slug){
  const button=$('#runParallelSandbox');const target=$('#executionCouncilResult');
  if(!button||!target)return;
  button.disabled=true;button.textContent='隔離並列レビュー中…';
  target.innerHTML='<div class="council-note">専門ワーカーごとの隔離コピーを準備しています…</div>';
  try{
    const report=await api('/api/v1/agent/sandbox/parallel',{
      method:'POST',
      body:JSON.stringify({
        goal:'現在のプロジェクトを複数の専門AIが隔離環境で並列レビューする',
        project_slug:slug
      })
    });
    const workers=report.workers||[];
    target.innerHTML='<div class="council-report"><div class="council-head"><strong>Aivy Parallel Sandbox</strong><span>'+esc(report.status||'')+'</span></div>'+
      '<p>元コード無変更: '+(report.source_unchanged?'VERIFIED':'BLOCKED')+' · workers: '+workers.length+'</p>'+
      workers.map(w=>{
        const s=w.specialist||{};
        return '<details class="council-turn"><summary>'+esc(w.role)+' · '+esc(w.status||'')+'</summary>'+
          '<p>'+esc(s.summary||'')+'</p>'+
          ((s.findings||[]).length?'<p>'+s.findings.slice(0,3).map(esc).join('<br>')+'</p>':'')+
          '</details>';
      }).join('')+'</div>';
  }catch(e){
    target.innerHTML='<div class="council-note">Parallel Sandboxを実行できませんでした: '+esc(e.message)+'</div>';
  }finally{
    button.disabled=false;button.textContent='並列Sandbox';
  }
}
async function runProjectExecutionCouncil(slug){
  const button=$('#runExecutionCouncil');const target=$('#executionCouncilResult');
  if(!button||!target)return;
  button.disabled=true;button.textContent='専門AI＋実測中…';
  target.innerHTML='<div class="council-note">検証済みToolのEvidenceを集めています…</div>';
  try{
    const report=await api('/api/v1/agent/council/execute',{
      method:'POST',
      body:JSON.stringify({
        goal:'現在のプロジェクトを専門AIと検証済みToolで実測レビューする',
        project_slug:slug,
        context:{source:'web-project-execution-council'}
      })
    });
    if(report.status==='not_connected'){
      target.innerHTML='<div class="council-note">AIモデル未接続のため実行Councilは開始していません。</div>';
      return;
    }
    const executed=report.executed_tools||[];
    const delegated=report.delegated_tools||[];
    target.innerHTML='<div class="council-report"><div class="council-head"><strong>Aivy専門AI＋実測</strong><span>'+esc(report.status||'')+'</span></div>'+
      '<p>実行: '+esc(executed.join(', ')||'なし')+'<br>委譲: '+esc(delegated.join(', ')||'なし')+'</p>'+
      (report.turns||[]).map(x=>{
        const r=x.result||{};
        const toolRows=(x.tool_executions||[]).map(t=>esc(t.tool_name)+': '+esc(t.status)).join(' / ');
        return '<details class="council-turn"><summary>'+esc(x.specialist)+' · '+esc(r.summary||'')+'</summary>'+
          (toolRows?'<p>Tool: '+toolRows+'</p>':'')+
          ((r.findings||[]).length?'<p>'+ (r.findings||[]).slice(0,3).map(esc).join('<br>') +'</p>':'')+
          '</details>';
      }).join('')+
      '<div class="council-final"><strong>まとめ</strong><p>'+esc(report.summary||'')+'</p></div></div>';
  }catch(e){
    target.innerHTML='<div class="council-note error">専門AI＋実測を完了できませんでした: '+esc(e.message)+'</div>';
  }finally{
    button.disabled=false;button.textContent='専門AI＋実測';
  }
}
async function runProjectHealth(slug){
  const button=$('#runHealthCheck');const status=$('#healthStatus');
  if(!button||!status)return;
  button.disabled=true;button.textContent='再点検中…';status.textContent='Evidenceを収集中';
  try{
    const report=await api('/api/v1/projects/'+encodeURIComponent(slug)+'/health-check',{
      method:'POST',
      body:JSON.stringify({})
    });
    const icon=report.status==='pass'?'✓':'!';
    status.innerHTML=icon+' Tests '+(report.tests_passed?'PASS':'NG')+' · Design '+(report.design_passed?'PASS':'NG')+' · Security '+(report.security_passed?'PASS':'NG');
    button.textContent=report.status==='pass'?'再点検 PASS':'要確認';
  }catch(e){
    status.textContent='再点検失敗: '+e.message;
    button.textContent='再点検';
  }finally{
    button.disabled=false;
  }
}
async function loadDownloads(){
  if(!state.projects.length)await loadProjects();
  const all=[];
  for(const p of state.projects){
    try{const d=await api('/api/v1/projects/'+encodeURIComponent(p.slug)+'/deliveries');(d.deliveries||[]).forEach(x=>all.push({...x,project_name:p.name}));}catch{}
  }
  $('#downloadList').innerHTML=all.map(x=>`
    <div class="download-row ${x.available?'':'pending'}">
      <div><strong>${esc(x.project_name)}</strong><div class="meta">${esc(x.label)}</div></div>
      <div>${esc(x.target)}</div>
      <div class="download-status">${esc(x.status)}</div>
      <div class="meta">${esc(x.guide)}${x.available&&x.artifact_id?`<div class="download-action"><a class="download-link" href="/api/v1/artifacts/download?project=${encodeURIComponent(x.project_slug)}&id=${encodeURIComponent(x.artifact_id)}">ダウンロード</a></div>`:''}</div>
    </div>`).join('')||'<div class="empty">まだ配布対象の成果物はありません。</div>';
}
function setMode(mode){
  const allowed=['chat','app','web','automation','ivy_lab'];
  state.currentMode=allowed.includes(mode)?mode:'chat';
  storageSet('aivy-mode',state.currentMode);
  document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===state.currentMode));
  const labels={chat:'CHAT',app:'APP',web:'WEB',automation:'AUTOMATION',ivy_lab:'IVY LAB'};
  const status=$('#modeStatus');if(status)status.innerHTML='<i></i>'+labels[state.currentMode];
  const prompt=$('#prompt');
  if(prompt){
    const placeholders={
      chat:'何でも話してください…',
      app:'作りたいアプリをそのまま話してください…',
      web:'作りたいサイトやデザインを話してください…',
      automation:'自動化したい作業を話してください…',
      ivy_lab:'Aivyに成長してほしい内容を話してください…'
    };
    prompt.placeholder=placeholders[state.currentMode]||placeholders.chat;
  }
}
async function newChat(){
  saveDraft();
  const row=await api('/api/v1/conversations',{method:'POST',body:JSON.stringify({title:'新しいチャット'})});
  state.currentThread=row;storageSet('aivy-last-thread',row.thread_id||'');
  $('#messages').innerHTML='';$('#welcome').hidden=false;$('#topbarTitle').textContent='新しいチャット';
  setMode('chat');setView('home');restoreDraft();await loadConversations();
  $('#prompt')?.focus();
}
async function planGoal(text){
  const projectSlug=state.currentThread?.project_slug||null;
  const plan=await api('/api/v1/agent/plan',{method:'POST',body:JSON.stringify({goal:text,project_slug:projectSlug})});
  $('#agentPlan').innerHTML=(plan.steps||[]).map((x,i)=>{
    const team=(x.specialists||[]).length?' · '+(x.specialists||[]).map(s=>({
      coordinator:'司令塔',research:'Research',architect:'Architect',coding:'Coding',design:'Design',test:'Test',security:'Security',build:'Build',release:'Release'
    }[s]||s)).join(' / '):'';
    return `<div class="plan-step"><div class="step-no">${i+1}</div><div><strong>${esc(x.title)}</strong><p>${esc(x.purpose)}${esc(team)}${x.requires_human_approval?' · 人の承認が必要':''}</p></div></div>`;
  }).join('');
  if(projectSlug){
    const holder=document.createElement('div');
    holder.className='safe-agent-wrap';
    holder.innerHTML='<button class="agent-action secondary" id="runSafeAgent" type="button">Aivy自律点検</button><p>現在のアプリをInspect → Tests → Design → Securityまで安全Toolだけで確認します。コード変更・公開はしません。</p><div id="safeAgentResult"></div>';
    $('#agentPlan').append(holder);
    $('#runSafeAgent').onclick=()=>runSafeAgent(text,projectSlug);
  }
  $('#inspector').classList.add('open');
  return plan;
}
async function runSafeAgent(goal,projectSlug){
  const button=$('#runSafeAgent');const target=$('#safeAgentResult');
  if(!button||!target)return;
  button.disabled=true;button.textContent='Aivy点検中…';
  target.innerHTML='<div class="safe-agent-note">Evidenceを集めています…</div>';
  try{
    const report=await api('/api/v1/agent/run-safe',{
      method:'POST',
      body:JSON.stringify({goal,project_slug:projectSlug})
    });
    const labels={executed:'実行済み',delegated:'既存パイプラインへ委譲',approval_required:'人の承認待ち',failed:'NG',error:'エラー',planned:'計画'};
    target.innerHTML='<div class="safe-agent-report"><div class="safe-agent-head"><strong>Aivy Agent Run</strong><span>'+esc(report.status||'')+'</span></div>'+
      (report.steps||[]).map(x=>'<div class="safe-agent-step '+esc(x.status||'')+'"><b>'+esc(x.step_id||x.action||'step')+'</b><span>'+esc(labels[x.status]||x.status||'')+'</span><p>'+esc(x.summary||'')+'</p></div>').join('')+
      '<div class="safe-agent-foot">任意shell: '+(report.arbitrary_shell?'有効':'無効')+' · 実行Tool: '+esc((report.executed_tools||[]).join(', ')||'なし')+'</div></div>';
  }catch(e){
    target.innerHTML='<div class="safe-agent-note error">自律点検を完了できませんでした: '+esc(e.message)+'</div>';
  }finally{
    button.disabled=false;button.textContent='Aivy自律点検';
  }
}
function setBusy(value){
  state.busy=value;
  const send=$('#sendButton');if(send)send.disabled=value;
  const composer=$('#composer');if(composer)composer.classList.toggle('busy',value);
  const hint=$('#composerHint');
  if(hint)hint.textContent=value?'Aivyが作業中 · 次の依頼は入力して保存できます':'Enterで送信 · Shift+Enterで改行';
}
function showBuildApproval(instruction){
  state.pendingInstruction=instruction||state.lastGoal;
  const holder=document.createElement('div');
  holder.className='agent-action-wrap';
  holder.innerHTML='<div class="agent-action-grid"><button class="agent-action secondary" id="runCouncil">専門AIで検討</button><button class="agent-action" id="approveBuild">この内容で作る</button></div><p>専門AI会議は明示的に押した時だけ実行します。「この内容で作る」を押すまで生成は始まりません。</p><div id="councilResult"></div>';
  $('#agentPlan').append(holder);
  $('#approveBuild').onclick=approveBuild;
  $('#runCouncil').onclick=runCouncil;
}
async function runCouncil(){
  const button=$('#runCouncil');const target=$('#councilResult');
  if(!button||!target||state.busy)return;
  button.disabled=true;button.textContent='専門AI＋安全Tool確認中…';
  try{
    const report=await api('/api/v1/agent/safe-run',{
      method:'POST',
      body:JSON.stringify({
        goal:state.pendingInstruction||state.lastGoal||'',
        project_slug:state.currentThread?.project_slug||null,
        context:{source:'web-user-requested-safe-agent-run'}
      })
    });
    const council=report||{};
    if(council.status==='not_connected'){
      target.innerHTML='<div class="council-note">AIモデル未接続のため専門AI会議・Tool実行は行っていません。</div>';
      return;
    }
    const turns=council.turns||[];
    const executed=(council.tool_executions||[]).filter(x=>x.status==='executed'||x.status==='reused');
    const skipped=(council.tool_executions||[]).filter(x=>!['executed','reused'].includes(x.status));
    target.innerHTML='<div class="council-report"><div class="council-head"><strong>Aivy専門AI会議＋安全Tool</strong><span>'+esc(council.status)+'</span></div>'+
      turns.map(x=>{
        const r=x.result||{};
        const findings=(r.findings||[]).slice(0,3);
        return '<details class="council-turn"><summary>'+esc(x.specialist)+' · '+esc(r.summary||'')+'</summary>'+
          (findings.length?'<p>'+findings.map(esc).join('<br>')+'</p>':'')+
          ((r.uncertainties||[]).length?'<p class="muted">不確実: '+(r.uncertainties||[]).slice(0,2).map(esc).join(' / ')+'</p>':'')+
          '</details>';
      }).join('')+
      '<div class="council-tools"><strong>安全Tool実行</strong><p>'+
        (executed.length?executed.map(x=>esc(x.specialist)+' → '+esc(x.tool_name)+' ✓').join('<br>'):'実行対象なし')+
        (skipped.length?'<br><span class="muted">保留/拒否: '+skipped.map(x=>esc(x.tool_name)+' ('+esc(x.status)+')').join(' / ')+'</span>':'')+
      '</p></div>'+
      '<div class="evidence-review '+esc(council.evidence_state||'partial')+'"><strong>実Evidence判定: '+esc(council.evidence_state||'partial')+'</strong><p>'+esc((council.validation||{}).rule||'')+'</p></div>'+
      '<div class="council-final"><strong>まとめ</strong><p>'+esc(council.summary||'')+'</p></div></div>';
  }catch(e){
    target.innerHTML='<div class="council-note error">専門AI＋安全Toolを実行できませんでした: '+esc(e.message)+'</div>';
  }finally{
    button.disabled=false;button.textContent='専門AIで検討';
  }
}
async function executeBuild(slug,instruction){
  setBusy(true);
  state.activeBuildStage='starting';
  message('assistant','Aivyが作成・デザイン確認・テスト・セキュリティ検査を開始しました。');
  const stageNames={
    queued:'待機中',starting:'開始中',preflight:'事前確認',understand:'内容確認',plan:'設計中',build:'コード生成中',
    enhance:'AI改善中',package:'成果物準備中',design:'Design確認中',repair:'修正中',
    verify:'テスト・Security確認中',visual:'Vision Design確認中',core_checked:'Core内部確認済み',
    postflight:'独立再検証',trace:'Evidence照合',certificate:'証明書作成',done:'完了',issue:'確認事項あり'
  };
  const stageProgress={
    queued:3,starting:6,preflight:10,understand:15,plan:22,build:38,enhance:50,package:58,
    design:65,repair:70,verify:78,visual:84,core_checked:88,postflight:92,trace:95,certificate:98,done:100,issue:100
  };
  setTaskProgress(true,'Aivyが制作しています','開始しています…',5);
  try{
    const started=await api('/api/v1/projects/'+encodeURIComponent(slug)+'/build/jobs',{
      method:'POST',
      body:JSON.stringify({
        instruction,
        approved:true,
        thread_id:state.currentThread?.thread_id||null
      })
    });
    if(!started.job_id)throw new Error('Build Job IDを取得できませんでした');
    let job=started;
    for(let i=0;i<1200;i++){
      if(['completed','blocked','failed'].includes(job.status))break;
      await new Promise(resolve=>setTimeout(resolve,1000));
      job=await api('/api/v1/build/jobs/'+encodeURIComponent(started.job_id));
      const stage=job.stage||'starting';
      state.activeBuildStage=stage;
      const label=stageNames[stage]||stage||'処理中';
      const percent=stageProgress[stage]??Math.min(96,8+Math.floor(i/12));
      $('#coreStatus').innerHTML='<i></i>'+esc(label);
      $('#coreStatus').classList.add('success');
      setTaskProgress(true,'Aivyが制作しています',label,percent);
    }
    if(!['completed','blocked','failed'].includes(job.status)){
      throw new Error('生成処理の状態確認がタイムアウトしました');
    }
    if(job.status==='failed'){
      throw new Error(job.error||job.message||'Build Job failed');
    }
    const result=job.result||{};
    state.activeBuildStage=job.status==='completed'?'done':'issue';
    setTaskProgress(true,job.status==='completed'?'制作完了':'確認が必要です',job.message||result.message||'',100);
    message('assistant',result.message||job.message||'確認が完了しました。');
    await loadProjects();
    await loadConversations();
    await loadDownloads();
    await showProject(slug);
    toast(job.status==='completed'?'制作・検証が完了しました。':'確認が必要な項目があります。',job.status==='completed'?'success':'info');
  }catch(e){
    state.activeBuildStage='issue';
    setTaskProgress(true,'処理を完了できませんでした',e.message,100);
    message('assistant','生成を完了できませんでした: '+e.message);
    toast('生成処理でエラーが発生しました。','error');
  }finally{
    $('#coreStatus').innerHTML='<i></i>Core接続';
    $('#coreStatus').classList.add('success');
    setBusy(false);
    setTimeout(()=>setTaskProgress(false),2200);
  }
}
async function approveBuild(){
  if(state.busy||!state.currentThread)return;
  setBusy(true);
  message('user','この内容で作る');
  try{
    const decision=await api('/api/v1/chat/turn',{
      method:'POST',
      body:JSON.stringify({thread_id:state.currentThread.thread_id,message:'この内容で作る',mode:state.currentMode})
    });
    if(decision.thread)state.currentThread=decision.thread;
    if(decision.mode)setMode(decision.mode);
    message('assistant',decision.message||'確認しました。');
    if(decision.action!=='build'||!decision.project_slug||!decision.instruction){
      throw new Error('生成承認状態を確認できませんでした');
    }
    setBusy(false);
    await executeBuild(decision.project_slug,decision.instruction);
  }catch(e){
    setBusy(false);
    message('assistant','生成開始を確認できませんでした: '+e.message);
  }
}
async function send(text){
  text=text.trim();if(!text)return;
  if(state.busy){
    saveDraft();
    toast('Aivyは現在作業中です。入力内容は下書き保存しました。','info');
    return;
  }
  if(!state.currentThread)await newChat();
  state.lastGoal=text;
  message('user',text);storageRemove(draftKey());$('#prompt').value='';autoGrow();setBusy(true);showThinking();
  const draftStatus=$('#draftStatus');if(draftStatus)draftStatus.textContent='下書き保存';
  try{
    const decision=await api('/api/v1/chat/turn',{
      method:'POST',
      body:JSON.stringify({thread_id:state.currentThread.thread_id,message:text,mode:state.currentMode})
    });
    if(decision.thread)state.currentThread=decision.thread;
    if(decision.mode)setMode(decision.mode);
    removeThinking();message('assistant',decision.message||'確認しました。');
    if(decision.action==='review'){
      await planGoal(decision.instruction||text);
      showBuildApproval(decision.instruction||text);
      toast('設計内容を確認できます。問題なければ「この内容で作る」を押してください。','success');
    }else if(decision.action==='build'&&decision.project_slug&&decision.instruction){
      setBusy(false);
      await executeBuild(decision.project_slug,decision.instruction);
      return;
    }else if(decision.project_slug&&decision.action!=='chat'){
      await planGoal(decision.instruction||text);
    }
    await loadConversations();
  }catch(e){
    removeThinking();
    message('assistant','Aivyが会話を処理できませんでした: '+e.message);
    toast('会話処理でエラーが発生しました。','error');
  }finally{
    removeThinking();setBusy(false);
  }
}
function autoGrow(){const p=$('#prompt');p.style.height='auto';p.style.height=Math.min(p.scrollHeight,160)+'px';}
async function loadModelRoutes(){
  const target=$('#modelRouteSummary');const controls=$('#modelRouteControls');if(!target)return;
  try{
    const data=await api('/api/v1/models/routes');
    const rows=(data.routes||[]).filter(x=>['coding','vision','research','reasoning'].includes(x.capability));
    target.textContent=rows.map(x=>{
      const r=x.effective||{};
      return x.capability+' → '+(r.provider||'none')+(r.model?' / '+r.model:'');
    }).join(' · ')||'ルート未設定';
    if(controls){
      controls.innerHTML=rows.map(x=>{
        const configured=x.configured||{};
        const effective=x.effective||{};
        const provider=configured.provider||effective.provider||'none';
        const model=configured.model||effective.model||'';
        return `<div class="route-row" data-capability="${esc(x.capability)}">
          <div><strong>${esc(x.capability)}</strong><small>${esc(effective.capability||'')}</small></div>
          <select class="route-provider" aria-label="${esc(x.capability)} provider">
            <option value="none"${provider==='none'?' selected':''}>Default</option>
            <option value="openai"${provider==='openai'?' selected':''}>OpenAI</option>
            <option value="gemini"${provider==='gemini'?' selected':''}>Gemini</option>
          </select>
          <input class="route-model" value="${esc(model)}" placeholder="model name" aria-label="${esc(x.capability)} model">
          <button class="route-save" type="button">保存</button>
        </div>`;
      }).join('');
      $$('#modelRouteControls .route-save').forEach(button=>{
        button.onclick=async()=>{
          const row=button.closest('.route-row');
          const capability=row.dataset.capability;
          const provider=row.querySelector('.route-provider').value;
          const model=row.querySelector('.route-model').value.trim();
          button.disabled=true;button.textContent='保存中';
          try{
            await api('/api/v1/models/routes',{
              method:'POST',
              body:JSON.stringify({capability,provider,model})
            });
            button.textContent='保存済み';
            await loadModelRoutes();
          }catch(e){
            button.textContent='失敗';
            target.textContent='Model Router保存に失敗: '+e.message;
          }finally{
            button.disabled=false;
          }
        };
      });
    }
  }catch(e){target.textContent='Model Router情報を取得できませんでした';}
}
async function loadEvolutionSummary(){
  const target=$('#evolutionSummary');if(!target)return;
  try{
    const [policy,history]=await Promise.all([
      api('/api/v1/evolution/policy'),
      api('/api/v1/evolution/experiments')
    ]);
    const rows=history.experiments||[];
    const latest=rows[0];
    const suffix=latest?(' · 最新: '+latest.status+' / '+latest.title):' · Experiment履歴なし';
    target.textContent='自動適用なし / main自動mergeなし / 人レビュー必須'+suffix;
  }catch(e){target.textContent='Evolution情報を取得できませんでした';}
}
async function loadKnowledgeSummary(){
  const target=$('#knowledgeSummary');if(!target)return;
  try{
    const data=await api('/api/v1/knowledge/staged');
    const rows=data.knowledge||[];
    const counts={untrusted:0,candidate:0,verified:0};
    rows.forEach(x=>{if(Object.prototype.hasOwnProperty.call(counts,x.trust_level))counts[x.trust_level]++;});
    target.textContent='Untrusted '+counts.untrusted+' · Candidate '+counts.candidate+' · Verified '+counts.verified+' · Agentが再利用するのはVerifiedのみ';
  }catch(e){target.textContent='Knowledge状態を取得できませんでした';}
}
async function loadHealthSummary(){
  const target=$('#healthSummary');if(!target)return;
  try{
    const data=await api('/api/v1/health/dashboard');
    target.textContent='Status '+(data.status||'unknown')+' · Projects '+(data.project_count||0)+' · AI '+(data.specialist_count||0)+'人 · Missions '+(data.active_missions||0)+' active / '+(data.mission_count||0)+' total · Verified Learning '+(data.verified_learning_examples||0);
  }catch(e){target.textContent='Aivy Healthを取得できませんでした';}
}
async function loadBenchmarkSummary(){
  const target=$('#benchmarkSummary');if(!target)return;
  try{
    const data=await api('/api/v1/models/benchmark?capability=coding');
    const rows=data.models||[];
    if(!rows.length){
      target.textContent='まだ実測データなし · 成功したビルドから自動蓄積';
      return;
    }
    target.textContent='Coding実測 '+(data.observations||0)+'件 · '+rows.slice(0,3).map(x=>x.provider+'/'+x.model+' 成功率 '+Math.round((x.success_rate||0)*100)+'% / 品質 '+(x.average_quality||0)).join(' · ');
  }catch(e){target.textContent='Model Benchmarkを取得できませんでした';}
}
async function loadSquadSummary(){
  const target=$('#squadSummary');if(!target)return;
  try{
    const data=await api('/api/v1/agents');
    const agents=data.agents||[];
    const names=agents.map(x=>x.title||x.name).filter(Boolean);
    target.textContent=agents.length+'人の専門AI · 案件ごとに必要な役職を自動招集 · '+names.slice(0,6).join(' / ')+(agents.length>6?' ほか':'');
  }catch(e){target.textContent='AIチーム状態を取得できませんでした';}
}
async function loadLearningSummary(){
  const target=$('#learningSummary');if(!target)return;
  try{
    const data=await api('/api/v1/learning/status');
    const latest=data.latest||null;
    const suffix=latest?(' · 最新 '+latest.evaluation_score+'/100'):' · まだ検証済み経験なし';
    target.textContent='Verified '+(data.verified_examples||0)+'件 · 平均 '+(data.average_score||0)+'/100 · AI利用 '+(data.ai_backed_examples||0)+'件 · 教師候補を安全に蓄積中'+suffix;
  }catch(e){target.textContent='Learning状態を取得できませんでした';}
}
async function loadGrowthLab(){
  const headline=$('#growthHeadline');const summary=$('#growthSummary');const toggle=$('#toggleGrowth');
  const driveHeadline=$('#selfDriveHeadline');const driveSummary=$('#selfDriveSummary');const driveToggle=$('#toggleSelfDrive');
  if(!headline||!summary||!toggle||!driveHeadline||!driveSummary||!driveToggle)return;
  try{
    const [data,practice,drive,backlog,daily,completion,crossMode,multiMission,soak]=await Promise.all([
      api('/api/v1/growth/status'),
      api('/api/v1/practice/status'),
      api('/api/v1/self-drive/status'),
      api('/api/v1/backlog/today'),
      api('/api/v1/daily-evolution/status'),
      api('/api/v1/completion/readiness'),
      api('/api/v1/completion/cross-mode-e2e'),
      api('/api/v1/completion/multi-mission-e2e'),
      api('/api/v1/completion/soak')
    ]);

    const completionScore=Number(completion.percentage||0);
    $('#completionHeadline').textContent=completion.complete
      ? 'Aivy Completion Readiness · 100%'
      : 'Aivy Completion Readiness · '+completionScore.toFixed(1)+'%';
    $('#completionSummary').textContent=completion.complete
      ? '全ての採点基準がEvidence付きで完了しています。'
      : '100%まで残り '+Math.max(0,100-completionScore).toFixed(1)+'pt · 未検証は完成扱いにしません。';
    $('#completionScore').textContent=completionScore.toFixed(1)+'%';
    $('#completionBar').style.width=Math.max(0,Math.min(100,completionScore))+'%';
    const topGap=completion.highest_priority_gap||null;
    $('#completionGap').innerHTML=topGap
      ? '<strong>最大ギャップ: '+esc(topGap.title||topGap.criterion_id||'未確認')+' · -'+esc(topGap.lost_points||0)+'pt</strong>'+
        '<p>'+esc((topGap.missing||[]).join(' / ')||'Evidence不足')+'<br>次: '+esc(topGap.next_action||'再評価')+'</p>'
      : '<strong>主要ギャップなし</strong><p>全採点基準を通過しています。</p>';
    const completionEvidence=$('#completionEvidence');
    if(completionEvidence){
      const modeRows=crossMode.cases||[];
      completionEvidence.innerHTML=
        '<strong>Cross-mode real E2E: '+(crossMode.verified?'VERIFIED':'UNVERIFIED')+'</strong>'+
        '<div>source: '+esc(crossMode.source||'none')+(crossMode.stale?' · STALE':'')+'</div>'+
        '<div class="e2e-modes">'+['app','web','automation'].map(mode=>{
          const row=modeRows.find(x=>x.mode===mode)||{};
          return '<span class="e2e-mode '+(row.passed?'pass':'fail')+'">'+mode.toUpperCase()+' '+(row.passed?'PASS':'未検証')+'</span>';
        }).join('')+
        '<span class="e2e-mode '+(multiMission.verified?'pass':'fail')+'">MULTI MISSION '+(multiMission.verified?'PASS':'未検証')+'</span></div>'+
        '<div>Mission source: '+esc(multiMission.source||'none')+(multiMission.stale?' · STALE':'')+'</div>';
    }
    const soakProgress=Number(soak.progress_percent||0);
    $('#soakStatus').textContent=soak.verified?'VERIFIED':String(soak.status||'running').toUpperCase();
    $('#soakBar').style.width=Math.max(0,Math.min(100,soakProgress))+'%';
    const soakHours=(Number(soak.elapsed_seconds||0)/3600).toFixed(1);
    const remainHours=(Number(soak.remaining_seconds||0)/3600).toFixed(1);
    $('#soakSummary').textContent=
      '実経過 '+soakHours+'h / 24h · '+soakProgress.toFixed(1)+'% · Sample '+(soak.sample_count||0)+'/'+(soak.min_samples||80)+
      ' · Failure '+(soak.failure_count||0)+
      (soak.verified?' · 24h Evidence成立':' · 残り約'+remainHours+'h')+
      (soak.stale?' · SOURCE変更で無効':'');
    const completionCriteria=$('#completionCriteria');
    if(completionCriteria){
      completionCriteria.innerHTML=(completion.criteria||[]).map(x=>
        '<div class="completion-criterion '+esc(x.status||'partial')+'">'+
        '<div class="completion-criterion-head"><strong>'+esc(x.title||x.criterion_id||'criterion')+'</strong><span>'+esc(x.score||0)+'/'+esc(x.weight||0)+'</span></div>'+
        '<p>'+((x.gaps||[]).length?'不足: '+esc((x.gaps||[]).join(', ')):'Evidence OK')+'</p></div>'
      ).join('');
    }

    const dailyLast=daily.last_result||{};
    const delta=dailyLast.evolution_delta||{};
    const dailyPractice=dailyLast.practice||{};
    const dailyPromotion=dailyPractice.promotion||{};
    $('#dailyEvolutionHeadline').textContent=daily.enabled
      ? (daily.due_today?'毎日進化 · 今日まだ未実行':'毎日進化 · 今日の進化完了')
      : '毎日進化 OFF';
    $('#dailyEvolutionSummary').textContent=
      (daily.background_active?'自動チェック稼働中 · ':'')+
      '起動時に未実行なら自動進化 · 以後30分ごとに日付確認'+
      (daily.last_run_at?' · 最終 '+fmt(daily.last_run_at):'');
    $('#dailyEvolutionDue').textContent=daily.enabled?(daily.due_today?'未実行':'完了'):'OFF';
    $('#dailyEvolutionSkills').textContent=daily.skills||0;
    $('#dailyEvolutionWeaknesses').textContent=daily.weaknesses||0;
    $('#dailyEvolutionPractice').textContent=dailyPromotion.promoted?'Skill昇格':(dailyLast.ran?'確認済み':'—');
    const dailyButton=$('#toggleDailyEvolution');
    dailyButton.textContent=daily.enabled?'毎日進化をOFF':'毎日進化をON';
    dailyButton.dataset.enabled=daily.enabled?'true':'false';
    const dailyLastTarget=$('#dailyEvolutionLast');
    if(dailyLastTarget){
      if(!daily.last_run_at){
        dailyLastTarget.innerHTML='<span class="meta">まだ日次進化履歴はありません。</span>';
      }else{
        dailyLastTarget.innerHTML=
          '<strong>'+esc(dailyLast.status||'completed')+'</strong>'+
          ' · Skill '+esc(delta.skills_before??daily.skills??0)+' → '+esc(delta.skills_after??daily.skills??0)+
          ' · 弱点 '+esc(delta.weaknesses_before??daily.weaknesses??0)+' → '+esc(delta.weaknesses_after??daily.weaknesses??0)+
          (delta.practice_promoted?' · 自主トレSkill昇格':' · 自主トレ確認済み')+
          ' · '+esc(fmt(daily.last_run_at));
      }
    }

    const counts=backlog.counts||{};
    const focus=backlog.focus||[];
    $('#backlogHeadline').textContent='今日のAivy · '+esc(backlog.date||'');
    $('#backlogSummary').textContent=
      (backlog.self_drive_enabled?'自走ON':'自走OFF')+
      ' · 安全に自動実行できる項目 '+(backlog.safe_auto_count||0)+'件'+
      ' · 人の判断待ち '+(backlog.approval_waiting||0)+'件';
    $('#backlogTodo').textContent=counts.todo||0;
    $('#backlogApproval').textContent=counts.waiting_approval||0;
    $('#backlogDone').textContent=counts.completed||0;
    $('#backlogFailed').textContent=counts.failed||0;
    const focusTarget=$('#backlogFocus');
    if(focusTarget){
      focusTarget.innerHTML=focus.length
        ? focus.map((x,i)=>'<div class="daily-focus-row"><span class="daily-focus-rank">'+(i+1)+'</span><div><strong>'+esc(x.title||x.kind||'task')+'</strong><p>'+esc(x.reason||'')+(x.target?' · '+esc(x.target):'')+'</p></div><span class="daily-focus-status '+esc(x.status||'todo')+'">'+esc(x.status||'todo')+'</span></div>').join('')
        : '<span class="meta">今日の安全な自走タスクは完了しています。新しいEvidenceが出るまで待機します。</span>';
    }

    driveHeadline.textContent=drive.enabled?'自走モード ON':'自走モード OFF';
    driveSummary.textContent=
      '10分ごとに安全な優先タスクを最大1件 · Queue '+(drive.queue_count||0)+'件'+
      ' · 承認待ち '+(drive.approval_waiting||0)+'件'+
      (drive.background_active?' · Autopilot稼働中':'');
    driveToggle.textContent=drive.enabled?'自走をOFF':'自走をON';
    driveToggle.dataset.enabled=drive.enabled?'true':'false';

    const driveQueue=$('#selfDriveQueue');
    const driveApproval=$('#selfDriveApproval');
    const driveLast=$('#selfDriveLast');
    const queueRows=drive.queue||[];
    if(driveQueue){
      driveQueue.innerHTML=queueRows.length
        ? queueRows.slice(0,6).map(x=>'<div class="self-drive-task"><div><strong>'+esc(x.title||x.kind||'task')+'</strong><p>'+esc(x.reason||'')+'</p></div><span class="self-drive-priority">P'+esc(x.priority||0)+'</span></div>').join('')
        : '<span class="meta">今すぐ安全に進める作業はありません。待機中です。</span>';
    }
    if(driveApproval){
      driveApproval.innerHTML=(drive.approval_waiting||0)>0
        ? '<div class="self-drive-task"><div><strong>'+esc(drive.approval_waiting)+'件の承認待ち</strong><p>Build・公開など人の判断が必要な地点で停止しています。</p></div><span class="self-drive-state off">WAIT</span></div>'
        : '<div class="self-drive-task"><div><strong>承認待ちなし</strong><p>現在、人の判断待ちで停止している自走タスクはありません。</p></div><span class="self-drive-state on">CLEAR</span></div>';
    }
    if(driveLast){
      const last=drive.last_action||null;
      if(!last){
        driveLast.innerHTML='<span class="meta">まだ自走履歴はありません。</span>';
      }else{
        const task=last.task||{};const outcome=last.outcome||{};
        driveLast.innerHTML='<div class="self-drive-task"><div><strong>'+esc(task.title||last.status||'自走')+'</strong><p>'+esc(outcome.message||outcome.status||last.status||'')+'</p><small>'+esc(last.created_at?fmt(last.created_at):'')+'</small></div><span class="self-drive-state '+(last.status==='completed'?'on':'off')+'">'+esc(last.status||'done')+'</span></div>';
      }
    }

    headline.textContent=data.enabled?'自律成長 ON':'自律成長 OFF';
    summary.textContent='Verified '+(data.verified_examples||0)+'件 · Skill '+(data.skills||0)+'件 · 平均 '+(data.average_score||0)+'/100'+(data.background_active?' · 放置成長ループ稼働中':'')+(data.practice_runner_connected?' · 自主トレ接続済み':'')+(data.last_run_at?' · 最終 '+fmt(data.last_run_at):'');
    toggle.textContent=data.enabled?'自律成長をOFF':'自律成長をON';
    toggle.dataset.enabled=data.enabled?'true':'false';

    const weaknesses=practice.weaknesses||[];
    const queue=practice.practice_queue||[];
    const last=practice.last_practice||null;
    const weaknessTarget=$('#practiceWeaknesses');
    const queueTarget=$('#practiceQueue');
    const lastTarget=$('#lastPractice');

    if(weaknessTarget){
      weaknessTarget.innerHTML=weaknesses.length
        ? weaknesses.slice(0,6).map(x=>'<div class="practice-row"><div><strong>'+esc(x.kind||'weakness')+'</strong><p>'+esc(x.summary||'')+'</p></div><span class="practice-severity '+esc(x.severity||'low')+'">'+esc(x.severity||'low')+'</span></div>').join('')
        : '<span class="meta">現在、優先自主トレ対象はありません。</span>';
    }
    if(queueTarget){
      queueTarget.innerHTML=queue.length
        ? queue.slice(0,5).map((x,i)=>'<div class="practice-row"><div><strong>#'+(i+1)+' '+esc(x.title||'practice')+'</strong><p>'+esc(x.objective||'')+'</p></div><span class="chip">'+esc(x.mode||'app').toUpperCase()+'</span></div>').join('')
        : '<span class="meta">Practice Queueは空です。</span>';
    }
    if(lastTarget){
      if(!last){
        lastTarget.innerHTML='<span class="meta">まだ自主トレ履歴はありません。</span>';
      }else{
        const promotion=last.promotion||{};
        const weakness=last.weakness||{};
        lastTarget.innerHTML='<div class="practice-row"><div><strong>'+esc(last.status||'completed')+'</strong><p>'+esc(weakness.summary||'')+'</p><small>'+esc(last.created_at?fmt(last.created_at):'')+'</small></div><span class="practice-promotion '+(promotion.promoted?'promoted':'rejected')+'">'+(promotion.promoted?'Skill昇格':'未昇格')+'</span></div>';
      }
    }
  }catch(e){
    driveHeadline.textContent='自走状態を取得できませんでした';
    driveSummary.textContent=e.message;
    headline.textContent='成長状態を取得できませんでした';
    summary.textContent=e.message;
  }
}
async function checkpointSoak(){
  const button=$('#checkpointSoak');if(!button)return;
  button.disabled=true;button.textContent='Soak確認中…';
  try{
    const data=await api('/api/v1/completion/soak/checkpoint',{method:'POST',body:'{}'});
    toast(
      'Soak '+Number(data.progress_percent||0).toFixed(1)+'% · Sample '+(data.sample_count||0)+' · Failure '+(data.failure_count||0),
      data.failure_count?'error':'success'
    );
    await loadGrowthLab();
  }catch(e){
    toast('Soak確認を完了できませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='Soak確認';}
}
async function runMultiMissionE2E(){
  const button=$('#runMultiMissionE2E');if(!button)return;
  button.disabled=true;button.textContent='Mission検証中…';
  try{
    const data=await api('/api/v1/completion/multi-mission-e2e/run',{method:'POST',body:'{}'});
    toast(
      data.verified?'複数Mission E2E: PASS':'複数Mission E2E: 要確認',
      data.verified?'success':'info'
    );
    await loadGrowthLab();
  }catch(e){
    toast('Mission E2Eを完了できませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='Mission E2E';}
}
async function runCrossModeE2E(){
  const button=$('#runCrossModeE2E');if(!button)return;
  button.disabled=true;button.textContent='3モード検証中…';
  try{
    const data=await api('/api/v1/completion/cross-mode-e2e/run',{method:'POST',body:'{}'});
    const passed=(data.cases||[]).filter(x=>x.passed).length;
    toast('実E2E: '+passed+'/3 モードPASS',data.verified?'success':'info');
    await loadGrowthLab();
  }catch(e){
    toast('実E2E検証を完了できませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='実E2E検証';}
}
async function refreshCompletion(){
  const button=$('#refreshCompletion');if(!button)return;
  button.disabled=true;button.textContent='再評価中…';
  try{
    await loadGrowthLab();
    toast('Completion ReadinessをEvidenceから再評価しました。','success');
  }catch(e){
    toast('完成度を再評価できませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='完成度を再評価';}
}
async function toggleDailyEvolution(){
  const button=$('#toggleDailyEvolution');if(!button)return;
  const next=button.dataset.enabled!=='true';
  button.disabled=true;
  try{
    await api('/api/v1/daily-evolution/settings',{method:'POST',body:JSON.stringify({enabled:next})});
    toast(next?'毎日自動進化をONにしました。':'毎日自動進化をOFFにしました。',next?'success':'info');
    await loadGrowthLab();
  }catch(e){
    toast('毎日進化の設定を変更できませんでした: '+e.message,'error');
  }finally{button.disabled=false;}
}
async function runDailyEvolution(){
  const button=$('#runDailyEvolution');if(!button)return;
  button.disabled=true;button.textContent='進化中…';
  try{
    const data=await api('/api/v1/daily-evolution/run',{method:'POST',body:'{}'});
    const delta=data.evolution_delta||{};
    toast(
      'Aivy進化: Skill '+(delta.skills_before??0)+' → '+(delta.skills_after??0)+
      (delta.practice_promoted?' · 自主トレSkill昇格':''), 
      data.status==='completed'?'success':'info'
    );
    await loadGrowthLab();
  }catch(e){
    toast('日次進化を完了できませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='今すぐ進化する';}
}
async function refreshBacklog(){
  const button=$('#refreshBacklog');if(!button)return;
  button.disabled=true;button.textContent='再整理中…';
  try{
    await api('/api/v1/backlog/refresh',{method:'POST',body:'{}'});
    await loadGrowthLab();
    toast('今日のバックログを最新状態へ整理しました。','success');
  }catch(e){
    toast('バックログを更新できませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='今日の予定を再整理';}
}
async function toggleSelfDrive(){
  const button=$('#toggleSelfDrive');if(!button)return;
  const next=button.dataset.enabled!=='true';
  button.disabled=true;
  try{
    await api('/api/v1/self-drive/settings',{method:'POST',body:JSON.stringify({enabled:next})});
    toast(next?'自走モードをONにしました。':'自走モードをOFFにしました。',next?'success':'info');
    await loadGrowthLab();
  }catch(e){
    toast('自走モードを変更できませんでした: '+e.message,'error');
  }finally{button.disabled=false;}
}
async function runSelfDrive(){
  const button=$('#runSelfDrive');if(!button)return;
  button.disabled=true;button.textContent='自走中…';
  try{
    const data=await api('/api/v1/self-drive/run',{method:'POST',body:'{}'});
    const task=data.task||{};const outcome=data.outcome||{};
    const summary=data.status==='idle'
      ? '安全に進める必要がある作業はありません。'
      : (task.title||task.kind||'自走')+' → '+(outcome.status||data.status||'完了');
    toast('Aivy自走: '+summary,data.status==='completed'?'success':'info');
    await loadGrowthLab();
  }catch(e){
    toast('自走サイクルを完了できませんでした: '+e.message,'error');
  }finally{button.disabled=false;button.textContent='今すぐ1サイクル';}
}
async function toggleGrowth(){
  const button=$('#toggleGrowth');if(!button)return;
  const next=button.dataset.enabled!=='true';
  button.disabled=true;
  try{
    await api('/api/v1/growth/settings',{method:'POST',body:JSON.stringify({enabled:next})});
    await loadGrowthLab();
  }catch(e){
    $('#growthResult').textContent='設定変更に失敗: '+e.message;
  }finally{button.disabled=false;}
}
async function runGrowth(){
  const button=$('#runGrowth');const result=$('#growthResult');if(!button||!result)return;
  button.disabled=true;button.textContent='成長中…';result.textContent='Verified Evidenceから再利用Skillを整理しています…';
  try{
    const data=await api('/api/v1/growth/run',{method:'POST',body:'{}'});
    result.textContent='成長サイクル '+(data.status||'completed')+' · Skill追加 '+(data.skills_added||0)+' · 更新 '+(data.skills_updated||0)+' · 合計 '+(data.total_skills||0)+(data.weaknesses?.length?' · 弱点: '+data.weaknesses.join(', '):'');
    await loadGrowthLab();
  }catch(e){
    result.textContent='成長サイクルを完了できませんでした: '+e.message;
  }finally{button.disabled=false;button.textContent='今すぐ成長サイクル';}
}
async function runPractice(){
  const button=$('#runPractice');const result=$('#growthResult');if(!button||!result)return;
  button.disabled=true;button.textContent='自主トレ中…';
  result.textContent='Evidenceから最優先の弱点を1件選び、Synthetic Sandboxで練習しています…';
  try{
    const data=await api('/api/v1/practice/run',{method:'POST',body:'{}'});
    const promotion=data.promotion||{};
    const weakness=data.weakness||{};
    const practice=data.practice||{};
    const arena=practice.arena||{};
    result.textContent='自主トレ '+(data.status||'completed')+' · '+(weakness.kind||'弱点なし')+' · Arena '+(arena.status||'n/a')+' · '+(promotion.promoted?'Verified Skillへ昇格':'昇格なし')+' · 本体コード変更なし';
    await loadGrowthLab();
  }catch(e){
    result.textContent='自主トレを完了できませんでした: '+e.message;
  }finally{button.disabled=false;button.textContent='今すぐ自主トレ';}
}

async function boot(){
  try{
    const status=await api('/api/v1/status');state.csrf=status.csrf||'';
    $('#coreStatus').innerHTML='<i></i>Core接続';$('#coreStatus').classList.add('success');
    await Promise.all([loadConversations(),loadProjects()]);
    await Promise.all([loadModelRoutes(),loadEvolutionSummary(),loadKnowledgeSummary(),loadLearningSummary(),loadSquadSummary(),loadHealthSummary(),loadBenchmarkSummary()]);
    renderResume();
  }catch(e){
    $('#coreStatus').textContent='Core未接続';
    toast('Aivy Coreへ接続できません。起動状態を確認してください。','error');
  }
}
$('#composer').addEventListener('submit',e=>{e.preventDefault();send($('#prompt').value);});
$('#prompt').addEventListener('input',()=>{autoGrow();saveDraft();});
$('#prompt').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(e.currentTarget.value);}});
document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>send(b.dataset.prompt));
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{setMode(b.dataset.mode);$('#prompt')?.focus();});
document.querySelectorAll('[data-starter-mode]').forEach(b=>b.onclick=()=>{
  setMode(b.dataset.starterMode);
  const prompt=$('#prompt');if(!prompt)return;
  prompt.value='';
  prompt.placeholder=b.dataset.starterText||'そのまま話してください…';
  saveDraft();autoGrow();prompt.focus();
  toast((b.querySelector('strong')?.textContent||'Aivy')+'モードで始めます。','success');
});
document.querySelectorAll('.nav-item[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
document.querySelectorAll('[data-mobile-view]').forEach(b=>b.onclick=()=>setView(b.dataset.mobileView));
$('#mobileNewChat').onclick=newChat;
$('#newChat').onclick=newChat;$('#createStrategicGoal').onclick=createStrategicGoal;$('#runStrategicGoal').onclick=runStrategicGoal;$('#createMission').onclick=createMission;$('#runCrossModeE2E').onclick=runCrossModeE2E;$('#runMultiMissionE2E').onclick=runMultiMissionE2E;$('#checkpointSoak').onclick=checkpointSoak;$('#refreshCompletion').onclick=refreshCompletion;$('#refreshBacklog').onclick=refreshBacklog;$('#toggleDailyEvolution').onclick=toggleDailyEvolution;$('#runDailyEvolution').onclick=runDailyEvolution;$('#toggleSelfDrive').onclick=toggleSelfDrive;$('#runSelfDrive').onclick=runSelfDrive;$('#toggleGrowth').onclick=toggleGrowth;$('#runGrowth').onclick=runGrowth;$('#runPractice').onclick=runPractice;$('#openSidebar').onclick=openSidebar;$('#closeSidebar').onclick=closeSidebar;$('#overlay').onclick=closeSidebar;$('#closeInspector').onclick=()=>$('#inspector').classList.remove('open');
$('#conversationSearch').addEventListener('input',e=>loadConversations(e.target.value));
$('#themeToggle').onclick=()=>{const order=['system','light','dark'];const current=document.documentElement.dataset.theme||'system';const next=order[(order.indexOf(current)+1)%order.length];document.documentElement.dataset.theme=next;storageSet('ui-theme',next);};
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){$('#inspector')?.classList.remove('open');closeSidebar();}
  if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName||'')){e.preventDefault();$('#prompt')?.focus();}
});
document.documentElement.dataset.theme=storageGet('ui-theme','system');
setMode(storageGet('aivy-mode','chat'));restoreDraft();setView('home');boot();
