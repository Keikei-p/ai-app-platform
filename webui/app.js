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
  if(name==='settings'){loadModelRoutes();loadEvolutionSummary();}
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
  const card=data.card||{};const readiness=data.readiness||{};const gaps=(data.gaps||{}).items||[];const evaluation=data.evaluation||{};const release=data.release_manager||{};
  $('#agentPlan').innerHTML=`
    <div class="data-card"><h3>${esc(card.name||slug)}</h3><div class="meta"><span>${esc(card.status)}</span><span>${esc(card.quality)}</span>${evaluation.score!=null?`<span>AI評価 ${evaluation.score}/100</span>`:''}</div></div>
    <div class="plan-step"><div class="step-no">✓</div><div><strong>プレビュー</strong><p>${readiness.preview_ready?'可能':'まだ準備が必要'}</p></div></div>
    <div class="plan-step"><div class="step-no">⇩</div><div><strong>配布状態</strong><p>${(release.targets||[]).length?(release.targets||[]).map(x=>esc(x.target)+': '+esc(x.artifact_status)+' / '+esc(x.distribution_status)).join('<br>'):'Release Manager未実行'}</p></div></div>
    <div class="plan-step"><div class="step-no">!</div><div><strong>未完了</strong><p>${gaps.length?gaps.map(x=>esc(x.reason||'')).join('<br>'):'大きな未完了項目なし'}</p></div></div>`;
  $('#inspector').classList.add('open');
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
  const plan=await api('/api/v1/agent/plan',{method:'POST',body:JSON.stringify({goal:text,project_slug:state.currentThread?.project_slug||null})});
  $('#agentPlan').innerHTML=(plan.steps||[]).map((x,i)=>{
    const team=(x.specialists||[]).length?' · '+(x.specialists||[]).map(s=>({
      coordinator:'司令塔',research:'Research',architect:'Architect',coding:'Coding',design:'Design',test:'Test',security:'Security',build:'Build',release:'Release'
    }[s]||s)).join(' / '):'';
    return `<div class="plan-step"><div class="step-no">${i+1}</div><div><strong>${esc(x.title)}</strong><p>${esc(x.purpose)}${esc(team)}${x.requires_human_approval?' · 人の承認が必要':''}</p></div></div>`;
  }).join('');
  $('#inspector').classList.add('open');
  return plan;
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
  holder.innerHTML='<button class="agent-action" id="approveBuild">この内容で作る</button><p>押すまで生成は始まりません。</p>';
  $('#agentPlan').append(holder);
  $('#approveBuild').onclick=approveBuild;
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
  const target=$('#modelRouteSummary');if(!target)return;
  try{
    const data=await api('/api/v1/models/routes');
    const rows=(data.routes||[]).filter(x=>['coding','vision','research','reasoning'].includes(x.capability));
    target.textContent=rows.map(x=>{
      const r=x.effective||{};
      return x.capability+' → '+(r.provider||'none')+(r.model?' / '+r.model:'');
    }).join(' · ')||'ルート未設定';
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
async function boot(){
  try{
    const status=await api('/api/v1/status');state.csrf=status.csrf||'';
    $('#coreStatus').innerHTML='<i></i>Core接続';$('#coreStatus').classList.add('success');
    await loadConversations();await loadProjects();await loadModelRoutes();await loadEvolutionSummary();
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
