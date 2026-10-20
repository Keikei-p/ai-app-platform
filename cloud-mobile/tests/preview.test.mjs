import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {handleRequest} from "../src/worker.mjs";
import {compileStaticPreview} from "../src/static-preview.mjs";

const OWNER="owner@example.com", OTHER="another@example.com";
const id="00000000-0000-4000-8000-000000000001";
const asOwner=async()=>({email:OWNER,role:"owner"});
const asOther=async()=>({email:OTHER,role:"owner"});
const url=path=>"https://ivy.example"+path;
const get=path=>new Request(url(path));
const post=(path,body,origin="https://ivy.example")=>new Request(url(path),{
  method:"POST",headers:{"content-type":"application/json","origin":origin,
    "sec-fetch-site":"same-origin"},body:JSON.stringify(body)
});

function harness(mode="web", prompt="魅力的な予約サイトを作って") {
  const row={id,owner_email:OWNER,mode,prompt,status:"awaiting_hosted_worker"};
  const state={rows:[row],artifacts:new Map(),paused:0};
  const DB={
    prepare(sql){
      const b={values:[],bind(...values){this.values=values;return this;},
        async first(){
          if(sql.includes("FROM ivy_control"))return {paused:state.paused};
          if(sql.includes("COUNT(*) AS today"))return {today:1};
          if(sql.startsWith("SELECT id,mode,prompt,status FROM ivy_requests")){
            const [requestId,email]=this.values;
            return state.rows.find(r=>r.id===requestId&&r.owner_email===email)||null;
          }
          if(sql.startsWith("SELECT status FROM ivy_requests")){
            const [requestId,email]=this.values;
            const found=state.rows.find(r=>r.id===requestId&&r.owner_email===email);
            return found?{status:found.status}:null;
          }
          if(sql.startsWith("SELECT generator,html,checks_json FROM ivy_static_previews")){
            const [requestId,email]=this.values;
            const found=state.artifacts.get(requestId);
            return found?.owner_email===email?found:null;
          }
          return null;
        },
        async all(){return {results:state.rows}},
        async run(){
          if(sql.startsWith("INSERT OR IGNORE INTO ivy_static_previews")){
            const [generator,html,checks,created,requestId,email]=this.values;
            const r=state.rows.find(x=>x.id===requestId&&x.owner_email===email);
            if(!r||state.paused||r.mode!=="web"||r.status!=="awaiting_hosted_worker"||
                state.artifacts.has(requestId))return {meta:{changes:0}};
            state.artifacts.set(requestId,{generator,html,checks_json:checks,
              owner_email:email,created_at:created});
            return {meta:{changes:1}};
          }
          if(sql.startsWith("UPDATE ivy_requests SET status='template_ready'")){
            const [requestId,email]=this.values;
            const r=state.rows.find(x=>x.id===requestId&&x.owner_email===email);
            if(!r||r.status!=="awaiting_hosted_worker"||
                state.artifacts.get(requestId)?.owner_email!==email)return {meta:{changes:0}};
            r.status="template_ready";return {meta:{changes:1}};
          }
          if(sql.startsWith("UPDATE ivy_requests SET status='cancelled'")){
            const [requestId,email]=this.values;
            const r=state.rows.find(x=>x.id===requestId&&x.owner_email===email);
            if(!r||r.status!=="awaiting_hosted_worker")return {meta:{changes:0}};
            r.status="cancelled";return {meta:{changes:1}};
          }
          if(sql.startsWith("UPDATE ivy_control")){
            state.paused=1;return {meta:{changes:1}};
          }
          throw new Error("Unhandled SQL in test DB: "+sql);
        }};
      return b;
    },
    async batch(statements){const results=[];for(const statement of statements)results.push(await statement.run());return results;}
  };
  return {state,env:{DB}};
}

test("compiler escapes untrusted HTML, never emits active scripts or external calls",()=>{
  const prompt='<img src=x onerror="alert(1)"> & awesome landing site';
  const {html,checks,generator}=compileStaticPreview({prompt,mode:"web"});
  assert.equal(generator,"static_template_v1");
  assert.ok(checks.every(c=>c.passed));
  assert.match(html,/&lt;img src=x onerror=&quot;alert\(1\)&quot;&gt;/);
  assert.doesNotMatch(html,/<img src=x|<script\b|<iframe\b|fetch\(/i);
  assert.match(html,/viewport/);
  assert.match(html,/AI生成.*ではありません/);
  assert.throws(()=>compileStaticPreview({prompt:"X",mode:"app"}));
});

test("intake status never claims an AI model or heavy build is connected",async()=>{
  const {env}=harness();
  const r=await handleRequest(get("/api/v1/status"),env,asOwner);
  const j=await r.json();
  assert.equal(r.status,200);
  assert.equal(j.ai_generation_enabled,false);
  assert.equal(j.generation_enabled,false);
  assert.equal(j.hosted_worker_connected,false);
  assert.equal(j.static_preview_enabled,true);
  assert.equal(j.publishing_enabled,false);
});

test("explicit owner approval creates an actual stored static artifact and a safe preview",async()=>{
  const {env,state}=harness();
  const path="/api/v1/requests/"+id;
  let r=await handleRequest(post(path+"/build-preview",{confirm:"generate_static_template"}),env,asOwner);
  assert.equal(r.status,201);
  let result=await r.json();
  assert.equal(result.ai_generated,false);
  assert.equal(result.tests,"template_integrity_only");
  assert.equal(state.rows[0].status,"template_ready");
  assert.ok(state.artifacts.get(id)?.html.includes("<!doctype html>"));
  r=await handleRequest(get(path+"/preview"),env,asOwner);
  assert.equal(r.status,200);
  assert.match(r.headers.get("content-security-policy"),/sandbox;/);
  assert.match(r.headers.get("content-security-policy"),/script-src 'none'/);
  assert.match(await r.text(),/魅力的な予約サイト/);
  r=await handleRequest(get(path+"/download"),env,asOwner);
  assert.equal(r.status,200);
  assert.match(r.headers.get("content-disposition"),/^attachment;/);
  assert.equal(r.headers.get("cache-control"),"private, no-store");
  r=await handleRequest(post(path+"/build-preview",{confirm:"generate_static_template"}),env,asOwner);
  assert.equal(r.status,200);
  assert.equal((await r.json()).reused,true);
  assert.equal(state.artifacts.size,1);
});

test("owner identity, origin, and explicit consent are all required",async()=>{
  const {env,state}=harness();
  const path="/api/v1/requests/"+id;
  let r=await handleRequest(post(path+"/build-preview",{confirm:"generate_static_template"}),env,asOther);
  assert.equal(r.status,404);
  r=await handleRequest(post(path+"/build-preview",{confirm:"generate_static_template"},
    "https://evil.example"),env,asOwner);
  assert.equal(r.status,400);
  r=await handleRequest(post(path+"/build-preview",{confirm:"anything_else"}),env,asOwner);
  assert.equal(r.status,400);
  r=await handleRequest(get(path+"/download"),env,asOther);
  assert.equal(r.status,404);
  r=await handleRequest(get(path+"/preview"),env,async()=>{throw new Error("no Access");});
  assert.equal(r.status,403);
  assert.equal(state.artifacts.size,0);
});

test("app binary generation remains unavailable and paused state blocks work",async()=>{
  const app=harness("app");
  const path="/api/v1/requests/"+id;
  let r=await handleRequest(post(path+"/build-preview",{confirm:"generate_static_template"}),app.env,asOwner);
  assert.equal(r.status,409);
  assert.equal(app.state.artifacts.size,0);
  const web=harness();
  let stop=await handleRequest(post("/api/v1/stop",{}),web.env,asOwner);
  assert.equal((await stop.json()).paused,true);
  r=await handleRequest(post(path+"/build-preview",{confirm:"generate_static_template"}),web.env,asOwner);
  assert.equal(r.status,409);
  assert.equal(web.state.artifacts.size,0);
});

test("cancel stops pending work, preserves owner records and prevents preview",async()=>{
  const {env,state}=harness();
  const path="/api/v1/requests/"+id;
  let r=await handleRequest(post(path+"/cancel",{confirm:"cancel_pending"}),env,asOwner);
  assert.equal(r.status,200);
  assert.equal(state.rows[0].status,"cancelled");
  r=await handleRequest(post(path+"/build-preview",{confirm:"generate_static_template"}),env,asOwner);
  assert.equal(r.status,409);
  r=await handleRequest(get(path+"/preview"),env,asOwner);
  assert.equal(r.status,404);
  assert.equal(state.artifacts.size,0);
  assert.equal(state.rows.length,1);
});

test("mobile UI uses sandboxed HTML iframe and no claimed AI code generation",()=>{
  const html=readFileSync(new URL("../web/index.html",import.meta.url),"utf8");
  const js=readFileSync(new URL("../web/app.mjs",import.meta.url),"utf8");
  const migration=readFileSync(new URL("../migrations/0002_static_previews.sql",import.meta.url),"utf8");
  assert.match(html,/id="previewFrame"[^>]*sandbox="allow-scripts"/);
  assert.match(js,/generate_static_template/);
  assert.match(js,/cancel_pending/);
  assert.match(js,/textContent/);
  assert.match(migration,/CREATE TABLE IF NOT EXISTS ivy_static_previews/);
  assert.doesNotMatch(html,/allow-same-origin/);
});
