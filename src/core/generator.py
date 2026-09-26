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
        safe_summary = html.escape(spec.summary)
        feature_labels = {
            "authentication": "ログイン/認証", "database": "データ保存", "search": "検索", "notifications": "通知",
            "payments": "決済", "admin": "管理画面", "analytics": "分析", "multi_language": "多言語", "offline": "オフライン"
        }
        chips = "".join(f'<span class="chip">{html.escape(feature_labels.get(f, f))}</span>' for f in spec.features) or '<span class="chip">基本機能</span>'
        auth = "authentication" in spec.features
        database = "database" in spec.features or auth
        app_body = self._body_for_type(spec.app_type, auth)
        index = project_dir / "index.html"
        style = project_dir / "styles.css"
        script = project_dir / "app.js"
        manifest = project_dir / "manifest.webmanifest"
        service_worker = project_dir / "sw.js"

        index.write_text(f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#101828"><title>{safe_name}</title>
<link rel="manifest" href="manifest.webmanifest"><link rel="stylesheet" href="styles.css"></head>
<body><header><div class="shell hero"><span class="eyebrow">AI App Platform</span><h1>{safe_name}</h1><p>{safe_summary}</p></div></header>
<main class="shell"><section class="meta" aria-label="アプリ情報"><div><b>種類</b><span>{html.escape(spec.app_type)}</span></div><div><b>出力先</b><span>{html.escape(', '.join(spec.targets))}</span></div></section>
<div class="chips" aria-label="機能">{chips}</div>{app_body}
<section class="card"><h2>品質</h2><p class="muted">使いやすさ・スマホ操作性・アクセシビリティを前提に生成しています。</p></section></main>
<script src="app.js"></script></body></html>''', encoding="utf-8")

        style.write_text(self._styles(), encoding="utf-8")
        script.write_text(self._script_for_type(spec.app_type, auth, database), encoding="utf-8")
        manifest.write_text(json.dumps({
            "name": spec.project_name, "short_name": spec.project_name[:20], "start_url": ".", "display": "standalone",
            "background_color": "#F7F8FC", "theme_color": "#101828", "lang": "ja"
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        service_worker.write_text("self.addEventListener('install',e=>self.skipWaiting());self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));", encoding="utf-8")

        files = [index, style, script, manifest, service_worker]
        if database:
            server = project_dir / "server.py"
            server.write_text(self._server_template(), encoding="utf-8")
            files.append(server)

        generated_manifest = project_dir / "generated_manifest.json"
        generated_manifest.write_text(json.dumps({
            "generator": "fullstack-v0.5", "type": spec.app_type, "features": spec.features, "targets": spec.targets,
            "runtime": "python-http-sqlite" if database else "static-pwa"
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append(generated_manifest)
        log_event("generator.web", f"Generated {spec.app_type} app", spec.slug)
        return files

    def _body_for_type(self, app_type: str, auth: bool) -> str:
        auth_block = '''<section class="card" id="authCard"><h2>アカウント</h2><div class="grid2"><label>メール<input id="email" type="email" autocomplete="email" placeholder="you@example.com"></label><label>パスワード<input id="password" type="password" autocomplete="current-password" placeholder="8文字以上"></label></div><div class="row"><button id="register">新規登録</button><button class="secondary" id="login">ログイン</button><button class="ghost" id="logout">ログアウト</button></div><p id="authStatus" class="muted" aria-live="polite"></p></section>''' if auth else ""
        if app_type == "todo":
            body = '<section class="card"><h2>タスク</h2><div class="row"><label class="grow">新しいタスク<input id="itemTitle" placeholder="例：資料を確認"></label><button id="addItem">追加</button></div><ul id="itemList" class="clean-list"></ul></section>'
        elif app_type == "booking":
            body = '<section class="card"><h2>予約</h2><div class="grid2"><label>お名前<input id="itemTitle" placeholder="お名前"></label><label>予約日<input id="itemValue" type="date"></label></div><button id="addItem">予約する</button><ul id="itemList" class="clean-list"></ul></section>'
        elif app_type == "inventory":
            body = '<section class="card"><h2>在庫</h2><div class="grid2"><label>商品名<input id="itemTitle" placeholder="商品名"></label><label>数量<input id="itemValue" type="number" min="0" value="1"></label></div><button id="addItem">登録</button><ul id="itemList" class="clean-list"></ul></section>'
        elif app_type == "crm":
            body = '<section class="card"><h2>顧客</h2><div class="grid2"><label>顧客名<input id="itemTitle" placeholder="顧客名"></label><label>メモ<input id="itemValue" placeholder="連絡内容など"></label></div><button id="addItem">登録</button><ul id="itemList" class="clean-list"></ul></section>'
        else:
            body = '<section class="card"><h2>データ</h2><div class="grid2"><label>タイトル<input id="itemTitle" placeholder="タイトル"></label><label>内容<input id="itemValue" placeholder="内容"></label></div><button id="addItem">保存</button><ul id="itemList" class="clean-list"></ul></section>'
        return auth_block + body + '<p id="status" class="muted" aria-live="polite"></p>'

    def _styles(self) -> str:
        return '''
:root{--color-bg:#F7F8FC;--color-surface:#fff;--color-text:#101828;--color-muted:#667085;--color-border:#E4E7EC;--color-accent:#101828;--space-1:6px;--space-2:10px;--space-3:14px;--space-4:20px;--space-5:28px;--radius:18px}
*{box-sizing:border-box}html{color-scheme:light}body{margin:0;background:var(--color-bg);color:var(--color-text);font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.55}header{background:linear-gradient(145deg,#0B1220,#1D2939);color:#fff;padding:44px 18px 34px}.shell{max-width:980px;margin:auto}.hero h1{font-size:clamp(2rem,6vw,3.7rem);line-height:1.05;margin:8px 0 12px;letter-spacing:-.04em}.hero p{max-width:720px;color:#D0D5DD;font-size:clamp(1rem,2vw,1.15rem)}.eyebrow{font-size:.78rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:#98A2B3}main{padding:var(--space-5) 18px 64px}.meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.meta div,.card{background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius);padding:var(--space-4);box-shadow:0 12px 34px rgba(16,24,40,.05)}.meta b,.meta span{display:block}.meta span,.muted{color:var(--color-muted)}.chips{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.chip{background:#EEF2FF;color:#3730A3;padding:7px 11px;border-radius:999px;font-weight:700}.card{margin:18px 0}.card h2{margin:0 0 14px;font-size:1.25rem}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.grow{flex:1 1 260px}label{display:grid;gap:6px;font-size:.92rem;font-weight:700;color:#344054}input,button{font:inherit;border-radius:13px}input{width:100%;min-height:48px;border:1px solid #D0D5DD;padding:11px 13px;background:#fff;color:#101828}button{min-height:48px;border:0;background:var(--color-accent);color:#fff;padding:11px 16px;font-weight:800;cursor:pointer}button.secondary{background:#344054}button.ghost{background:#F2F4F7;color:#344054}button:focus-visible,input:focus-visible{outline:3px solid #84ADFF;outline-offset:2px}.clean-list{list-style:none;padding:0;margin:16px 0 0;display:grid;gap:10px}.clean-list li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px;border:1px solid var(--color-border);border-radius:14px;background:#FCFCFD}.clean-list li button{min-height:44px;padding:8px 12px;background:#FEE4E2;color:#B42318}
@media(max-width:680px){header{padding-top:32px}.grid2{grid-template-columns:1fr}.row>button{flex:1 1 120px}main{padding-top:20px}.card,.meta div{padding:16px}}
'''

    def _script_for_type(self, app_type: str, auth: bool, database: bool) -> str:
        if not database:
            return '''
const list=document.querySelector('#itemList'),title=document.querySelector('#itemTitle'),value=document.querySelector('#itemValue'),status=document.querySelector('#status');
let rows=JSON.parse(localStorage.getItem('rows')||'[]');
function render(){list.innerHTML='';rows.forEach((r,i)=>{const li=document.createElement('li');const text=document.createElement('span');text.textContent=r.title+(r.value?' — '+r.value:'');const b=document.createElement('button');b.textContent='削除';b.onclick=()=>{rows.splice(i,1);save();};li.append(text,b);list.append(li);});}
function save(){localStorage.setItem('rows',JSON.stringify(rows));render();}
document.querySelector('#addItem').onclick=()=>{const t=title.value.trim();if(!t){status.textContent='入力してください';return;}rows.push({title:t,value:value?.value||''});title.value='';if(value)value.value='';save();status.textContent='保存しました';};render();
if('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(()=>{});
'''
        return f'''
let csrf='';const authRequired={str(auth).lower()};
const list=document.querySelector('#itemList'),title=document.querySelector('#itemTitle'),value=document.querySelector('#itemValue'),status=document.querySelector('#status');
async function api(path,options={{}}){{options.headers={{'Content-Type':'application/json',...(options.headers||{{}})}};if(csrf)options.headers['X-CSRF-Token']=csrf;const r=await fetch(path,options);let data={{}};try{{data=await r.json();}}catch{{}}if(!r.ok)throw new Error(data.error||'request_failed');return data;}}
function render(rows){{list.innerHTML='';for(const r of rows){{const li=document.createElement('li');const text=document.createElement('span');text.textContent=r.title+(r.value?' — '+r.value:'');const b=document.createElement('button');b.textContent='削除';b.onclick=async()=>{{try{{await api('/api/items/'+r.id,{{method:'DELETE'}});await load();}}catch(e){{status.textContent=e.message;}}}};li.append(text,b);list.append(li);}}}}
async function load(){{try{{const me=await api('/api/me');csrf=me.csrf||'';const data=await api('/api/items');render(data.items||[]);status.textContent=me.email?'ログイン中: '+me.email:'準備完了';}}catch(e){{if(authRequired)status.textContent='ログインするとデータを保存できます';else status.textContent=e.message;}}}}
document.querySelector('#addItem').onclick=async()=>{{const t=title.value.trim();if(!t){{status.textContent='入力してください';return;}}try{{await api('/api/items',{{method:'POST',body:JSON.stringify({{title:t,value:value?.value||''}})}});title.value='';if(value)value.value='';await load();}}catch(e){{status.textContent=e.message;}}}};
const email=document.querySelector('#email'),password=document.querySelector('#password'),authStatus=document.querySelector('#authStatus');
if(email){{document.querySelector('#register').onclick=async()=>{{try{{await api('/api/register',{{method:'POST',body:JSON.stringify({{email:email.value,password:password.value}})}});authStatus.textContent='登録しました';await load();}}catch(e){{authStatus.textContent=e.message;}}}};document.querySelector('#login').onclick=async()=>{{try{{await api('/api/login',{{method:'POST',body:JSON.stringify({{email:email.value,password:password.value}})}});authStatus.textContent='ログインしました';await load();}}catch(e){{authStatus.textContent=e.message;}}}};document.querySelector('#logout').onclick=async()=>{{try{{await api('/api/logout',{{method:'POST'}});csrf='';authStatus.textContent='ログアウトしました';render([]);}}catch(e){{authStatus.textContent=e.message;}}}};}}
load();if('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(()=>{{}});
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
