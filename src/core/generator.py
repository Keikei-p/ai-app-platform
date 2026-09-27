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
        theme = self._resolve_theme(spec)
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
      <button class="icon-button" id="themeToggle" type="button" aria-label="表示テーマを切り替える" title="テーマ: システム">◐</button>
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
<div id="toast" class="toast" role="status" aria-live="polite" aria-atomic="true"></div>
<dialog id="confirmDialog" class="confirm-dialog">
  <form method="dialog">
    <div class="dialog-icon">?</div>
    <h2>確認</h2>
    <p id="confirmMessage">この操作を続けますか？</p>
    <div class="dialog-actions">
      <button value="cancel" class="ghost">キャンセル</button>
      <button value="ok">続ける</button>
    </div>
  </form>
</dialog>
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
            "generator": "fullstack-v0.8",
            "type": spec.app_type,
            "features": spec.features,
            "targets": spec.targets,
            "design_style": spec.design_style,
            "resolved_theme": theme,
            "usage_context": spec.usage_context,
            "runtime": "python-http-sqlite" if database else "static-pwa",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        files.append(generated_manifest)
        log_event("generator.web", f"Generated {spec.app_type} app", spec.slug)
        return files

    @staticmethod
    def _resolve_theme(spec: AppSpec) -> str:
        style = (spec.design_style or "").strip().lower()
        context = " ".join([spec.summary or "", spec.usage_context or "", spec.app_type or ""]).lower()
        direct = {
            "minimal": "minimal",
            "premium": "premium",
            "modern": "modern",
            "friendly": "friendly",
            "business": "business",
            "soft": "soft",
            "finance": "finance",
            "youthful": "youthful",
            "future": "future",
            "dark": "dark",
        }
        if style in direct:
            return direct[style]
        if any(word in style + context for word in ("美容", "サロン", "女性向け", "やわらか", "柔らか", "上品")):
            return "soft"
        if any(word in style + context for word in ("金融", "投資", "資産", "会計", "請求", "bank", "finance")):
            return "finance"
        if any(word in style + context for word in ("若者", "学生", "ポップ", "カジュアル", "creator")):
            return "youthful"
        if any(word in style + context for word in ("未来的", "近未来", "aiっぽ", "futur", "cyber")):
            return "future"
        if any(word in style + context for word in ("ダーク", "dark mode", "darkmode")):
            return "dark"
        if any(word in style + context for word in ("apple", "アップル")):
            return "minimal"
        if spec.app_type == "social_automation":
            return "youthful"
        return "modern"

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
        return r'''
:root{
  --color-bg:#F7F7F8;--color-surface:#FFFFFF;--color-surface-soft:#FBFBFC;--color-text:#18181B;
  --color-muted:#71717A;--color-border:#E8E8EC;--color-accent:#6558F5;--color-accent-hover:#5749E8;
  --color-accent-soft:#F0EEFF;--color-success:#15803D;--color-danger:#B42318;--focus:#A7A0FF;
  --space-1:6px;--space-2:10px;--space-3:14px;--space-4:20px;--space-5:28px;--space-6:40px;
  --radius-xs:10px;--radius-sm:14px;--radius:22px;--radius-lg:28px;
  --shadow:0 16px 45px rgba(24,24,27,.055);--shadow-soft:0 6px 22px rgba(24,24,27,.04);
}
*{box-sizing:border-box}html{color-scheme:light dark;scroll-behavior:smooth}
body{margin:0;background:var(--color-bg);color:var(--color-text);font-family:Inter,"Yu Gothic UI","Hiragino Sans",system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.62;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
body[data-theme="premium"]{--color-bg:#F8F5F0;--color-text:#211D18;--color-muted:#776B5F;--color-border:#E7DED4;--color-accent:#6F563A;--color-accent-hover:#5E472F;--color-accent-soft:#F0E8DC}
body[data-theme="friendly"]{--color-bg:#FFF8FA;--color-text:#33282D;--color-muted:#816B74;--color-border:#F0DDE4;--color-accent:#C65F82;--color-accent-hover:#AF4E70;--color-accent-soft:#FCEAF1}
body[data-theme="business"]{--color-bg:#F5F7FA;--color-text:#172033;--color-muted:#667085;--color-border:#DEE4EC;--color-accent:#356AE6;--color-accent-hover:#2859C7;--color-accent-soft:#EAF0FF}
body[data-theme="minimal"]{--color-bg:#FAFAFA;--color-text:#171717;--color-muted:#737373;--color-border:#E7E7E7;--color-accent:#171717;--color-accent-hover:#2A2A2A;--color-accent-soft:#F0F0F0}
body[data-theme="soft"]{--color-bg:#FCF9FF;--color-text:#2B2432;--color-muted:#786C82;--color-border:#EAE2F0;--color-accent:#8A6CC7;--color-accent-hover:#7658B4;--color-accent-soft:#F1EBFA}
body[data-theme="finance"]{--color-bg:#F4F8F7;--color-text:#102A2A;--color-muted:#5D7775;--color-border:#D8E5E2;--color-accent:#176B66;--color-accent-hover:#125954;--color-accent-soft:#E4F1EF}
body[data-theme="youthful"]{--color-bg:#FFF9F7;--color-text:#30272A;--color-muted:#7D6B70;--color-border:#F0E0DC;--color-accent:#E46572;--color-accent-hover:#CD515E;--color-accent-soft:#FCECEF}
body[data-theme="future"]{--color-bg:#F7F8FF;--color-text:#1E2033;--color-muted:#6D708D;--color-border:#E1E3F2;--color-accent:#5C63E8;--color-accent-hover:#4A50CF;--color-accent-soft:#EDEEFF}
body[data-theme="dark"]{--color-bg:#111114;--color-surface:#19191D;--color-surface-soft:#202026;--color-text:#F4F4F5;--color-muted:#A1A1AA;--color-border:#2E2E35;--color-accent:#8B83FF;--color-accent-hover:#9A93FF;--color-accent-soft:#28264A;--shadow:0 20px 50px rgba(0,0,0,.22)}
html[data-color-mode="dark"] body:not([data-theme="dark"]){--color-bg:#111114;--color-surface:#19191D;--color-surface-soft:#202026;--color-text:#F4F4F5;--color-muted:#A1A1AA;--color-border:#2E2E35;--color-accent:#8B83FF;--color-accent-hover:#9A93FF;--color-accent-soft:#28264A;--shadow:0 20px 50px rgba(0,0,0,.22)}
@media(prefers-color-scheme:dark){html[data-color-mode="system"] body:not([data-theme="dark"]){--color-bg:#111114;--color-surface:#19191D;--color-surface-soft:#202026;--color-text:#F4F4F5;--color-muted:#A1A1AA;--color-border:#2E2E35;--color-accent:#8B83FF;--color-accent-hover:#9A93FF;--color-accent-soft:#28264A;--shadow:0 20px 50px rgba(0,0,0,.22)}}
button,input,select,textarea{font:inherit}
button{touch-action:manipulation}
.shell{width:min(1160px,calc(100% - 40px));margin-inline:auto}
.topbar{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--color-surface) 88%,transparent);backdrop-filter:blur(18px);border-bottom:1px solid color-mix(in srgb,var(--color-border) 88%,transparent)}
.nav{min-height:64px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{color:var(--color-text);text-decoration:none;font-weight:800;letter-spacing:-.025em;font-size:1.03rem}
.nav-actions{display:flex;align-items:center;justify-content:flex-end;gap:7px;flex-wrap:wrap}
.feature-chip,.status-badge{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--color-border);background:var(--color-surface);border-radius:999px;padding:7px 10px;font-size:.75rem;font-weight:700;color:var(--color-muted)}
.status-dot{width:7px;height:7px;border-radius:50%;background:#22C55E}
.icon-button{min-height:38px;min-width:38px;width:38px;padding:0;border-radius:999px;background:var(--color-surface-soft);color:var(--color-text);border:1px solid var(--color-border);display:inline-grid;place-items:center}
.hero{padding:54px 0 28px}.hero-copy{max-width:820px}
.eyebrow,.section-kicker{font-size:.7rem;font-weight:850;letter-spacing:.13em;color:var(--color-muted)}
.hero h1{font-size:clamp(2rem,5vw,3.7rem);line-height:1.06;letter-spacing:-.05em;margin:10px 0 14px;max-width:900px}
.hero p{margin:0;color:var(--color-muted);font-size:clamp(.98rem,2vw,1.1rem);max-width:720px}
.stats-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:8px 0 16px}
.stat-card{min-width:0;background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius);padding:19px;box-shadow:var(--shadow-soft)}
.stat-card span,.stat-card small{display:block;color:var(--color-muted);font-size:.8rem}.stat-card strong{font-size:1.9rem;line-height:1.1;letter-spacing:-.035em}.stat-card .text-stat{font-size:1.08rem;margin-top:7px}
.content-grid{display:grid;grid-template-columns:minmax(0,.94fr) minmax(0,1.06fr);gap:16px;align-items:start}
.panel{min-width:0;background:var(--color-surface);border:1px solid var(--color-border);border-radius:var(--radius);padding:23px;box-shadow:var(--shadow);margin-bottom:16px}
.section-heading{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}.section-heading h2{margin:3px 0 0;font-size:1.22rem;letter-spacing:-.022em}.section-heading p{margin:0;max-width:290px;color:var(--color-muted);font-size:.86rem}
.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.form-grid .wide{grid-column:1/-1}
label{display:grid;gap:7px;color:var(--color-text);font-size:.86rem;font-weight:700;min-width:0}
input,select,textarea{width:100%;min-width:0;min-height:50px;border:1px solid var(--color-border);background:var(--color-surface-soft);color:var(--color-text);padding:12px 14px;border-radius:var(--radius-sm);transition:border-color .15s ease,box-shadow .15s ease,background .15s ease}
textarea{resize:vertical;min-height:116px}
input::placeholder,textarea::placeholder{color:color-mix(in srgb,var(--color-muted) 72%,transparent)}
input:hover,select:hover,textarea:hover{border-color:color-mix(in srgb,var(--color-muted) 52%,var(--color-border))}
input:focus-visible,select:focus-visible,textarea:focus-visible,button:focus-visible{outline:3px solid color-mix(in srgb,var(--focus) 72%,transparent);outline-offset:2px}
button{min-height:48px;border:0;background:var(--color-accent);color:#fff;padding:11px 17px;border-radius:var(--radius-sm);font-weight:760;cursor:pointer;transition:transform .14s ease,opacity .14s ease,background .14s ease}
button:hover{transform:translateY(-1px);background:var(--color-accent-hover)}button:active{transform:translateY(0)}button:disabled{opacity:.55;cursor:not-allowed;transform:none}
button.secondary{background:var(--color-surface-soft);color:var(--color-text);border:1px solid var(--color-border)}button.secondary:hover,button.ghost:hover{background:var(--color-accent-soft)}
button.ghost{background:transparent;color:var(--color-muted);border:1px solid var(--color-border)}
.button-row{display:flex;gap:9px;flex-wrap:wrap;margin-top:15px}.full-button{width:100%;margin-top:16px}
.feedback{min-height:1.5em;color:var(--color-muted);font-size:.86rem;overflow-wrap:anywhere}
.clean-list{list-style:none;padding:0;margin:0;display:grid;gap:9px}.clean-list li{min-width:0;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 15px;border:1px solid var(--color-border);border-radius:15px;background:var(--color-surface-soft)}
.clean-list li span{min-width:0;overflow-wrap:anywhere}.clean-list li button{min-height:42px;padding:7px 11px;background:transparent;color:var(--color-danger);border:1px solid color-mix(in srgb,var(--color-danger) 28%,var(--color-border))}
.empty-state{border:1px dashed color-mix(in srgb,var(--color-muted) 28%,var(--color-border));border-radius:16px;padding:30px 20px;text-align:center;color:var(--color-muted);background:var(--color-surface-soft)}
.toast{position:fixed;right:20px;bottom:20px;z-index:80;max-width:min(420px,calc(100% - 32px));padding:12px 15px;border-radius:14px;background:#18181B;color:#fff;box-shadow:0 16px 44px rgba(0,0,0,.2);font-size:.88rem;opacity:0;transform:translateY(10px);pointer-events:none;transition:opacity .18s ease,transform .18s ease}
.toast.show{opacity:1;transform:translateY(0)}.toast[data-type="error"]{background:#8F1D18}.toast[data-type="success"]{background:#166534}
.confirm-dialog{width:min(430px,calc(100% - 32px));border:1px solid var(--color-border);border-radius:22px;padding:0;background:var(--color-surface);color:var(--color-text);box-shadow:0 30px 90px rgba(0,0,0,.22)}.confirm-dialog::backdrop{background:rgba(15,15,18,.36);backdrop-filter:blur(3px)}
.confirm-dialog form{padding:24px}.confirm-dialog h2{margin:10px 0 7px;font-size:1.18rem}.confirm-dialog p{margin:0;color:var(--color-muted)}.dialog-icon{width:40px;height:40px;border-radius:14px;display:grid;place-items:center;background:var(--color-accent-soft);color:var(--color-accent);font-weight:900}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:22px}
.app-footer{padding:24px 0 50px;color:var(--color-muted);font-size:.76rem}
@media(max-width:800px){.shell{width:min(100% - 24px,1160px)}.nav{min-height:58px}.nav-actions .feature-chip,.status-badge{display:none}.hero{padding:36px 0 20px}.hero h1{font-size:clamp(2rem,11vw,3.15rem)}.stats-grid,.content-grid{grid-template-columns:1fr}.section-heading{display:block}.section-heading p{margin-top:6px;max-width:none}.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}.panel{padding:17px;border-radius:18px}.stat-card{padding:16px}.button-row button{flex:1 1 140px}.clean-list li{align-items:flex-start;flex-wrap:wrap}.clean-list li button{width:100%}.toast{right:12px;bottom:12px}}
@media(max-width:430px){.shell{width:min(100% - 18px,1160px)}.hero{padding-top:28px}.panel{padding:15px}.nav-actions{gap:4px}.icon-button{width:36px;min-width:36px;min-height:36px}}
'''

    def _script_for_type(self, app_type: str, auth: bool, database: bool) -> str:
        return f'''
const appType={json.dumps(app_type)};
const authRequired={str(auth).lower()};
const hasDatabase={str(database).lower()};
const list=document.querySelector('#itemList');
const title=document.querySelector('#itemTitle');
const value=document.querySelector('#itemValue');
const status=document.querySelector('#status');
const emptyState=document.querySelector('#emptyState');
const statPrimary=document.querySelector('#statPrimary');
const toast=document.querySelector('#toast');
const confirmDialog=document.querySelector('#confirmDialog');
const confirmMessage=document.querySelector('#confirmMessage');
const themeToggle=document.querySelector('#themeToggle');
let csrf='';
let localRows=[];
let toastTimer=null;

function showToast(message,type='info'){{
  if(!toast)return;
  toast.textContent=message;
  toast.dataset.type=type;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>toast.classList.remove('show'),2600);
}}
function setStatus(message,type='info'){{
  if(status)status.textContent=message;
  if(message)showToast(message,type);
}}
function setBusy(button,busy,label='処理中…'){{
  if(!button)return;
  if(busy){{button.dataset.label=button.textContent;button.textContent=label;button.disabled=true;}}
  else{{button.textContent=button.dataset.label||button.textContent;button.disabled=false;}}
}}
function confirmAction(message){{
  if(!confirmDialog||typeof confirmDialog.showModal!=='function')return Promise.resolve(window.confirm(message));
  confirmMessage.textContent=message;
  return new Promise(resolve=>{{
    const close=()=>{{confirmDialog.removeEventListener('close',close);resolve(confirmDialog.returnValue==='ok');}};
    confirmDialog.addEventListener('close',close);
    confirmDialog.showModal();
  }});
}}
function initTheme(){{
  const saved=localStorage.getItem('color-mode')||'system';
  document.documentElement.dataset.colorMode=saved;
  if(themeToggle)themeToggle.title='テーマ: '+({{system:'システム',light:'ライト',dark:'ダーク'}}[saved]||'システム');
}}
function cycleTheme(){{
  const order=['system','light','dark'];
  const current=document.documentElement.dataset.colorMode||'system';
  const next=order[(order.indexOf(current)+1)%order.length];
  document.documentElement.dataset.colorMode=next;
  localStorage.setItem('color-mode',next);
  if(themeToggle)themeToggle.title='テーマ: '+({{system:'システム',light:'ライト',dark:'ダーク'}}[next]);
  showToast('表示テーマ: '+({{system:'システム',light:'ライト',dark:'ダーク'}}[next]));
}}
if(themeToggle)themeToggle.addEventListener('click',cycleTheme);
initTheme();

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
    b.onclick=()=>removeItem(r.id,r.title);
    li.append(text,b);
    list.append(li);
  }}
}}
async function removeItem(id,label){{
  if(!(await confirmAction((label||'この項目')+'を削除しますか？')))return;
  if(hasDatabase){{
    try{{await api('/api/items/'+id,{{method:'DELETE'}});await load();setStatus('削除しました','success');}}
    catch(e){{setStatus(e.message,'error');}}
  }}else{{
    localRows=localRows.filter((_,index)=>index!==id);
    localStorage.setItem('rows',JSON.stringify(localRows));
    render(localRows.map((row,index)=>({{...row,id:index}})));
    setStatus('削除しました','success');
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
  if(!hasDatabase){{
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
const addButton=document.querySelector('#addItem');
if(addButton)addButton.onclick=async()=>{{
  const item=payload();
  if(!item.title){{setStatus('必須項目を入力してください','error');title?.focus();return;}}
  setBusy(addButton,true,'保存中…');
  try{{
    if(hasDatabase){{
      await api('/api/items',{{method:'POST',body:JSON.stringify(item)}});
      clearForm();await load();
    }}else{{
      localRows.push(item);localStorage.setItem('rows',JSON.stringify(localRows));
      clearForm();render(localRows.map((row,index)=>({{...row,id:index}})));
    }}
    setStatus('保存しました','success');
  }}catch(e){{setStatus(e.message,'error');}}
  finally{{setBusy(addButton,false);}}
}};
const email=document.querySelector('#email'),password=document.querySelector('#password'),authStatus=document.querySelector('#authStatus');
function authMessage(message,type='info'){{if(authStatus)authStatus.textContent=message;showToast(message,type);}}
if(email){{
  document.querySelector('#register').onclick=async()=>{{try{{await api('/api/register',{{method:'POST',body:JSON.stringify({{email:email.value,password:password.value}})}});authMessage('登録しました','success');await load();}}catch(e){{authMessage(e.message,'error');}}}};
  document.querySelector('#login').onclick=async()=>{{try{{await api('/api/login',{{method:'POST',body:JSON.stringify({{email:email.value,password:password.value}})}});authMessage('ログインしました','success');await load();}}catch(e){{authMessage(e.message,'error');}}}};
  document.querySelector('#logout').onclick=async()=>{{try{{await api('/api/logout',{{method:'POST'}});csrf='';authMessage('ログアウトしました','success');render([]);}}catch(e){{authMessage(e.message,'error');}}}};
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
