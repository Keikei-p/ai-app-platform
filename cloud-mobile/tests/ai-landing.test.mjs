import test from "node:test";
import assert from "node:assert/strict";
import {compileAiLandingPlan,createAiLandingText} from "../src/ai-landing.mjs";

test("only schema validated non-executable HTML may be emitted from AI response",()=>{
  const document=JSON.stringify({
    title:'<img src=x onerror="alert(1)">',
    subtitle:"& difficult content",
    sections:[{heading:"私たちのサービス",body:"<script>alert(1)</script>"}]
  });
  const result=compileAiLandingPlan(document);
  assert.equal(result.ai_assisted,true);
  assert.equal(result.generator,"static_template_v1");
  assert.match(result.html,/&lt;img src=x/);
  assert.match(result.html,/&lt;script&gt;/);
  assert.doesNotMatch(result.html,/<script\b|<img src=x/i);
  assert.ok(result.html.length<16000);
  for(const bad of [
    '<script>alert(1)</script>',
    '{"title":"ok","subtitle":"yes","sections":[]}',
    JSON.stringify({title:"X".repeat(81),subtitle:"Y",
      sections:[{heading:"Z",body:"A"}]}),
    JSON.stringify({title:"safe",subtitle:"safe",sections:[
      {heading:"H",body:"B".repeat(451)}
    ]}),
    JSON.stringify({title:"safe",subtitle:"safe",sections:[
      {heading:"H",body:"B"},{heading:"H",body:"B"},
      {heading:"H",body:"B"},{heading:"H",body:"B"}
    ]}),
  ]){
    withBad(bad);
  }
});
function withBad(bad){assert.throws(()=>compileAiLandingPlan(bad),/ai_output_invalid/);}

test("Cloudflare model call bounded and never includes arbitrary commands",async()=>{
  let calls=0;
  const ai={run:async(model,options)=>{
    calls++;
    assert.equal(model,"@cf/meta/llama-3.1-8b-instruct-fp8");
    assert.equal(options.max_tokens,420);
    assert.equal(options.messages[1].content,"美容室の紹介サイトを作りたい");
    assert.ok(options.messages[0].content.includes("JSON"));
    return {response:JSON.stringify({
      title:"Salon",subtitle:"素敵な時間",
      sections:[{heading:"予約",body:"お電話ください"}]
    })};
  }};
  const result=await createAiLandingText(ai,"美容室の紹介サイトを作りたい");
  assert.equal(result.template_kind,"ai_landing");
  assert.equal(calls,1);
  await assert.rejects(()=>createAiLandingText(undefined,"X"),/ai_unavailable/);
  await assert.rejects(()=>createAiLandingText(ai,"X".repeat(1201)),/ai_unavailable/);
  assert.equal(calls,1);
});
