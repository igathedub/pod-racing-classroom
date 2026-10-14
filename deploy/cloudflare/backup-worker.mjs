const isBackupPath = path => path === '/backup' || path.startsWith('/backup/');
const unavailable = () => new Response('Die Reserve ist derzeit nicht erreichbar.', {status:503, headers:{'content-type':'text/plain; charset=utf-8','cache-control':'no-store','retry-after':'30'}});

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!isBackupPath(url.pathname)) return fetch(request);
    if (url.protocol !== 'https:') {
      url.protocol = 'https:';
      return new Response(null, {status:308, headers:{location:url.href,'cache-control':'no-store'}});
    }
    try {
      const origin = new URL(env.BACKUP_ORIGIN);
      if (origin.origin !== 'https://mac-backup-origin.codeweek-wi.de' || origin.pathname !== '/' || origin.search || origin.hash || origin.username || origin.password || !env.BACKUP_EDGE_SECRET) return unavailable();
      const upstream = new URL(url.pathname + url.search, origin);
      const headers = new Headers();
      for (const name of ['accept','accept-language','authorization','content-type','origin','referer','x-admin-token','sec-fetch-site','sec-fetch-mode','sec-fetch-dest']) {
        if (request.headers.has(name)) headers.set(name, request.headers.get(name));
      }
      headers.set('x-pod-backup-gateway', env.BACKUP_EDGE_SECRET);
      const cookie = (request.headers.get('cookie') || '').split(';').map(value => value.trim()).filter(value => value.startsWith('pod_participant_backup=')).join('; ');
      if (cookie) headers.set('cookie', cookie);
      const init = {method:request.method, headers, redirect:'manual', signal:AbortSignal.timeout(15000)};
      if (!['GET','HEAD'].includes(request.method)) { init.body=request.body; init.duplex='half'; }
      const response = await fetch(new Request(upstream, init), {cf:{cacheTtl:0,cacheEverything:false}});
      if (response.status >= 500) return unavailable();
      const outputHeaders = new Headers(response.headers);
      outputHeaders.set('cache-control', 'no-store');
      if (outputHeaders.has('set-cookie')) {
        const cookies = typeof outputHeaders.getSetCookie === 'function' ? outputHeaders.getSetCookie() : [outputHeaders.get('set-cookie')];
        for (const value of cookies) {
          if (!value.startsWith('pod_participant_backup=') || !/;\s*path=\/backup(?:;|$)/i.test(value) || !/;\s*secure(?:;|$)/i.test(value) || !/;\s*httponly(?:;|$)/i.test(value) || !/;\s*samesite=strict(?:;|$)/i.test(value) || /;\s*domain=/i.test(value)) return unavailable();
        }
      }
      if (outputHeaders.has('location')) {
        const location = new URL(outputHeaders.get('location'), upstream);
        if (!['https:','http:'].includes(location.protocol) || ![origin.host, url.host].includes(location.host) || !isBackupPath(location.pathname)) return unavailable();
        outputHeaders.set('location', url.origin + location.pathname + location.search + location.hash);
      }
      return new Response(response.body, {status:response.status, statusText:response.statusText, headers:outputHeaders});
    } catch {
      // Never fall back to Windows or reveal tunnel errors/credential details.
      return unavailable();
    }
  }
};
