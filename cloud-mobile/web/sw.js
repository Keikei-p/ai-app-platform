// Network-only by design. Never cache private requests or Cloudflare Access sessions.
self.addEventListener("install",event=>{event.waitUntil(self.skipWaiting());});
self.addEventListener("activate",event=>{event.waitUntil(self.clients.claim());});
// No fetch interception: offline mode cannot expose stale request history.
