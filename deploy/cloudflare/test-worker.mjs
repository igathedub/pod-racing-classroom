import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';

const file = new URL('./backup-worker.mjs', import.meta.url);
const env = { BACKUP_ORIGIN: 'https://mac-backup-origin.codeweek-wi.de', BACKUP_EDGE_SECRET: 'synthetic-edge-secret-for-tests' };
let worker;

test('Worker implementation exists', async () => {
  assert.ok(existsSync(file), 'Backup edge Worker missing');
  worker = (await import(file.href)).default;
});

test('backup forwards only to independent Mac origin with no root credentials', async () => {
  globalThis.fetch = async (req, opts) => {
    assert.equal(req.url, 'https://mac-backup-origin.codeweek-wi.de/backup/api/state?lang=de');
    assert.equal(req.headers.get('x-pod-backup-gateway'), env.BACKUP_EDGE_SECRET);
    assert.equal(req.headers.get('authorization'), 'Basic synthetic-only');
    assert.equal(req.headers.get('cookie'), 'pod_participant_backup=synthetic-backup');
    assert.equal(req.headers.get('x-admin-token'), 'synthetic-teacher');
    assert.equal(req.redirect, 'manual');
    assert.equal(opts.cf.cacheTtl, 0);
    return new Response('{"safe":true}', { headers: {'content-type': 'application/json'} });
  };
  const response = await worker.fetch(new Request('https://codeweek-wi.de/backup/api/state?lang=de', { headers: {authorization:'Basic synthetic-only',cookie:'pod_participant=synthetic-root; unrelated=root-private; pod_participant_backup=synthetic-backup','x-admin-token':'synthetic-teacher'} }), env);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
});

test('root and lookalike path remain original request', async () => {
  for (const path of ['/', '/api/health', '/backups', '/backup-other']) {
    const original = new Request('https://codeweek-wi.de' + path);
    globalThis.fetch = async request => { assert.equal(request, original); return new Response('original'); };
    const response = await worker.fetch(original, env);
    assert.equal(await response.text(), 'original');
  }
});

test('HTTP backup redirects to HTTPS without origin fetch', async () => {
  globalThis.fetch = async () => { throw Error('must not fetch'); };
  const response = await worker.fetch(new Request('http://codeweek-wi.de/backup/teacher?lang=de'), env);
  assert.equal(response.status, 308);
  assert.equal(response.headers.get('location'), 'https://codeweek-wi.de/backup/teacher?lang=de');
});

test('missing marker configuration and recursive/unsafe origin fail closed', async () => {
  globalThis.fetch = async () => { throw Error('must not fetch'); };
  for (const config of [{...env,BACKUP_EDGE_SECRET:''},{...env,BACKUP_ORIGIN:'https://codeweek-wi.de'},{...env,BACKUP_ORIGIN:'http://mac-backup-origin.codeweek-wi.de'},{...env,BACKUP_ORIGIN:'https://mac-backup-origin.codeweek-wi.de/unsafe'}]) {
    const response = await worker.fetch(new Request('https://codeweek-wi.de/backup/'), config);
    assert.equal(response.status, 503);
  }
});

test('origin failure never falls back to Windows or reveals exception text', async () => {
  let calls=0;
  globalThis.fetch = async () => { calls++; throw Error('private-origin-details'); };
  const response = await worker.fetch(new Request('https://codeweek-wi.de/backup/'),env);
  assert.equal(response.status,503);
  assert.equal(calls,1);
  assert.ok(!(await response.text()).includes('private-origin-details'));
});

test('unauthenticated request preserves origin 401 challenge without adding credentials', async () => {
  globalThis.fetch = async req => { assert.equal(req.headers.get('authorization'),null); return new Response('Unauthorized',{status:401,headers:{'www-authenticate':'Basic realm="Pod Lab Mac Backup"'}}); };
  const response=await worker.fetch(new Request('https://codeweek-wi.de/backup/'),env);
  assert.equal(response.status,401);
  assert.equal(response.headers.get('www-authenticate'),'Basic realm="Pod Lab Mac Backup"');
});

test('POST JSON and mutation origin headers survive forwarding', async () => {
  globalThis.fetch = async req => {
    assert.equal(req.method,'POST');
    assert.equal(req.headers.get('origin'),'https://codeweek-wi.de');
    assert.equal(req.headers.get('sec-fetch-site'),'same-origin');
    assert.equal(await req.text(),'{"duration_seconds":7200}');
    return new Response('{}');
  };
  const request=new Request('https://codeweek-wi.de/backup/api/admin/session/start',{method:'POST',headers:{'content-type':'application/json',origin:'https://codeweek-wi.de','sec-fetch-site':'same-origin'},body:'{"duration_seconds":7200}'});
  assert.equal((await worker.fetch(request,env)).status,200);
});

test('participant cookie must be backup scoped and secure', async () => {
  for (const cookie of ['pod_participant=bad; Path=/; Secure; HttpOnly; SameSite=Strict','pod_participant_backup=bad; Path=/; Secure; HttpOnly; SameSite=Strict','pod_participant_backup=bad; Path=/backup; HttpOnly; SameSite=Strict']) {
    globalThis.fetch=async()=>new Response('{}',{headers:{'set-cookie':cookie}});
    assert.equal((await worker.fetch(new Request('https://codeweek-wi.de/backup/api/join'),env)).status,503);
  }
  globalThis.fetch=async()=>new Response('{}',{headers:{'set-cookie':'pod_participant_backup=synthetic; Path=/backup; Secure; HttpOnly; SameSite=Strict'}});
  const response=await worker.fetch(new Request('https://codeweek-wi.de/backup/api/join'),env);
  assert.equal(response.status,200);
  assert.match(response.headers.get('set-cookie'),/Path=\/backup/);
});

test('redirects stay on public backup path, never technical origin/root', async () => {
  globalThis.fetch=async()=>new Response(null,{status:308,headers:{location:'https://mac-backup-origin.codeweek-wi.de/backup/'}});
  let response=await worker.fetch(new Request('https://codeweek-wi.de/backup'),env);
  assert.equal(response.headers.get('location'),'https://codeweek-wi.de/backup/');
  globalThis.fetch=async()=>new Response(null,{status:308,headers:{location:'/'}});
  response=await worker.fetch(new Request('https://codeweek-wi.de/backup'),env);
  assert.equal(response.status,503);
});

test('internal HTTP redirect on known public host is upgraded to public HTTPS', async () => {
  globalThis.fetch=async()=>new Response(null,{status:307,headers:{location:'http://codeweek-wi.de/backup/?lang=de'}});
  const response=await worker.fetch(new Request('https://codeweek-wi.de/backup?lang=de'),env);
  assert.equal(response.status,307);
  assert.equal(response.headers.get('location'),'https://codeweek-wi.de/backup/?lang=de');
});
