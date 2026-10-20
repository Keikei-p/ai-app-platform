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
  return status === "awaiting_hosted_worker" ? "保存済み・AI実行未接続" :
    status === "template_ready" ? "静的HTMLテンプレート完成（AI生成ではない）" :
    status === "cancelled" ? "依頼を中止" :
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
    card.append(head,stamp,body);
    const actions = document.createElement("div");
    actions.className="entry-actions";
    if (item.status === "awaiting_hosted_worker") {
      if (item.mode === "web") {
        const generate = document.createElement("button");
        generate.type="button"; generate.className="quiet";
        generate.textContent="固定HTMLプレビューを生成";
        generate.onclick=async()=>{
          if(!confirm("AI生成ではなく、安全な固定HTMLテンプレートをクラウドで作成します。続けますか？"))return;
          generate.disabled=true;
          try{
            await api("/api/v1/requests/"+encodeURIComponent(item.id)+"/build-preview",{
              method:"POST",headers:{"content-type":"application/json"},
              body:JSON.stringify({confirm:"generate_static_template"})
            });
            text("message","HTMLテンプレートを保存しました。AI生成・ビルド・公開は行っていません。");
            await refresh();
          }catch(e){ text("message","テンプレートを生成できませんでした: "+e.message); }
          finally{generate.disabled=false;}
        };
        actions.append(generate);
      }
      const cancel = document.createElement("button");
      cancel.type="button";cancel.className="quiet";cancel.textContent="依頼を中止";
      cancel.onclick=async()=>{
        if(!confirm("この未実行依頼を中止しますか？"))return;
        cancel.disabled=true;
        try {
          await api("/api/v1/requests/"+encodeURIComponent(item.id)+"/cancel",{
            method:"POST",headers:{"content-type":"application/json"},
            body:JSON.stringify({confirm:"cancel_pending"})
          });
          await refresh();
        }catch(e){text("message","中止できませんでした: "+e.message);}
        finally{cancel.disabled=false;}
      };
      actions.append(cancel);
    }
    if (item.status === "template_ready") {
      const view = document.createElement("button");view.type="button";
      view.className="quiet";view.textContent="HTMLプレビュー";
      view.onclick=()=>{
        const frame=$("previewFrame");
        frame.src="/api/v1/requests/"+encodeURIComponent(item.id)+"/preview";
        $("previewSection").hidden=false;
        $("previewSection").scrollIntoView({behavior:"smooth"});
      };
      const download = document.createElement("a");
      download.className="download-link";
      download.href="/api/v1/requests/"+encodeURIComponent(item.id)+"/download";
      download.textContent="HTMLをダウンロード";
      download.setAttribute("download","ivy-static-preview.html");
      actions.append(view,download);
    }
    if (actions.childNodes.length) card.append(actions);
    root.append(card);
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
$("closePreview").addEventListener("click",()=>{
  $("previewFrame").removeAttribute("src");
  $("previewSection").hidden=true;
});
void refresh();
document.addEventListener("visibilitychange",()=>{if(!document.hidden)void refresh()});
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(()=>{});
