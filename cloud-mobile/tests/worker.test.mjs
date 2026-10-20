import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { handleRequest } from "../src/worker.mjs";

const owner = async () => ({ email:"owner@example.com",role:"owner" });
function harness() {
  const state={paused:0,requests:[]};
  const DB={prepare(sql) {
    let args=[];
    return {
      bind(...values){args=values;return this},
      async first(){
        if(sql.includes("FROM ivy_control"))return {paused:state.paused};
        if(sql.includes("COUNT(*) AS today"))return {today:state.requests.length};
        if(sql.includes("idempotency_key=?"))return state.requests.find(x=>x.owner_email===args[0]&&x.idempotency_key===args[1])||null;
        return null;
      },
      async all(){return {results:state.requests.map(({id,mode,prompt,status,created_at})=>({id,mode,prompt,status,created_at}))}},
      async run(){
        if(sql.includes("UPDATE ivy_control")){state.paused=1;return {meta:{changes:1}}}
        if(sql.includes("INSERT INTO ivy_requests")){
          if(state.paused)return {meta:{changes:0}};
          if(state.requests.length>=10)return {meta:{changes:0}};
          const [id,owner_email,idempotency_key,mode,prompt,created_at]=args;
          state.requests.push({id,owner_email,idempotency_key,mode,prompt,created_at,status:"awaiting_hosted_worker"});
          return {meta:{changes:1}};
        }
        return {meta:{changes:0}};
      }
    };
  }};
  return {state,env:{DB,ASSETS:{fetch:async()=>new Response("site",{status:200})}}};
}
function post(path,body,headers={}) {
  return new Request("https://ivy.example"+path,{method:"POST",
    headers:{"origin":"https://ivy.example","sec-fetch-site":"same-origin","content-type":"application/json",...headers},
    body:JSON.stringify(body)});
}
test("API fails closed for missing owner verification",async()=>{
  const {env}=harness();
  const res=await handleRequest(new Request("https://ivy.example/api/v1/status"),env,async()=>{throw Error("denied")});
  assert.equal(res.status,403);
  assert.equal((await res.json()).error,"owner_login_required");
});
test("status reports no generator / no publishing, even when intake works",async()=>{
  const {env}=harness();
  const res=await handleRequest(new Request("https://ivy.example/api/v1/status"),env,owner);
  const data=await res.json();
  assert.equal(res.status,200);
  assert.equal(data.generation_enabled,false);
  assert.equal(data.hosted_worker_connected,false);
  assert.equal(data.publishing_enabled,false);
});
test("valid request is saved once, never treated as generation",async()=>{
  const {env,state}=harness();
  const body={prompt:" Build a Japanese app ",mode:"app",idempotency_key:"mobile_request_00000001"};
  const first=await handleRequest(post("/api/v1/requests",body),env,owner);
  assert.equal(first.status,202);
  const created=await first.json();
  assert.equal(created.status,"awaiting_hosted_worker");
  const second=await handleRequest(post("/api/v1/requests",body),env,owner);
  assert.equal(second.status,200);
  assert.equal((await second.json()).reused,true);
  assert.equal(state.requests.length,1);
});
test("cross-origin POST is rejected",async()=>{
  const {env}=harness();
  const res=await handleRequest(post("/api/v1/requests",{
    prompt:"create",mode:"web",idempotency_key:"mobile_request_00000001"
  },{"origin":"https://attacker.example"}),env,owner);
  assert.equal(res.status,400);
});
test("unsafe mode and oversized prompts fail",async()=>{
  const {env}=harness();
  for (const b of [
    {prompt:"ok",mode:"shell",idempotency_key:"mobile_request_00000001"},
    {prompt:"a".repeat(1201),mode:"web",idempotency_key:"mobile_request_00000001"},
  ]){
    const res=await handleRequest(post("/api/v1/requests",b),env,owner);
    assert.equal(res.status,400);
  }
});
test("stop fails closed and blocks new intake",async()=>{
  const {env}=harness();
  const stop=await handleRequest(post("/api/v1/stop",{}),env,owner);
  assert.equal((await stop.json()).paused,true);
  const blocked=await handleRequest(post("/api/v1/requests",{
    prompt:"new app",mode:"web",idempotency_key:"mobile_request_00000001"
  }),env,owner);
  assert.equal(blocked.status,423);
});
test("PWA shell is configured without sensitive offline cache",()=>{
  const html=readFileSync(new URL("../web/index.html",import.meta.url),"utf8");
  const sw=readFileSync(new URL("../web/sw.js",import.meta.url),"utf8");
  const manifest=JSON.parse(readFileSync(new URL("../web/manifest.webmanifest",import.meta.url),"utf8"));
  assert.match(html,/name="viewport"/);
  assert.match(html,/id="requestForm"/);
  assert.equal(manifest.display,"standalone");
  assert.doesNotMatch(sw,/caches\.open|cache\.put|respondWith/);
});
