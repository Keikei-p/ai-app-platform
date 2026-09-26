from __future__ import annotations
import html
import json
from pathlib import Path
from .database import log_event
from .app_spec import AppSpec

class StarterGenerator:
    def generate_web(self, project_dir: Path, project_name: str, instruction: str, slug: str) -> list[Path]:
        spec = AppSpec(project_name, slug, instruction, "generic", [], ["web"])
        return self.generate_from_spec(project_dir, spec)

    def generate_from_spec(self, project_dir: Path, spec: AppSpec) -> list[Path]:
        safe_name = html.escape(spec.project_name)
        context = spec.usage_context.strip() or spec.summary.splitlines()[0].strip()
        safe_context = html.escape(context[:500])
        theme = spec.design_style if spec.design_style in {"minimal", "premium", "modern", "friendly", "business"} else "modern"
        feature_labels = {
            "authentication": "ログイン", "database": "データ保存", "search": "検索", "notifications": "通知",
            "payments": "決済", "admin": "管理者", "analytics": "分析", "multi_language": "多言語", "offline": "オフライン"
        }
        chips = "".join(
            f'<span class="feature-chip">{html.escape(feature_labels.get(feature, feature))}</span>'
            for feature in spec.features
        )
        auth = "authentication" in spec.features
        database = "database" in spec.features or auth
        app_body = self._body_for_type(spec.app_type, auth)
        headline, eyebrow = self._headline_for_type(spec.app_type)

        index = project_dir / "index.html"
        style = project_dir / "styles.css"
        script = project_dir / "app.js"
        manifest = project_dir / "manifest.webmanifest"
        service_worker = project_dir / "sw.js"

        index.write_text(f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#111827">
<title>{safe_name}</title>
<link rel="manifest" href="manifest.webmanifest">
<link rel="stylesheet" href="styles.css">
</head>
<body data-theme="{html.escape(theme)}" data-app-type="{html.escape(spec.app_type)}">
<header class="topbar">
  <div class="shell nav">
    <a class="brand" href="#" aria-label="{safe_name} ホーム">{safe_name}</a>
    <div class="nav-actions">
      {chips}
      <span class="status-badge"><span class="status-dot"></span>利用可能</span>
    </div>
  </div>
</header>
<main class="shell">
  <section class="hero">
    <div class="hero-copy">
      <span class="eyebrow">{eyebrow}</span>
      <h1>{headline}</h1>
      <p>{safe_context}</p>
    </div>
  </section>
  {app_body}
</main>
<footer class="shell app-footer">© {safe_name}</footer>
<script src="app.js"></script>
</body>
</html>''', encoding="utf-8")

        style.write_text(self._styles(), encoding="utf-8")
        script.write_text(self._script_for_type(spec.app_type, auth, database), encoding="utf-8")
        manifest.write_text(json.dumps({
            "name": spec.project_name,
            "short_name": spec.project_name[:20],
            "start_url": ".",
            "display": "standalone",
            "background_color": "#F5F6F8",
            "theme_color": "#111827",
            "lang": "ja",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        service_worker.write_text(
            "self.addEventListener('install',e=>self.skipWaiting());"
            "self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));",
            encoding="utf-8",
        )

        files = [index, style, script, manifest, service_worker]
        if database:
            server = project_dir / "server.py"
            server.write_text(self._server_template(), encoding="utf-8")
            files.append(server)

        generated_manifest = project_dir / "generated_manifest.json"
        generated_manifest.write_text(json.dumps({
            "generator": "fullstack-v0.6",
            "type": spec.app_type,
            "features": spec.features,
            "targets": spec.targets,
            "design_style": spec.design_style,
            "usage_context": spec.usage_context,
            "runtime": "python-http-sqlite" if database else "static-pwa",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append(generated_manifest)
        log_event("generator.web", f"Generated {spec.app_type} app", spec.slug)
        return files

    @staticmethod
    def _headline_for_type(app_type: str) -> tuple[str, str]:
        mapping = {
            "booking": ("予約を、迷わずスムーズに。", "BOOKING"),
            "todo": ("やることを整理して、次の一手を明確に。", "TASKS"),
            "inventory": ("在庫の今を、ひと目で把握。", "INVENTORY"),
            "crm": ("顧客との次のアクションを見逃さない。", "CUSTOMERS"),
            "dashboard": ("数字から、次にやることが見える。", "DASHBOARD"),
            "ecommerce": ("商品を見つけやすく、買いやすく。", "STORE"),
        }
        return mapping.get(app_type, ("必要な情報と操作を、ひとつの画面に。", "WORKSPACE"))

    def _body_for_type(self, app_type: str, auth: bool) -> str:
        auth_block = '''<section class="panel auth-panel" id="authCard">
<div class="section-heading"><div><span class="section-kicker">ACCOUNT</span><h2>アカウント</h2></div><p>自分のデータを安全に管理します。</p></div>
<div class="form-grid"><label>メール<input id="email" type="email" autocomplete="email" placeholder="you@example.com"></label><label>パスワード<input id="password" type="password" autocomplete="current-password" placeholder="8文字以上"></label></div>
<div class="button-row"><button id="register">新規登録</button><button class="secondary" id="login">ログイン</button><button class="ghost" id="logout">ログアウト</button></div>
<p id="authStatus" class="feedback" aria-live="polite"></p></section>''' if auth else ""

        if app_type == "booking":
            body = '''<section class="stats-grid" aria-label="予約状況"><div class="stat-card"><span>本日の予約</span><strong id="statPrimary">0</strong><small>件</small></div><div class="stat-card"><span>受付状態</span><strong class="text-stat">受付中</strong><small>オンライン</small></div><div class="stat-card"><span>次の確認</span><strong class="text-stat">予約一覧</strong><small>最新順</small></div></section>
<section class="content-grid"><section class="panel"><div class="section-heading"><div><span class="section-kicker">NEW BOOKING</span><h2>予約を追加</h2></div><p>必要事項を入力して予約を登録します。</p></div>
<div class="form-grid"><label>お名前<input id="itemTitle" placeholder="例：山田 太郎"></label><label>サービス<select id="extraA"><option>カット</option><option>カラー</option><option>相談</option></select></label><label>担当<select id="extraB"><option>おまかせ</option><option>担当A</option><option>担当B</option></select></label><label>予約日<input id="itemValue" type="date"></label><label>時間<input id="extraC" type="time"></label></div>
<button id="addItem" class="full-button">予約を登録</button><p id="status" class="feedback" aria-live="polite"></p></section>
<section class="panel"><div class="section-heading"><div><span class="section-kicker">BOOKINGS</span><h2>予約一覧</h2></div><p>登録した予約を確認できます。</p></div><ul id="itemList" class="clean-list"></ul><div id="emptyState" class="empty-state">まだ予約はありません。</div></section></section>'''
        elif app_type == "todo":
            body = '''<section class="stats-grid" aria-label="タスク状況"><div class="stat-card"><span>登録タスク</span><strong id="statPrimary">0</strong><small>件</small></div><div class="stat-card"><span>今日の状態</span><strong class="text-stat">集中</strong><small>優先順位を整理</small></div><div class="stat-card"><span>表示</span><strong class="text-stat">最新順</strong><small>自動更新</small></div></section>
<section class="content-grid"><section class="panel"><div class="section-heading"><div><span class="section-kicker">NEW TASK</span><h2>タスクを追加</h2></div><p>やることと期限を登録します。</p></div>
<div class="form-grid"><label class="wide">タスク名<input id="itemTitle" placeholder="例：提案資料を仕上げる"></label><label>期限<input id="itemValue" type="date"></label><label>優先度<select id="extraA"><option>通常</option><option>高</option><option>低</option></select></label></div>
<button id="addItem" class="full-button">タスクを追加</button><p id="status" class="feedback" aria-live="polite"></p></section>
<section class="panel"><div class="section-heading"><div><span class="section-kicker">TASKS</span><h2>タスク一覧</h2></div><p>登録した内容を最新順で表示します。</p></div><ul id="itemList" class="clean-list"></ul><div id="emptyState" class="empty-state">まだタスクはありません。</div></section></section>'''
        elif app_type == "inventory":
            body = '''<section class="stats-grid"><div class="stat-card"><span>登録商品</span><strong id="statPrimary">0</strong><small>件</small></div><div class="stat-card"><span>管理状態</span><strong class="text-stat">最新</strong><small>在庫を確認</small></div><div class="stat-card"><span>更新</span><strong class="text-stat">即時</strong><small>ローカル反映</small></div></section>
<section class="content-grid"><section class="panel"><div class="section-heading"><div><span class="section-kicker">STOCK</span><h2>在庫を登録</h2></div><p>商品と現在数を入力します。</p></div><div class="form-grid"><label class="wide">商品名<input id="itemTitle" placeholder="商品名"></label><label>数量<input id="itemValue" type="number" min="0" value="1"></label></div><button id="addItem" class="full-button">在庫を登録</button><p id="status" class="feedback"></p></section><section class="panel"><div class="section-heading"><div><span class="section-kicker">ITEMS</span><h2>在庫一覧</h2></div><p>登録済みの商品を確認します。</p></div><ul id="itemList" class="clean-list"></ul><div id="emptyState" class="empty-state">在庫データはまだありません。</div></section></section>'''
        elif app_type == "crm":
            body = '''<section class="stats-grid"><div class="stat-card"><span>顧客</span><strong id="statPrimary">0</strong><small>件</small></div><div class="stat-card"><span>管理</span><strong class="text-stat">フォロー</strong><small>次の行動を記録</small></div><div class="stat-card"><span>表示</span><strong class="text-stat">最新順</strong><small>更新履歴</small></div></section>
<section class="content-grid"><section class="panel"><div class="section-heading"><div><span class="section-kicker">CUSTOMER</span><h2>顧客を登録</h2></div><p>顧客名と次のアクションを記録します。</p></div><div class="form-grid"><label class="wide">顧客名<input id="itemTitle" placeholder="会社名・お名前"></label><label class="wide">次のアクション<input id="itemValue" placeholder="例：金曜に見積もり送付"></label></div><button id="addItem" class="full-button">顧客を登録</button><p id="status" class="feedback"></p></section><section class="panel"><div class="section-heading"><div><span class="section-kicker">CUSTOMERS</span><h2>顧客一覧</h2></div><p>次の対応を見失わないための一覧です。</p></div><ul id="itemList" class="clean-list"></ul><div id="emptyState" class="empty-state">顧客データはまだありません。</div></section></section>'''
        else:
            body = '''<section class="stats-grid"><div class="stat-card"><span>登録データ</span><strong id="statPrimary">0</strong><small>件</small></div><div class="stat-card"><span>状態</span><strong class="text-stat">準備完了</strong><small>すぐ使えます</small></div><div class="stat-card"><span>表示</span><strong class="text-stat">シンプル</strong><small>主要操作を優先</small></div></section>
<section class="content-grid"><section class="panel"><div class="section-heading"><div><span class="section-kicker">NEW ITEM</span><h2>データを追加</h2></div><p>必要な情報を登録します。</p></div><div class="form-grid"><label class="wide">タイトル<input id="itemTitle" placeholder="タイトル"></label><label class="wide">内容<input id="itemValue" placeholder="内容"></label></div><button id="addItem" class="full-button">保存</button><p id="status" class="feedback"></p></section><section class="panel"><div class="section-heading"><div><span class="section-kicker">ITEMS</span><h2>一覧</h2></div><p>保存したデータを確認できます。</p></div><ul id="itemList" class="clean-list"></ul><div id="emptyState" class="empty-state">まだデータはありません。</div></section></section>'''
        return auth_block + body

    def _styles(self) -> str:
        return '''
:root{--color-bg:#F5F6F8;--color-surface:#FFFFFF;--color-text:#111827;--color-muted:#6B7280;--color-border:#E5E7EB;--color-accent:#111827;--color-accent-soft:#EEF2FF;--space-1:6px;--space-2:10px;--space-3:14px;--space-4:20px;--space-5:28px;--space-6:40px;--radius-sm:12px;--radius:20px;--shadow:0 18px 50px rgba(17,24,39,.06)}
*{box-sizing:border-box}html{color-scheme:light}body{margin:0;background:var(--color-bg);color:var(--color-text);font-family:Inter,"Yu Gothic UI","Hiragino Sans",system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased}
body[data-theme="premium"]{--color-bg:#F6F3EE;--color-text:#211D18;--color-border:#E5DED3;--color-accent:#211D18;--color-accent-soft:#EFE7DB}
body[data-theme="friendly"]{--color-bg:#FFF8F3;--color-text:#342A27;--color-border:#F0DDD2;--color-accent:#8B5E4B;--color-accent-soft:#FBE9DF}
body[data-theme="business"]{--color-bg:#F3F6F9;--color-text:#122033;--color-border:#DCE3EA;--color-accent:#183B66;--color-accent-soft:#E7EEF7}
body[data-theme="minimal"]{--color-bg:#FAFAFA;--color-text:#181818;--color-border:#E7E7E7;--color-accent:#181818;--color-accent-soft:#F0F0F0}
.shell{width:min(1120px,calc(100% - 36px));margin-inline:auto}.topbar{position:sticky;top:0;z-index:20;background:rgba(255,255,255,.88);backdrop-filter:blur(18px);border-bottom:1px solid rgba(229,231,235,.85)}.nav{min-height:68px;display:flex;align-items:center;justify-content:space-between;gap:18px}.brand{color:var(--color-text);text-decoration:none;font-weight:800;letter-spacing:-.03em;font-size:1.05rem}.nav-actions{display:flex;align-items:center;justify-content:flex-end;gap:7px;flex-wrap:wrap}.feature-chip,.status-badge{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--color-border);background:#fff;border-radius:999px;padding:7px 10px;font-size:.76rem;font-weight:700;color:#4B5563}.status-dot{width:7px;height:7px;border-radius:50%;background:#22C55E}
.hero{padding:72px 0 34px}.hero-copy{max-width:850px}.eyebrow,.section-kicker{font-size:.72rem;font-weight:900;letter-spacing:.14em;color:#7C8290}.hero h1{font-size:clamp(2.45rem,6vw,4.9rem);line-height:1.02;letter-spacing:-.06em;margin:12px 0 18px;max-width:900px}.hero p{margin:0;color:var(--color-muted);font-size:clamp(1rem,2vw,1.16rem);max-width:760px}
.stats-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:10px 0 18px}.stat-card{background:rgba(255,255,255,.72);border:1px solid var(--color-border);border-radius:var(--radius);padding:20px;box-shadow:0 8px 30px rgba(17,24,39,.035)}.stat-card span,.stat-card small{display:block;color:var(--color-muted);font-size:.82rem}.stat-card strong{font-size:2rem;line-height:1.1;letter-spacing:-.04em}.stat-card .text-stat{font-size:1.15rem;margin-top:7px}.content-grid{display:grid;grid-template-columns:minmax(0,.92fr) minmax(0,1.08fr);gap:18px;align-items:start}.panel{background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius);padding:24px;box-shadow:var(--shadow);margin-bottom:18px}.section-heading{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:20px}.section-heading h2{margin:3px 0 0;font-size:1.28rem;letter-spacing:-.025em}.section-heading p{margin:0;max-width:290px;color:var(--color-muted);font-size:.88rem}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.form-grid .wide{grid-column:1/-1}label{display:grid;gap:7px;color:#374151;font-size:.88rem;font-weight:750}input,select,button{font:inherit;border-radius:var(--radius-sm)}input,select{width:100%;min-height:50px;border:1px solid #D1D5DB;background:#FBFBFC;color:var(--color-text);padding:12px 14px}input:hover,select:hover{border-color:#B9BEC7}input:focus-visible,select:focus-visible,button:focus-visible{outline:3px solid #A5B4FC;outline-offset:2px}button{min-height:48px;border:0;background:var(--color-accent);color:#fff;padding:11px 17px;font-weight:800;cursor:pointer;transition:transform .14s ease,opacity .14s ease}button:hover{transform:translateY(-1px)}button.secondary{background:#374151}button.ghost{background:#F3F4F6;color:#374151}.button-row{display:flex;gap:9px;flex-wrap:wrap;margin-top:15px}.full-button{width:100%;margin-top:16px}.feedback{min-height:1.5em;color:var(--color-muted);font-size:.88rem}.clean-list{list-style:none;padding:0;margin:0;display:grid;gap:9px}.clean-list li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 15px;border:1px solid var(--color-border);border-radius:14px;background:#FCFCFD}.clean-list li span{min-width:0;overflow-wrap:anywhere}.clean-list li button{min-height:44px;padding:7px 11px;background:#FFF1F1;color:#A12525}.empty-state{border:1px dashed #D7DAE0;border-radius:14px;padding:28px;text-align:center;color:#8A909B;background:#FAFAFB}.app-footer{padding:25px 0 55px;color:#9CA3AF;font-size:.78rem}
@media(max-width:800px){.nav{min-height:60px}.nav-actions .feature-chip{display:none}.hero{padding:46px 0 24px}.hero h1{font-size:clamp(2.15rem,12vw,3.5rem)}.stats-grid{grid-template-columns:1fr}.content-grid{grid-template-columns:1fr}.section-heading{display:block}.section-heading p{margin-top:7px}.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}.panel{padding:18px}.shell{width:min(100% - 24px,1120px)}}
'''

    def _script_for_type(self, app_type: str, auth: bool, database: bool) -> str:
        return f'''
const appType={json.dumps(app_type)};
const authRequired={str(auth).lower()};
const list=document.querySelector('#itemList');
const title=document.querySelector('#itemTitle');
const value=document.querySelector('#itemValue');
const status=document.querySelector('#status');
const emptyState=document.querySelector('#emptyState');
const statPrimary=document.querySelector('#statPrimary');
let csrf='';
let localRows=[];
function extra(id){{const node=document.querySelector(id);return node?node.value.trim():'';}}
function payload(){{
  const baseTitle=title?.value.trim()||'';
  if(appType==='booking'){{
    const details=[extra('#extraA'),extra('#extraB'),value?.value||'',extra('#extraC')].filter(Boolean).join(' / ');
    return {{title:baseTitle,value:details}};
  }}
  if(appType==='todo'){{
    const details=[value?.value||'',extra('#extraA')].filter(Boolean).join(' / ');
    return {{title:baseTitle,value:details}};
  }}
  return {{title:baseTitle,value:value?.value||''}};
}}
function clearForm(){{
  if(title)title.value='';
  if(value){{if(value.type==='number')value.value='1';else value.value='';}}
}}
function render(rows){{
  list.innerHTML='';
  if(emptyState)emptyState.hidden=rows.length>0;
  if(statPrimary)statPrimary.textContent=String(rows.length);
  for(const r of rows){{
    const li=document.createElement('li');
    const text=document.createElement('span');
    text.textContent=r.title+(r.value?'  ·  '+r.value:'');
    const b=document.createElement('button');
    b.textContent='削除';
    b.setAttribute('aria-label',r.title+'を削除');
    b.onclick=()=>removeItem(r.id);
    li.append(text,b);
    list.append(li);
  }}
}}
async function removeItem(id){{
  if({str(database).lower()}){{
    try{{await api('/api/items/'+id,{{method:'DELETE'}});await load();}}
    catch(e){{status.textContent=e.message;}}
  }}else{{
    localRows=localRows.filter((_,index)=>index!==id);
    localStorage.setItem('rows',JSON.stringify(localRows));
    render(localRows.map((row,index)=>({{...row,id:index}})));
  }}
}}
async function api(path,options={{}}){{
  options.headers={{'Content-Type':'application/json',...(options.headers||{{}})}};
  if(csrf)options.headers['X-CSRF-Token']=csrf;
  const r=await fetch(path,options);
  let data={{}};try{{data=await r.json();}}catch{{}}
  if(!r.ok)throw new Error(data.error||'request_failed');
  return data;
}}
async function load(){{
  if(!{str(database).lower()}){{
    localRows=JSON.parse(localStorage.getItem('rows')||'[]');
    render(localRows.map((row,index)=>({{...row,id:index}})));
    return;
  }}
  try{{
    const me=await api('/api/me');csrf=me.csrf||'';
    const data=await api('/api/items');render(data.items||[]);
    if(status)status.textContent=me.email?'ログイン中: '+me.email:'準備完了';
  }}catch(e){{
    render([]);
    if(status)status.textContent=authRequired?'ログインするとデータを保存できます':e.message;
  }}
}}
document.querySelector('#addItem').onclick=async()=>{{
  const item=payload();
  if(!item.title){{status.textContent='必須項目を入力してください';return;}}
  if({str(database).lower()}){{
    try{{
      await api('/api/items',{{method:'POST',body:JSON.stringify(item)}});
      clearForm();await load();status.textContent='登録しました';
    }}catch(e){{status.textContent=e.message;}}
  }}else{{
    localRows.push(item);localStorage.setItem('rows',JSON.stringify(localRows));
    clearForm();render(localRows.map((row,index)=>({{...row,id:index}})));status.textContent='保存しました';
  }}
}};
const email=document.querySelector('#email'),password=document.querySelector('#password'),authStatus=document.querySelector('#authStatus');
if(email){{
  document.querySelector('#register').onclick=async()=>{{try{{await api('/api/register',{{method:'POST',body:JSON.stringify({{email:email.value,password:password.value}})}});authStatus.textContent='登録しました';await load();}}catch(e){{authStatus.textContent=e.message;}}}};
  document.querySelector('#login').onclick=async()=>{{try{{await api('/api/login',{{method:'POST',body:JSON.stringify({{email:email.value,password:password.value}})}});authStatus.textContent='ログインしました';await load();}}catch(e){{authStatus.textContent=e.message;}}}};
  document.querySelector('#logout').onclick=async()=>{{try{{await api('/api/logout',{{method:'POST'}});csrf='';authStatus.textContent='ログアウトしました';render([]);}}catch(e){{authStatus.textContent=e.message;}}}};
}}
load();
if('serviceWorker' in navigator)navigator.serviceWorker.register('./sw.js').catch(()=>{{}});
'''

    def _server_template(self) -> str:
        return r'''from __future__ import annotations
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from http.cookies import SimpleCookie
import argparse, hashlib, json, os, secrets, sqlite3, time
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parent
DB=ROOT/'app_data.db'
MAX_BODY=1024*1024

@contextmanager
def db():
    c=sqlite3.connect(DB);c.row_factory=sqlite3.Row
    try:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,csrf TEXT NOT NULL,created_at INTEGER NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT NOT NULL,value TEXT NOT NULL DEFAULT '',created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
        """)
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def hash_pw(password,salt_hex):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt_hex),210000).hex()

def make_user(email,password):
    email=email.strip().lower()
    if '@' not in email or len(password)<8: raise ValueError('メールと8文字以上のパスワードが必要です')
    salt=secrets.token_hex(16)
    with db() as c:
        try:
            cur=c.execute('INSERT INTO users(email,password_hash,salt,created_at) VALUES(?,?,?,?)',(email,hash_pw(password,salt),salt,int(time.time())))
        except sqlite3.IntegrityError: raise ValueError('このメールは登録済みです')
        return cur.lastrowid

def auth_user(email,password):
    with db() as c:r=c.execute('SELECT * FROM users WHERE email=?',(email.strip().lower(),)).fetchone()
    return int(r['id']) if r and secrets.compare_digest(r['password_hash'],hash_pw(password,r['salt'])) else None

def new_session(uid):
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
    with db() as c:c.execute('INSERT INTO sessions(token,user_id,csrf,created_at) VALUES(?,?,?,?)',(token,uid,csrf,int(time.time())))
    return token,csrf

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def log_message(self,fmt,*args):pass
    def _json(self,status,data,cookie=None):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store')
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(raw)
    def _body(self):
        n=int(self.headers.get('Content-Length') or 0)
        if n>MAX_BODY:raise ValueError('request_too_large')
        return json.loads(self.rfile.read(n) or b'{}')
    def _session(self):
        c=SimpleCookie(self.headers.get('Cookie',''));token=c.get('session')
        if not token:return None
        with db() as conn:return conn.execute('SELECT s.token,s.user_id,s.csrf,u.email FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?',(token.value,)).fetchone()
    def _require(self,csrf=False):
        s=self._session()
        if not s:self._json(401,{'error':'login_required'});return None
        if csrf and not secrets.compare_digest(str(s['csrf']),self.headers.get('X-CSRF-Token','')):
            self._json(403,{'error':'csrf_failed'});return None
        return s
    def do_GET(self):
        p=urlparse(self.path).path
        if p=='/api/me':
            s=self._require()
            if s:self._json(200,{'email':s['email'],'csrf':s['csrf']})
            return
        if p=='/api/items':
            s=self._require()
            if not s:return
            with db() as c:rows=c.execute('SELECT id,title,value,created_at,updated_at FROM items WHERE user_id=? ORDER BY id DESC',(s['user_id'],)).fetchall()
            self._json(200,{'items':[dict(r) for r in rows]});return
        return super().do_GET()
    def do_POST(self):
        p=urlparse(self.path).path
        try:data=self._body()
        except Exception as e:self._json(400,{'error':str(e)});return
        if p=='/api/register':
            try:uid=make_user(str(data.get('email','')),str(data.get('password','')));token,csrf=new_session(uid);self._json(201,{'ok':True,'csrf':csrf},f'session={token}; HttpOnly; SameSite=Lax; Path=/')
            except ValueError as e:self._json(400,{'error':str(e)})
            return
        if p=='/api/login':
            uid=auth_user(str(data.get('email','')),str(data.get('password','')))
            if not uid:self._json(401,{'error':'メールまたはパスワードが違います'});return
            token,csrf=new_session(uid);self._json(200,{'ok':True,'csrf':csrf},f'session={token}; HttpOnly; SameSite=Lax; Path=/');return
        if p=='/api/logout':
            s=self._session()
            if s:
                with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(s['token'],))
            self._json(200,{'ok':True},'session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/');return
        if p=='/api/items':
            s=self._require(csrf=True)
            if not s:return
            title=str(data.get('title','')).strip()[:200];value=str(data.get('value',''))[:2000]
            if not title:self._json(400,{'error':'title_required'});return
            now=int(time.time())
            with db() as c:cur=c.execute('INSERT INTO items(user_id,title,value,created_at,updated_at) VALUES(?,?,?,?,?)',(s['user_id'],title,value,now,now))
            self._json(201,{'ok':True,'id':cur.lastrowid});return
        if p=='/api/password':
            s=self._require(csrf=True)
            if not s:return
            current=str(data.get('current_password',''));new=str(data.get('new_password',''))
            if len(new)<8:self._json(400,{'error':'new_password_too_short'});return
            if not auth_user(s['email'],current):self._json(403,{'error':'current_password_invalid'});return
            salt=secrets.token_hex(16)
            with db() as c:c.execute('UPDATE users SET password_hash=?,salt=? WHERE id=?',(hash_pw(new,salt),salt,s['user_id']))
            self._json(200,{'ok':True});return
        if p=='/api/account':
            s=self._require(csrf=True)
            if not s:return
            if not auth_user(s['email'],str(data.get('current_password',''))):self._json(403,{'error':'current_password_invalid'});return
            with db() as c:
                c.execute('DELETE FROM items WHERE user_id=?',(s['user_id'],));c.execute('DELETE FROM sessions WHERE user_id=?',(s['user_id'],));c.execute('DELETE FROM users WHERE id=?',(s['user_id'],))
            self._json(200,{'ok':True},'session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/');return
        self._json(404,{'error':'not_found'})
    def do_PUT(self):
        p=urlparse(self.path).path;s=self._require(csrf=True)
        if not s:return
        try:item_id=int(p.rsplit('/',1)[1]);data=self._body()
        except Exception:self._json(400,{'error':'bad_request'});return
        title=str(data.get('title','')).strip()[:200];value=str(data.get('value',''))[:2000]
        with db() as c:cur=c.execute('UPDATE items SET title=?,value=?,updated_at=? WHERE id=? AND user_id=?',(title,value,int(time.time()),item_id,s['user_id']))
        self._json(200 if cur.rowcount else 404,{'ok':bool(cur.rowcount)})
    def do_DELETE(self):
        p=urlparse(self.path).path;s=self._require(csrf=True)
        if not s:return
        try:item_id=int(p.rsplit('/',1)[1])
        except Exception:self._json(400,{'error':'bad_request'});return
        with db() as c:cur=c.execute('DELETE FROM items WHERE id=? AND user_id=?',(item_id,s['user_id']))
        self._json(200 if cur.rowcount else 404,{'ok':bool(cur.rowcount)})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    if args.host not in ('127.0.0.1','localhost') and os.environ.get('AI_APP_ALLOW_LAN')!='1':raise SystemExit('Refusing non-loopback bind without AI_APP_ALLOW_LAN=1')
    print(f'http://{args.host}:{args.port}',flush=True);ThreadingHTTPServer((args.host,args.port),Handler).serve_forever()
'''
