/** Offline, deterministic, functional templates (NOT AI code generation). */
import { GENERATOR_KIND } from "./static-preview.mjs";

const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[c]));
const CSS = ':root{color-scheme:dark;font:16px/1.6 system-ui,sans-serif;color:#eef6ff;background:#0d1421}' +
  '*{box-sizing:border-box}body{margin:0;min-height:100dvh;padding:22px 14px 60px;background:radial-gradient(circle at 85% 0%,#234962,transparent 48%),#0d1421}' +
  'main{width:min(800px,100%);margin:auto;padding:clamp(17px,5vw,35px);background:#ffffff0a;border:1px solid #b3dbea3d;border-radius:23px}' +
  'h1{font-size:clamp(27px,7vw,40px);margin:4px 0}.eyebrow{letter-spacing:.2em;color:#9ed9e2;font-size:11px;font-weight:800}' +
  '.panel{background:#07182791;border:1px solid #b3dbea23;border-radius:17px;padding:15px;margin:16px 0}' +
  'label{display:block;font-weight:700;margin:11px 0 5px;font-size:13px}' +
  'input,textarea,select,button{font:inherit;font-size:16px;max-width:100%}' +
  'input,textarea,select{width:100%;min-height:44px;padding:10px;border:1px solid #aecedd66;border-radius:11px;background:#091b2b;color:#eafaff}' +
  'textarea{min-height:110px}button{min-height:44px;border:0;border-radius:11px;background:#b7e8ef;color:#092a3a;padding:9px 14px;font-weight:750;cursor:pointer}' +
  'button.secondary{background:#26475c;color:#e5f6fa}button.danger{background:#592b3c;color:#ffeaf0}' +
  '.row{display:flex;gap:10px;flex-wrap:wrap}.row>*{flex:1;min-width:110px}' +
  '.item{padding:14px;margin:8px 0;border:1px solid #b1dbea33;border-radius:14px;background:#09192a;overflow-wrap:anywhere}' +
  '.done strong{text-decoration:line-through;opacity:.6}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.actions button{font-size:13px}' +
  '.muted,small,footer{color:#aac4d3;font-size:12px}p{white-space:pre-wrap;overflow-wrap:anywhere}' +
  '.hidden{display:none}.status{min-height:18px;color:#aedfb9}';

function offlineAppRuntime() {
  "use strict";
  const $ = id => document.getElementById(id);
  const kind = document.documentElement.getAttribute("data-ivy-template");
  const key = "ivy-offline-" + kind + "-v1";
  let entries=[],editing=null;
  const valid = item => item && typeof item.id === "string" &&
    typeof item.title === "string" && item.title.length <= 140 &&
    typeof item.body === "string" && item.body.length <= 5000 &&
    typeof item.done === "boolean" && ["low","normal","high"].includes(item.priority) &&
    typeof item.due === "string" && item.due.length <= 10;
  const el = (tag, text) => {
    const node=document.createElement(tag);
    if (text !== undefined) node.textContent=text;
    return node;
  };
  try {
    const data=JSON.parse(localStorage.getItem(key) || "[]");
    if(Array.isArray(data)) entries=data.filter(valid).slice(0,200);
  } catch { /* storage may be disabled in an opaque preview iframe */ }
  const save = () => {
    try {
      localStorage.setItem(key,JSON.stringify(entries));
      $("status").textContent="このブラウザに保存しました。";
    } catch {
      $("status").textContent="プレビューでは保存できません。JSONバックアップを利用してください。";
    }
  };
  const reset=()=>{
    editing=null;$("title").value="";$("body").value="";$("priority").value="normal";$("due").value="";
    $("save").textContent="追加する";
  };
  const show=()=>{
    const root=$("list"),query=$("search").value.trim().toLocaleLowerCase(),filter=$("filter").value;
    root.replaceChildren();
    const visible=entries.filter(t=>(t.title+" "+t.body).toLocaleLowerCase().includes(query) &&
      (kind!=="todo"||filter==="all"||t.done===(filter==="done")));
    $("counter").textContent="全"+entries.length+"件 / 表示"+visible.length+"件";
    if(!visible.length)root.append(el("p","該当するデータはありません。"));
    for(const item of visible){
      const card=el("section");card.className="item"+(item.done?" done":"");
      const name=el("strong",item.title);
      const meta=el("small",kind==="todo"?"優先度: "+({low:"低",normal:"通常",high:"高"}[item.priority])+
        (item.due?" · 期限: "+item.due:""):item.body.slice(0,350));
      meta.style.whiteSpace="pre-wrap";
      const buttons=el("div");buttons.className="actions";
      const add=(label,callback,cls)=>{
        const button=el("button",label);button.type="button";button.className=cls;
        button.onclick=callback;buttons.append(button);
      };
      if(kind==="todo")add(item.done?"未完了に戻す":"完了",()=>{item.done=!item.done;save();show();},"secondary");
      add("編集",()=>{
        editing=item.id;$("title").value=item.title;$("body").value=item.body;
        $("priority").value=item.priority;$("due").value=item.due;
        $("save").textContent="変更を保存";$("title").focus();
      },"secondary");
      add("削除",()=>{
        if(!confirm("この項目を削除しますか？"))return;
        entries=entries.filter(x=>x.id!==item.id);
        if(editing===item.id)reset();
        save();show();
      },"danger");
      card.append(name,meta,buttons);root.append(card);
    }
  };
  $("form").onsubmit=event=>{
    event.preventDefault();
    const title=$("title").value.trim(),body=$("body").value;
    if(!title||title.length>140||body.length>5000)return;
    if(editing){
      const item=entries.find(x=>x.id===editing);
      if(item){item.title=title;item.body=body;item.priority=$("priority").value;item.due=$("due").value;}
    } else {
      if(entries.length>=200){$("status").textContent="最大200件です。";return;}
      entries.unshift({id:Date.now()+"-"+Math.random().toString(36).slice(2),
        title,body,done:false,priority:$("priority").value,due:$("due").value});
    }
    reset();save();show();
  };
  $("reset").onclick=reset;$("search").oninput=show;$("filter").onchange=show;
  $("export").onclick=()=>{
    const url=URL.createObjectURL(new Blob([JSON.stringify(entries,null,2)],{type:"application/json"}));
    const link=el("a");link.href=url;link.download="ivy-"+kind+"-backup.json";link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  $("import").onchange=async event=>{
    const file=event.target.files?.[0];
    if(!file)return;
    try {
      if(file.size>700000)throw new Error("too_large");
      const items=JSON.parse(await file.text());
      if(!Array.isArray(items)||items.length>200||!items.every(valid))throw new Error("invalid");
      if(!confirm("既存のデータを読み込んだ内容で置き換えますか？"))return;
      entries=items.map(x=>({id:x.id,title:x.title,body:x.body,done:x.done,priority:x.priority,due:x.due}));
      reset();save();show();
    } catch { $("status").textContent="JSONファイルを読み込めません。"; }
    finally{event.target.value="";}
  };
  if(kind==="todo")$("notesFields").classList.add("hidden");
  else $("todoFields").classList.add("hidden");
  show();
}

export function chooseTemplate(prompt, specified="auto") {
  if(!["auto","todo","notes","landing"].includes(specified))throw new Error("invalid_template");
  if(specified!=="auto")return specified;
  if(/todo|to-do|タスク|やること/i.test(prompt))return "todo";
  if(/メモ|ノート|notes?/i.test(prompt))return "notes";
  return "landing";
}
export function compileInteractiveTemplate({prompt,mode}, kind) {
  if(mode!=="web"||typeof prompt!=="string"||!prompt.trim()||prompt.length>1200)throw new Error("invalid_template_request");
  if(!["todo","notes"].includes(kind))throw new Error("invalid_template");
  const title=kind==="todo"?"ToDo管理アプリ":"メモ管理アプリ";
  const html=['<!doctype html>','<!-- ivy-trusted-interactive-template:'+kind+' -->',
    '<html lang="ja" data-ivy-template="'+kind+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
    '<meta name="referrer" content="no-referrer"><title>'+title+'</title><style>'+CSS+'</style></head><body><main>',
    '<div class="eyebrow">IVY · OFFLINE WEB APP TEMPLATE</div><h1>'+title+'</h1>',
    '<p class="muted">AI生成ではなく、動作する既定テンプレートです。外部API・課金なし。</p>',
    '<details><summary>元の制作依頼</summary><p>'+escapeHTML(prompt)+'</p></details>',
    '<form class="panel" id="form"><label for="title">タイトル</label><input id="title" required maxlength="140">',
    '<div id="notesFields"><label for="body">内容</label><textarea id="body" maxlength="5000"></textarea></div>',
    '<div id="todoFields" class="row"><div><label for="priority">優先度</label><select id="priority"><option value="normal">通常</option><option value="low">低</option><option value="high">高</option></select></div><div><label for="due">期限</label><input id="due" type="date"></div></div>',
    '<div class="actions"><button id="save" type="submit">追加する</button><button class="secondary" id="reset" type="button">クリア</button></div></form>',
    '<section class="panel"><div class="row"><div><label for="search">検索</label><input id="search" placeholder="検索"></div>',
    '<div><label for="filter">状態</label><select id="filter"><option value="all">すべて</option><option value="false">未完了</option><option value="done">完了</option></select></div></div>',
    '<p id="counter" class="muted"></p><div id="list"></div></section>',
    '<section class="panel"><h2>バックアップ</h2><div class="actions"><button id="export" class="secondary" type="button">JSONに保存</button>',
    '<label>JSONを読み込む <input id="import" type="file" accept=".json,application/json"></label></div><p id="status" class="status"></p></section>',
    '<footer>プレビュー内は保存できない場合があります。HTMLをダウンロードして使用し、JSONでバックアップしてください。</footer>',
    '</main><script>('+offlineAppRuntime.toString()+')();</script></body></html>'
  ].join("\n");
  const checks=[
    {name:"bounded_output",passed:html.length<=19500},
    {name:"known_template",passed:true},
    {name:"no_external_assets",passed:!/<script[^>]+src=|<link[^>]+href=/i.test(html)},
    {name:"escaped_user_input",passed:!html.includes("<script>"+prompt)},
  ];
  if(!checks.every(x=>x.passed))throw new Error("template_validation_failed");
  return {html,checks,generator:GENERATOR_KIND,template_kind:kind};
}
