// Shell-only offline cache. Private state is in IndexedDB and is never cached
// here, nor are API calls, POST requests or cross-origin responses.
const NAME='madar-pwa-shell-1.0.22-1';
const SHELL=['./','./index.html','./madar-icon.svg','./manifest.webmanifest'];
self.addEventListener('install',event=>{
  event.waitUntil((async()=>{
    const cache=await caches.open(NAME);
    await cache.addAll(SHELL);
    // Pre-cache the fingerprinted Vite entrypoint chunks. Waiting until the
    // first controlled reload would leave a newly installed PWA unusable
    // offline immediately after installation.
    const html=await (await cache.match('./index.html')).text();
    const assets=Array.from(html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g),
      match=>new URL(match[1],self.registration.scope).toString());
    if(assets.length)await cache.addAll(assets);
  })());
  self.skipWaiting();
});
self.addEventListener('activate',event=>{
  event.waitUntil(Promise.all([
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('madar-pwa-shell-')&&key!==NAME).map(key=>caches.delete(key)))),
    self.clients.claim(),
  ]));
});
self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
  if(request.mode==='navigate'){
    event.respondWith(fetch(request).catch(()=>caches.match('./index.html')));
    return;
  }
  if(!url.pathname.match(/\.(?:css|js|png|svg|ico|webmanifest)$/))return;
  event.respondWith(caches.match(request).then(cached=>cached||fetch(request).then(response=>{
    if(response.ok&&response.type==='basic'){
      const copy=response.clone();
      event.waitUntil(caches.open(NAME).then(cache=>cache.put(request,copy)));
    }
    return response;
  })));
});
