/** Optional bounded Workers AI copywriting: NEVER execute generated code. */
const MODEL="@cf/meta/llama-3.1-8b-instruct-fp8";
const esc=value=>String(value).replace(/[&<>"']/g,c=>({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
}[c]));
const valid=(s,max)=>typeof s==="string"&&s.trim().length>0&&s.trim().length<=max;
export function compileAiLandingPlan(raw) {
  if(typeof raw!=="string"||raw.length>12000)throw new Error("ai_output_invalid");
  let v;
  try{v=JSON.parse(raw.trim());}catch{throw new Error("ai_output_invalid");}
  if(!v||Array.isArray(v)||typeof v!=="object"||!valid(v.title,80)||
    !valid(v.subtitle,220)||!Array.isArray(v.sections)||
    v.sections.length<1||v.sections.length>3)throw new Error("ai_output_invalid");
  for(const s of v.sections){
    if(!s||typeof s!=="object"||!valid(s.heading,80)||!valid(s.body,450))
      throw new Error("ai_output_invalid");
  }
  const sections=v.sections.map(s=>'<section class="card"><h2>'+esc(s.heading)+
    '</h2><p>'+esc(s.body)+'</p></section>').join("");
  const html=['<!doctype html>','<!-- ivy-ai-assisted-content-no-executable-code -->',
    '<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
    '<meta name="referrer" content="no-referrer"><title>'+esc(v.title)+'</title>',
    '<style>:root{font:16px/1.7 system-ui,sans-serif;color:#edf7ff;background:#0c1626}*{box-sizing:border-box}body{margin:0;padding:35px 18px;min-height:100vh;background:radial-gradient(circle at 85% 0,#244d62,transparent 60%),#0c1626}main{max-width:920px;margin:auto}h1{font-size:clamp(32px,8vw,64px);letter-spacing:-.06em;line-height:1.23}p{white-space:pre-wrap;overflow-wrap:anywhere;color:#c3dae7}.card{border:1px solid #b7dbea40;background:#ffffff0a;padding:22px;border-radius:20px;margin:15px 0}.eyebrow{color:#9ce2ed;font-size:12px;letter-spacing:.18em}footer{font-size:12px;color:#a2bdca;margin-top:30px}</style></head>',
    '<body><main><div class="eyebrow">IVY · AI-ASSISTED CONTENT / STATIC HTML</div>',
    '<h1>'+esc(v.title)+'</h1><p>'+esc(v.subtitle)+'</p>',
    sections,'<footer>文章・構成はAI補助で作りました。プログラムコードは固定テンプレートです。内容を確認してから公開してください。</footer>',
    '</main></body></html>'].join("");
  if(html.length>16000||/<script\b|<iframe\b/i.test(html))throw new Error("ai_output_invalid");
  return {html,checks:[{name:"schema_valid",passed:true},{name:"no_executable_code",passed:true}],
    generator:"static_template_v1",template_kind:"ai_landing",ai_assisted:true};
}
export async function createAiLandingText(ai,prompt) {
  if(!ai||typeof ai.run!=="function"||typeof prompt!=="string"||
    !prompt.trim()||prompt.length>1200)throw new Error("ai_unavailable");
  const result=await ai.run(MODEL,{
    messages:[
      {role:"system",content:"You are a Japanese web copywriter. Return ONLY JSON with title (1-80 chars), subtitle (1-220 chars), sections (1-3 objects with heading (1-80 chars) and body (1-450 chars)). No Markdown, HTML, code, URLs, or external assets. Never claim an app, database, or payment system was built."},
      {role:"user",content:prompt}
    ],
    max_tokens:420,temperature:0.25
  });
  return compileAiLandingPlan(result?.response);
}
