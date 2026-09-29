const state={csrf:'',view:'home',conversations:[],projects:[],currentThread:null,lastGoal:'',pendingInstruction:null,busy:false,currentMode:'chat'};
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
function openSidebar(){ $('#sidebar').classList.add('open');$('#overlay').classList.add('show');}
function closeSidebar(){ $('#sidebar').classList.remove('open');$('#overlay').classList.remove('show');}
function setView(name){
  state.view=name;
  $$('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+name));
  $$('.nav-item[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
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
  wrap.append(bubble);$('#messages').append(wrap);wrap.scrollIntoView({behavior:'smooth',block:'end'});
}
function renderRecent(){
  $('#recentChats').innerHTML=state.conversations.slice(0,8).map(x=>`<button class="recent-item" data-thread="${esc(x.thread_id)}">${x.pinned?'★ ':''}${esc(x.title)}</button>`).join('')||'<div class="empty">まだ会話はありません。</div>';
  $$('#recentChats [data-thread]').forEach(b=>b.onclick=()=>openConversation(b.dataset.thread));
}
async function loadConversations(query=''){
  const data=await api('/api/v1/conversations'+(query?'?q='+encodeURIComponent(query):''));
  state.conversations=data.conversations||[];renderRecent();
  $('#conversationGrid').innerHTML=state.conversations.map(x=>`
    <article class="data-card" data-thread="${esc(x.thread_id)}">
      <h3>${x.pinned?'★ ':''}${esc(x.title)}</h3>
      <div class="meta"><span>${x.project_slug?'アプリ: '+esc(x.project_slug):'会話のみ'}</span><span>${x.message_count} messages</span><span>${fmt(x.updated_at)}</span></div>
    </article>`).join('')||'<div class="empty">該当する会話はありません。</div>';
  $$('#conversationGrid [data-thread]').forEach(c=>c.onclick=()=>openConversation(c.dataset.thread));
}
async function openConversation(id){
  const row=state.conversations.find(x=>x.thread_id===id)||{thread_id:id,title:'会話'};
  state.currentThread=row;$('#messages').innerHTML='';$('#welcome').hidden=true;
  const data=await api('/api/v1/conversations/'+encodeURIComponent(id)+'/messages');
  (data.messages||[]).forEach(x=>message(x.role,x.content));
  setView('home');$('#topbarTitle').textContent=row.title;
}
async function loadMissions(){
  const projectSelect=$('#missionProject');
  try{
    if(!state.projects.length){
      const p=await api('/api/v1/projects');state.projects=p.projects||[];
    }
    if(projectSelect){
      projectSelect.innerHTML=state.projects.map(row=>`<option value="${esc(row.slug)}">${esc(row.name||row.slug)}</option>`).join('')||'<option value="">作成済みアプリがありません</option>';
    }
    const data=await api('/api/v1/missions');
    const rows=data.missions||[];
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

    $$('.mission-run').forEach(b=>b.onclick=()=>runMission(b.dataset.id,b.dataset.approved==='true'));
    $$('.mission-pause').forEach(b=>b.onclick=()=>pauseMission(b.dataset.id));
    $$('.mission-cancel').forEach(b=>b.onclick=()=>cancelMission(b.dataset.id));

    if(rows.some(m=>m.status==='running')&&state.view==='missions'){
      setTimeout(()=>{if(state.view==='missions')loadMissions();},1800);
    }
  }catch(e){
    $('#missionGrid').innerHTML='<div class="empty">Mission Controlを読み込めませんでした: '+esc(e.message)+'</div>';
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
  const data=await api('/api/v1/projects');state.projects=data.projects||[];
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
  $$('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===state.currentMode));
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
  const row=await api('/api/v1/conversations',{method:'POST',body:JSON.stringify({title:'新しいチャット'})});
  state.currentThread=row;$('#messages').innerHTML='';$('#welcome').hidden=false;$('#topbarTitle').textContent='新しいチャット';setMode('chat');setView('home');await loadConversations();
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
  $('#sendButton').disabled=value;
  $('#prompt').disabled=value;
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
  message('assistant','Aivyが作成・デザイン確認・テスト・セキュリティ検査を開始しました。');
  const stageNames={
    queued:'待機中',starting:'開始中',preflight:'事前確認',understand:'内容確認',plan:'設計中',build:'コード生成中',
    enhance:'AI改善中',package:'成果物準備中',design:'Design確認中',repair:'修正中',
    verify:'テスト・Security確認中',visual:'Vision Design確認中',core_checked:'Core内部確認済み',
    postflight:'独立再検証',trace:'Evidence照合',certificate:'証明書作成',done:'完了',issue:'確認事項あり'
  };
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
      const label=stageNames[job.stage]||job.stage||'処理中';
      $('#coreStatus').innerHTML='<i></i>'+esc(label);
      $('#coreStatus').classList.add('success');
    }
    if(!['completed','blocked','failed'].includes(job.status)){
      throw new Error('生成処理の状態確認がタイムアウトしました');
    }
    if(job.status==='failed'){
      throw new Error(job.error||job.message||'Build Job failed');
    }
    const result=job.result||{};
    message('assistant',result.message||job.message||'確認が完了しました。');
    await loadProjects();
    await loadConversations();
    await loadDownloads();
    await showProject(slug);
  }catch(e){
    message('assistant','生成を完了できませんでした: '+e.message);
  }finally{
    $('#coreStatus').innerHTML='<i></i>Core接続';
    $('#coreStatus').classList.add('success');
    setBusy(false);
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
  text=text.trim();if(!text||state.busy)return;
  if(!state.currentThread)await newChat();
  state.lastGoal=text;
  message('user',text);$('#prompt').value='';autoGrow();setBusy(true);
  try{
    const decision=await api('/api/v1/chat/turn',{
      method:'POST',
      body:JSON.stringify({thread_id:state.currentThread.thread_id,message:text,mode:state.currentMode})
    });
    if(decision.thread)state.currentThread=decision.thread;
    if(decision.mode)setMode(decision.mode);
    message('assistant',decision.message||'確認しました。');
    if(decision.action==='review'){
      await planGoal(decision.instruction||text);
      showBuildApproval(decision.instruction||text);
    }else if(decision.action==='build'&&decision.project_slug&&decision.instruction){
      setBusy(false);
      await executeBuild(decision.project_slug,decision.instruction);
      return;
    }else if(decision.project_slug){
      await planGoal(decision.instruction||text);
    }
    await loadConversations();
  }catch(e){
    message('assistant','Aivyが会話を処理できませんでした: '+e.message);
  }finally{
    setBusy(false);
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
      $('#modelRouteControls .route-save').forEach(button=>{
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
  if(!headline||!summary||!toggle)return;
  try{
    const [data,practice]=await Promise.all([
      api('/api/v1/growth/status'),
      api('/api/v1/practice/status')
    ]);
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
    headline.textContent='成長状態を取得できませんでした';
    summary.textContent=e.message;
  }
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
    await loadConversations();await loadProjects();await loadModelRoutes();await loadEvolutionSummary();await loadKnowledgeSummary();await loadLearningSummary();await loadSquadSummary();await loadHealthSummary();await loadBenchmarkSummary();
  }catch(e){$('#coreStatus').textContent='Core未接続';}
}
$('#composer').addEventListener('submit',e=>{e.preventDefault();send($('#prompt').value);});
$('#prompt').addEventListener('input',autoGrow);
$('#prompt').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(e.currentTarget.value);}});
$$('[data-prompt]').forEach(b=>b.onclick=()=>send(b.dataset.prompt));
$$('[data-mode]').forEach(b=>b.onclick=()=>{setMode(b.dataset.mode);$('#prompt')?.focus();});
$$('.nav-item[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$('#newChat').onclick=newChat;$('#createMission').onclick=createMission;$('#toggleGrowth').onclick=toggleGrowth;$('#runGrowth').onclick=runGrowth;$('#runPractice').onclick=runPractice;$('#openSidebar').onclick=openSidebar;$('#closeSidebar').onclick=closeSidebar;$('#overlay').onclick=closeSidebar;$('#closeInspector').onclick=()=>$('#inspector').classList.remove('open');
$('#conversationSearch').addEventListener('input',e=>loadConversations(e.target.value));
$('#themeToggle').onclick=()=>{const order=['system','light','dark'];const current=document.documentElement.dataset.theme||'system';const next=order[(order.indexOf(current)+1)%order.length];document.documentElement.dataset.theme=next;localStorage.setItem('ui-theme',next);};
document.documentElement.dataset.theme=localStorage.getItem('ui-theme')||'system';
setMode('chat');boot();
