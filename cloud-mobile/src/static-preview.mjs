/**
 * Bounded static HTML preview compiler for Cloudflare Workers.
 *
 * Explicitly NOT an LLM, arbitrary-code generator or release pipeline.
 * All user text is escaped, no scripts/network/font imports are emitted,
 * and the rendered preview is sandboxed by the serving endpoint.
 */
const MAX_PROMPT = 1200;
const htmlEscape = value => String(value).replace(/[&<>"']/g, char => ({
  "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
}[char]));
export const GENERATOR_KIND = "static_template_v1";

export function compileStaticPreview({prompt, mode}) {
  if (mode !== "web" || typeof prompt !== "string" ||
      prompt.trim().length < 1 || prompt.length > MAX_PROMPT)
    throw new Error("unsupported_preview_request");

  const rawTitle = prompt.trim().split(/[\r\n。！？!?]/, 1)[0].slice(0, 64);
  const title = htmlEscape(rawTitle || "新しいWebプロジェクト");
  const description = htmlEscape(prompt.trim());
  const html = `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<meta name="referrer" content="no-referrer">
<title>${title} | Ivy Preview</title>
<style>
:root{font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN",sans-serif;background:#0d1423;color:#eff6ff}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:28px 18px;background:radial-gradient(circle at 70% 0,#1e4960,transparent 55%),#0d1423}
main{width:min(720px,100%);padding:clamp(26px,7vw,66px);border-radius:25px;border:1px solid #badce64d;background:#ffffff0b;box-shadow:0 20px 70px #0004}
.eyebrow{color:#9bd6de;letter-spacing:.25em;font-size:12px;font-weight:750}
h1{font-size:clamp(29px,7vw,50px);overflow-wrap:anywhere;line-height:1.3;letter-spacing:-.045em}
p{line-height:1.85;overflow-wrap:anywhere;white-space:pre-wrap;color:#d0e1ec}
.tag{display:inline-block;border:1px solid #a3d9dd55;color:#a2d7e2;padding:7px 13px;border-radius:50px;font-size:12px}
small{display:block;margin-top:24px;color:#a4b3c5}
</style>
</head>
<body>
<main>
<div class="eyebrow">IVY · SAFE STATIC PREVIEW</div>
<h1>${title}</h1>
<p>${description}</p>
<span class="tag">Webサイト構成サンプル</span>
<small>これは固定テンプレートによる安全なプレビューです。AI生成、業務機能、テスト済みアプリではありません。</small>
</main>
</body>
</html>`;

  const checks = [
    {name:"bounded_output", passed:html.length < 20000},
    {name:"doctype_and_mobile_viewport", passed:html.startsWith("<!doctype html>") && html.includes('name="viewport"')},
    {name:"no_executable_scripts", passed:!/<script\b|<iframe\b|<form\b|<object\b|onerror\s*=|javascript:/i.test(html)},
    {name:"escaped_user_input", passed:!html.includes(prompt.trim()) || !/[<>&"']/.test(prompt)},
  ];
  if (!checks.every(check => check.passed)) throw new Error("preview_validation_failed");
  return {html, checks, generator:GENERATOR_KIND};
}
