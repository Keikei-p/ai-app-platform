"use strict";
const $ = id => document.getElementById(id);
const state = { loading:false, sending:false, accepting:false, pendingKey:null };
function text(id, value) { $(id).textContent = value; }
async function api(path, options = {}) {
  const response = await fetch(path, { credentials:"same-origin", cache:"no-store", ...options });
  let data = {}; try { data = await response.json(); } catch {}
  if (!response.ok || data.ok !== true) throw new Error(data.error || "connection_failed");
  return data;
}
function explainStatus(status) {
  return status === "awaiting_hosted_worker" ? "保存済み・生成エンジン接続待ち" :
    status === "review_ready" ? "結果確認待ち" : "状態未確認";
}
function showRequests(items) {
  const root = $("requests");
  root.replaceChildren();
  if (!Array.isArray(items) || items.length === 0) {
    root.textContent = "まだ依頼はありません。まずは最初の制作依頼を保存してみてください。";
    return;
  }
  for (const item of items) {
    const card = document.createElement("article"); card.className="entry";
    const head = document.createElement("strong");
    head.textContent = (item.mode === "app" ? "スマホアプリ" : "Web制作") + " / " + explainStatus(item.status);
    const stamp = document.createElement("small");
    const date = new Date(Number(item.created_at) * 1000);
    stamp.textContent = Number.isFinite(date.getTime()) ? date.toLocaleString("ja-JP") : "日時未確認";
    const body = document.createElement("p"); body.textContent = String(item.prompt || "");
    card.append(head,stamp,body); root.append(card);
  }
}
async function refresh() {
  if (state.loading) return;
  state.loading=true;
  try {
    const [status, history] = await Promise.all([
      api("/api/v1/status"),api("/api/v1/requests")
    ]);
    state.accepting = !status.paused;
    text("connection","クラウドに接続しました");
    text("workerState", status.hosted_worker_connected ? "接続済み" : "未接続");
    text("dailyCount",String(status.requests_today)+" / "+String(status.daily_limit));
    text("modeMessage", status.note || "クラウド状態を確認しました。");
    showRequests(history.requests);
  } catch(e) {
    state.accepting=false;
    text("connection", e.message==="owner_login_required" ?
      "OWNER認証が必要です。Cloudflare Accessのログインを確認してください。" :
      "接続または設定に問題があります。");
    text("workerState","未確認");
    text("modeMessage","登録結果が不明な場合、再送前に履歴を確認してください。");
  } finally { state.loading=false; $("submit").disabled = !state.accepting || state.sending; }
}
$("reload").addEventListener("click",()=>void refresh());
$("requestForm").addEventListener("submit",async event => {
  event.preventDefault();
  if (state.sending || !state.accepting) return;
  const prompt=$("prompt").value.trim(),mode=$("mode").value;
  if (!prompt) return;
  if (!state.pendingKey) state.pendingKey=crypto.randomUUID().replaceAll("-","");
  state.sending=true; $("submit").disabled=true;
  try {
    const result=await api("/api/v1/requests",{
      method:"POST",headers:{"content-type":"application/json"},
      body:JSON.stringify({prompt,mode,idempotency_key:state.pendingKey})
    });
    text("message","依頼 #"+result.request_id.slice(0,8)+" を保存しました。AI生成はまだ開始していません。");
    state.pendingKey=null; $("prompt").value="";
    await refresh();
  } catch (e) {
    text("message","保存結果を確認できません（"+e.message+"）。入力は残しました。履歴を確認してから再試行してください。");
  } finally {state.sending=false;$("submit").disabled=!state.accepting;}
});
$("stop").addEventListener("click",async()=>{
  if(!confirm("新しい制作依頼の受付を停止しますか？ 保存済みの依頼は消えません。"))return;
  $("stop").disabled=true;
  try{
    await api("/api/v1/stop",{method:"POST",headers:{"content-type":"application/json"},body:"{}"});
    text("stopResult","新しい依頼の受付を停止しました。再開には管理者による設定変更が必要です。");
    await refresh();
  }catch{text("stopResult","停止結果を確認できません。接続を確認してください。")}
  finally{$("stop").disabled=false;}
});
void refresh();
document.addEventListener("visibilitychange",()=>{if(!document.hidden)void refresh()});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(()=>{});
