const state={csrf:'',view:'home',conversations:[],projects:[],currentThread:null,lastGoal:'',pendingInstruction:null,busy:false};
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
  const titles={home:state.currentThread?.title||'新しいチャット',conversations:'最近の会話',projects:'作成したアプリ',downloads:'ダウンロード',settings:'設定'};
  $('#topbarTitle').textContent=titles[name]||'Aivy';
  closeSidebar();
  if(name==='conversations')loadConversations();
  if(name==='projects')loadProjects();
  if(name==='downloads')loadDownloads();
  if(name==='settings'){loadModelRoutes();loadEvolutionSummary();loadKnowledgeSummary();}
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
  const card=data.card||{};const readiness=data.readiness||{};const gaps=(data.gaps||{}).items||[];const evaluation=data.evaluation||{};const release=data.release_manager||{};const visual=data.visual_design||{};const certificate=data.development_certificate||{};const integrity=data.certificate_integrity||{};const latestRun=(data.agent_runs||[])[0]||null;
  const visualBlock=visual.status==='reviewed'
    ? `<div class="visual-review-card"><div class="visual-review-head"><strong>Vision Design</strong><span>${visual.score}/100</span></div><p>${esc(visual.summary||'')}</p><div class="visual-shots">
        ${['mobile.png','tablet.png','desktop.png'].map(name=>`<figure><img src="/api/v1/projects/${encodeURIComponent(slug)}/screenshots/${name}" alt="${name} screenshot"><figcaption>${name.replace('.png','')}</figcaption></figure>`).join('')}
      </div>${(visual.findings||[]).length?`<div class="visual-findings"><strong>指摘</strong><p>${(visual.findings||[]).map(esc).join('<br>')}</p></div>`:''}</div>`
    : `<div class="plan-step"><div class="step-no">◉</div><div><strong>Vision Design</strong><p>${esc(visual.summary||'スクリーンショット評価はまだありません')}</p></div></div>`;
  const traceBlock=latestRun
    ? `<div class="execution-trace"><div class="execution-trace-head"><strong>最新Aivy Execution Trace</strong><span>${esc(latestRun.status||'')}</span></div>${(latestRun.steps||[]).map(x=>`<div class="trace-row ${esc(x.status||'')}"><b>${esc(x.step_id||x.action||'step')}</b><span>${esc(x.status||'')}</span><p>${esc(x.summary||'')}</p></div>`).join('')}</div>`
    : '<div class="plan-step"><div class="step-no">◎</div><div><strong>Execution Trace</strong><p>まだBuild実行履歴はありません。</p></div></div>';
  const certificateBlock=certificate.status
    ? `<div class="certificate-card ${esc(certificate.status)}"><div class="certificate-head"><strong>Aivy Development Certificate</strong><span>${esc(certificate.status)}</span></div><p>Integrity: ${integrity.valid?'VERIFIED':'NG'} · Preflight: ${certificate.preflight_verified===true?'VERIFIED':certificate.preflight_verified===false?'NG':'N/A'} · Postflight: ${certificate.postflight_verified===true?'VERIFIED':certificate.postflight_verified===false?'NG':'N/A'} · Tests: ${certificate.tests_passed?'PASS':'NG'} · Design: ${certificate.design_passed?'PASS':'NG'} · Security: ${certificate.security_passed?'PASS':'NG'} · Trace: ${certificate.execution_trace_verified?'VERIFIED':'NG'}</p><p>Evidence: ${(certificate.evidence||[]).length}件 · 外部公開: ${esc(certificate.external_actions||'approval_required')}</p>${(certificate.blockers||[]).length?`<p class="certificate-blockers">${(certificate.blockers||[]).map(esc).join('<br>')}</p>`:''}${(!integrity.valid&&(integrity.missing||[]).length)?`<p class="certificate-blockers">Missing: ${(integrity.missing||[]).map(esc).join('<br>')}</p>`:''}${(!integrity.valid&&(integrity.mismatched||[]).length)?`<p class="certificate-blockers">Changed: ${(integrity.mismatched||[]).map(esc).join('<br>')}</p>`:''}</div>`
    : '<div class="plan-step"><div class="step-no">◇</div><div><strong>Development Certificate</strong><p>まだ証明書はありません。</p></div></div>';
  $('#agentPlan').innerHTML=`
    <div class="data-card"><h3>${esc(card.name||slug)}</h3><div class="meta"><span>${esc(card.status)}</span><span>${esc(card.quality)}</span>${evaluation.score!=null?`<span>AI評価 ${evaluation.score}/100</span>`:''}</div></div>
    <div class="health-actions"><button class="agent-action secondary" id="runHealthCheck" type="button">Aivy再点検</button><span id="healthStatus" class="meta">Tests / Design / Securityを再確認</span></div>
    ${visualBlock}
    ${traceBlock}
    ${certificateBlock}
    <div class="plan-step"><div class="step-no">✓</div><div><strong>プレビュー</strong><p>${readiness.preview_ready?'可能':'まだ準備が必要'}</p></div></div>
    <div class="plan-step"><div class="step-no">⇩</div><div><strong>配布状態</strong><p>${(release.targets||[]).length?(release.targets||[]).map(x=>esc(x.target)+': '+esc(x.artifact_status)+' / '+esc(x.distribution_status)).join('<br>'):'Release Manager未実行'}</p></div></div>
    <div class="plan-step"><div class="step-no">!</div><div><strong>未完了</strong><p>${gaps.length?gaps.map(x=>esc(x.reason||'')).join('<br>'):'大きな未完了項目なし'}</p></div></div>`;
  $('#inspector').classList.add('open');
  const healthButton=$('#runHealthCheck');
  if(healthButton)healthButton.onclick=()=>runProjectHealth(slug);
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
async function newChat(){
  const row=await api('/api/v1/conversations',{method:'POST',body:JSON.stringify({title:'新しいチャット'})});
  state.currentThread=row;$('#messages').innerHTML='';$('#welcome').hidden=false;$('#topbarTitle').textContent='新しいチャット';setView('home');await loadConversations();
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
  button.disabled=true;button.textContent='専門AIが検討中…';
  try{
    const report=await api('/api/v1/agent/council',{
      method:'POST',
      body:JSON.stringify({
        goal:state.pendingInstruction||state.lastGoal||'',
        project_slug:state.currentThread?.project_slug||null,
        context:{source:'web-user-requested-council'}
      })
    });
    if(report.status==='not_connected'){
      target.innerHTML='<div class="council-note">AIモデル未接続のため専門AI会議は実行していません。</div>';
      return;
    }
    const turns=report.turns||[];
    target.innerHTML='<div class="council-report"><div class="council-head"><strong>Aivy専門AI会議</strong><span>'+esc(report.status)+'</span></div>'+
      turns.map(x=>{
        const r=x.result||{};
        const findings=(r.findings||[]).slice(0,3);
        return '<details class="council-turn"><summary>'+esc(x.specialist)+' · '+esc(r.summary||'')+'</summary>'+
          (findings.length?'<p>'+findings.map(esc).join('<br>')+'</p>':'')+
          ((r.uncertainties||[]).length?'<p class="muted">不確実: '+(r.uncertainties||[]).slice(0,2).map(esc).join(' / ')+'</p>':'')+
          '</details>';
      }).join('')+
      '<div class="council-final"><strong>まとめ</strong><p>'+esc(report.summary||'')+'</p></div></div>';
  }catch(e){
    target.innerHTML='<div class="council-note error">専門AI会議を実行できませんでした: '+esc(e.message)+'</div>';
  }finally{
    button.disabled=false;button.textContent='専門AIで検討';
  }
}
async function executeBuild(slug,instruction){
  setBusy(true);
  message('assistant','Aivyが作成・デザイン確認・テスト・セキュリティ検査を開始しました。');
  const stageNames={
    queued:'待機中',starting:'開始中',understand:'内容確認',plan:'設計中',build:'コード生成中',
    enhance:'AI改善中',package:'成果物準備中',design:'Design確認中',repair:'修正中',
    verify:'テスト・Security確認中',visual:'Vision Design確認中',done:'完了',issue:'確認事項あり'
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
      body:JSON.stringify({thread_id:state.currentThread.thread_id,message:'この内容で作る'})
    });
    if(decision.thread)state.currentThread=decision.thread;
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
      body:JSON.stringify({thread_id:state.currentThread.thread_id,message:text})
    });
    if(decision.thread)state.currentThread=decision.thread;
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
async function boot(){
  try{
    const status=await api('/api/v1/status');state.csrf=status.csrf||'';
    $('#coreStatus').innerHTML='<i></i>Core接続';$('#coreStatus').classList.add('success');
    await loadConversations();await loadProjects();await loadModelRoutes();await loadEvolutionSummary();await loadKnowledgeSummary();
  }catch(e){$('#coreStatus').textContent='Core未接続';}
}
$('#composer').addEventListener('submit',e=>{e.preventDefault();send($('#prompt').value);});
$('#prompt').addEventListener('input',autoGrow);
$('#prompt').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send(e.currentTarget.value);}});
$$('[data-prompt]').forEach(b=>b.onclick=()=>send(b.dataset.prompt));
$$('.nav-item[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));
$('#newChat').onclick=newChat;$('#openSidebar').onclick=openSidebar;$('#closeSidebar').onclick=closeSidebar;$('#overlay').onclick=closeSidebar;$('#closeInspector').onclick=()=>$('#inspector').classList.remove('open');
$('#conversationSearch').addEventListener('input',e=>loadConversations(e.target.value));
$('#themeToggle').onclick=()=>{const order=['system','light','dark'];const current=document.documentElement.dataset.theme||'system';const next=order[(order.indexOf(current)+1)%order.length];document.documentElement.dataset.theme=next;localStorage.setItem('ui-theme',next);};
document.documentElement.dataset.theme=localStorage.getItem('ui-theme')||'system';
boot();
