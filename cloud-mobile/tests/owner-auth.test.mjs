import test from "node:test";
import assert from "node:assert/strict";
import { authorizeOwner } from "../src/owner-auth.mjs";

/** Real RS256 JWT signature, with locally generated test-only keys. */
const encode = value => Buffer.from(typeof value === "string" ? value :
  JSON.stringify(value)).toString("base64url");
const issue = async (privateKey, claims, header = {alg:"RS256",typ:"JWT",kid:"ivy-test-key"}) => {
  const payload = encode(header)+"."+encode(claims);
  const signature = await crypto.subtle.sign("RSASSA-PKCS1-v1_5",
    privateKey,new TextEncoder().encode(payload));
  return payload+"."+Buffer.from(signature).toString("base64url");
};
const request = token => new Request("https://ivy.staging.example/api/v1/status", {
  headers:token?{"cf-access-jwt-assertion":token}:{}
});
test("OWNER Access JWT fallback validates real RS256 signature on Static Assets router",async()=>{
  // Cloudflare Workers Static Assets currently do not forward ctx.access to the
  // user Worker. Verify the documented cryptographic fallback instead of
  // accepting a user-controlled email header or a fake decoded JSON token.
  const domain="https://ivy-asset-router-test.cloudflareaccess.com";
  const audience="ivy-staging-audience";
  const owner="owner@example.com";
  const keys=await crypto.subtle.generateKey({
    name:"RSASSA-PKCS1-v1_5",modulusLength:2048,
    publicExponent:new Uint8Array([1,0,1]),hash:"SHA-256"
  },true,["sign","verify"]);
  const jwk=await crypto.subtle.exportKey("jwk",keys.publicKey);
  const cert={...jwk,alg:"RS256",use:"sig",kid:"ivy-test-key"};
  const configured={TEAM_DOMAIN:domain,ACCESS_AUD:audience,OWNER_EMAIL:owner};
  const now=Math.floor(Date.now()/1000);
  const claims={iss:domain,aud:[audience],email:owner,iat:now,exp:now+300};
  const originalFetch=globalThis.fetch;
  let fetchCount=0;
  try {
    globalThis.fetch=async (url, options)=>{
      fetchCount++;
      assert.equal(url,domain+"/cdn-cgi/access/certs");
      assert.equal(options.headers.accept,"application/json");
      return new Response(JSON.stringify({keys:[cert]}),{status:200});
    };
    const good=await issue(keys.privateKey,claims);
    assert.deepEqual(await authorizeOwner(request(good),configured,undefined),
      {email:owner,role:"owner"});
    assert.equal(fetchCount,1);
    // A warm JWKS cache avoids repeated network charges/latency.
    assert.deepEqual(await authorizeOwner(request(good),configured,undefined),
      {email:owner,role:"owner"});
    assert.equal(fetchCount,1);
    await assert.rejects(
      ()=>authorizeOwner(request(good),{...configured,OWNER_EMAIL:"other@example.com"}),
      /access_denied/
    );
    await assert.rejects(
      ()=>authorizeOwner(request(good),{...configured,ACCESS_AUD:"wrong-audience"}),
      /access_denied/
    );
    const altered=good.split(".");
    const tamperedPayload={...claims,email:"other@example.com"};
    altered[1]=encode(tamperedPayload);
    await assert.rejects(
      ()=>authorizeOwner(request(altered.join(".")),{...configured,OWNER_EMAIL:"other@example.com"}),
      /access_denied/
    );
    const invalid=await issue(keys.privateKey,{...claims,exp:now-1});
    await assert.rejects(()=>authorizeOwner(request(invalid),configured),/access_denied/);
    await assert.rejects(()=>authorizeOwner(request("unsigned.jwt.garbage"),configured));
    await assert.rejects(()=>authorizeOwner(new Request(
      "https://ivy.staging.example/api/v1/status",{
        headers:{"cf-access-authenticated-user-email":owner}
      }),configured),/access_denied/);
  } finally {globalThis.fetch=originalFetch;}
});
test("native ctx.access succeeds for verified OWNER and fails closed for wrong user",async()=>{
  const cfg={ACCESS_AUD:"ivy-stage",OWNER_EMAIL:"owner@example.com"};
  const ctx={access:{aud:"ivy-stage",getIdentity:async()=>({email:"OWNER@EXAMPLE.COM"})}};
  const identity=await authorizeOwner(request(),cfg,ctx);
  assert.deepEqual(identity,{email:"owner@example.com",role:"owner"});
  await assert.rejects(()=>authorizeOwner(request(),cfg,{
    access:{aud:"different",getIdentity:async()=>({email:"owner@example.com"})}
  }),/access_native_audience_mismatch/);
  await assert.rejects(()=>authorizeOwner(request(),cfg,{
    access:{aud:"ivy-stage",getIdentity:async()=>({email:"unauthorized@example.com"})}
  }),/access_native_owner_mismatch/);
  await assert.rejects(()=>authorizeOwner(request(),cfg,{
    access:{aud:"ivy-stage",getIdentity:async()=>{throw new Error("provider failure")}}
  }),/access_native_identity_unavailable/);
});
