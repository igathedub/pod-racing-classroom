(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const { t } = window.PodLocale;
  const localizedFields = new Map();
  const basePath = document.body.dataset.basePath || '';
  const storagePrefix = basePath ? `pod-lab:${basePath}` : 'pod-lab';
  const viewPath = location.pathname.slice(basePath.length).replace(/\/$/, '');
  const view = viewPath === '/teacher' ? 'teacher' : viewPath === '/projector' ? 'projector' : 'student';
  document.body.dataset.view = view;
  document.querySelectorAll('nav [data-view]').forEach(link => { if (link.dataset.view === view) link.setAttribute('aria-current', 'page'); });
  $('student-panel').hidden = view !== 'student';
  $('teacher-panel').hidden = view !== 'teacher';
  $('projector-panel').hidden = view !== 'projector';
  $('roster-panel').hidden = view === 'projector';
  $('roster-panel').open = view === 'teacher';
  if (view === 'teacher') $('teacher-panel').insertBefore($('roster-panel'), $('code-inspection'));
  if (view !== 'projector') document.querySelector('.monitor').prepend($(view === 'student' ? 'student-panel' : 'teacher-panel'));
  function updateTitle() { document.title = `Pod Lab · ${t(view === 'student' ? 'Student arena' : view === 'teacher' ? 'Teacher console' : 'Race projector')}`; }
  updateTitle();
  const palette = ['#ffb268', '#89ddba', '#86bfff', '#e9a5d2', '#e4dd81', '#b5b9c2'];
  const TURN_RATE = 10; // Replay presentation speed; not engine wall-clock time.
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const defaultBounds = () => ({ minX: -700, minY: -700, maxX: 16700, maxY: 9700 });
  const app = { state: null, online: false, stateBusy: false, adminBusy: false, submitBusy: false, practiceBusy: false, practiceReplay: null, localReplay: false, clockOffset: 0, follow: true, ranking: view === 'projector' ? 'race' : 'qualification', replayId: null, replay: null, replayBusy: false, lastReplayFetch: 0, position: 0, playing: !reducedMotion, speed: 1, finishTurns: new Map(), processedFrames: 0, lastRankingPaint: 0, lastAnimation: 0, bounds: defaultBounds() };
  const text = (id, value) => { localizedFields.set(id, value); $(id).textContent = String(value ?? ''); };
  const message = (id, value, type = '') => { text(id, value); $(id).className = `form-message ${type}`.trim(); };
  const notice = (id, value) => { text(id, value); $(id).hidden = !value; };
  const safeGet = (store, key) => { try { return store.getItem(key) || ''; } catch { return ''; } };
  const safeSet = (store, key, value) => { try { if (value) store.setItem(key, value); else store.removeItem(key); return true; } catch { return false; } };
  const memoryClaims = new Map();
  const aliasKey = alias => `${storagePrefix}:claim:${alias.trim().toLowerCase()}`;
  const claimFor = alias => memoryClaims.get(alias.trim().toLowerCase()) || safeGet(localStorage, aliasKey(alias));
  let adminToken = view === 'teacher' ? safeGet(sessionStorage, `${storagePrefix}:admin`) : '';
  let submissionDurationInitialized = false;
  let submissionDurationEdited = false;
  const humanStatus = status => ({ waiting: t('Waiting for teacher to open'), open: t('Submissions are open'), closed: t('Submissions closed'), qualifying: t('Qualification in progress'), qualified: t('Qualification complete'), final: t('Final race in progress'), finished: t('Classroom final complete') }[status] || t('Waiting for session'));
  const formatTime = seconds => {
    const s = Math.max(0, Math.floor(seconds));
    return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map(v => String(v).padStart(2, '0')).join(':');
  };
  const now = () => Date.now() / 1000 + app.clockOffset;
  const isOpen = () => app.online && app.state?.session?.status === 'open' && Number(app.state.session.deadline) > now();
  function localizedError(value) { const error = new Error(String(value)); error.localized = value; return error; }
  function errorText(data, status) {
    let detail = data?.detail ?? data?.error ?? data?.message;
    if (Array.isArray(detail)) {
      const issues = detail.map(item => typeof item === 'string' ? window.PodLocale.serverText(item) : t('Invalid value for {field}: {error}', { field: item.field || (item.loc || []).filter(v => v !== 'body').join('.'), error: window.PodLocale.serverText(item.message || item.msg) || t('Invalid input') }));
      // Resolve nested locale descriptors again after a language switch.
      return t('Validation issues: {issues}', { issues: { toString: () => issues.map(String).join('\n') } });
    }
    if (typeof detail === 'string' && detail) return window.PodLocale.serverText(detail);
    if (detail && typeof detail === 'object') detail = detail.message || JSON.stringify(detail);
    return typeof detail === 'string' && detail ? detail : ({ 401: t('Teacher secret is missing or incorrect.'), 403: t('Permission denied. Check your secret or claim token.'), 404: t('This record no longer exists. Refresh the classroom state.'), 409: t('This action conflicts with the current classroom state.'), 413: t('Python source exceeds the 32 KiB limit.'), 503: t('The Docker sandbox is unavailable. Ask the teacher to check Docker.') }[status] || t('Request failed (HTTP {status}).', { status }));
  }
  async function api(path, { method = 'GET', body, admin = false } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const headers = { Accept: 'application/json', 'Accept-Language': window.PodLocale.language };
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (admin && (view !== 'teacher' || !adminToken)) throw localizedError(t('Enter the teacher secret first.'));
      if (view === 'teacher' && adminToken) headers['X-Admin-Token'] = adminToken;
      const response = await fetch(basePath + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal, credentials: 'same-origin', cache: 'no-store' });
      let data;
      try { data = await response.json(); } catch { data = null; }
      if (!response.ok) { if (response.status === 401 && (path === '/api/state' || path === '/api/submissions' || path === '/api/practice' || path.startsWith('/api/replays/'))) lockClassroom(); const error = localizedError(errorText(data, response.status)); error.status = response.status; throw error; }
      if (data === null) throw localizedError(t('The server returned an unreadable response.'));
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw localizedError(t('The server did not respond in time. Try again.'));
      if (error instanceof TypeError) throw localizedError(t('Cannot reach the classroom server. Check your connection.'));
      throw error;
    } finally { clearTimeout(timer); }
  }
  function updateClock() {
    const session = app.state?.session;
    if (!session) return;
    const expired = session.status === 'open' && Number(session.deadline) <= now();
    text('session-status', humanStatus(expired ? 'closed' : session.status));
    text('countdown', session.status === 'open' && session.deadline ? formatTime(Number(session.deadline) - now()) : session.deadline ? '00:00:00' : '--:--:--');
    text('countdown-label', session.deadline ? (session.status === 'open' && !expired ? t('TIME TO SUBMIT') : t('WINDOW ENDED')) : t('Coding session'));
    updateControls();
  }
  function updateClaimHint() {
    const alias = $('alias').value.trim();
    const token = alias && claimFor(alias);
    const existing = app.state?.submissions?.find(entry => entry.alias.toLowerCase() === alias.toLowerCase());
    text('claim-hint', token ? t('Private claim token saved here. Submitting will update your existing pilot.') : existing ? t('This alias is already claimed. Import its private claim token to replace it, or choose your own alias.') : t('Your claim token will be saved in this browser after your first submission.'));
    $('export-claim').disabled = !token;
    updateControls();
  }
  function updateControls() {
    const active = app.state?.job?.status === 'running';
    const session = app.state?.session?.status;
    const adminReady = app.online && Boolean(adminToken) && !app.adminBusy && !active;
    const eligible = (app.state?.leaderboard || []).filter(row => !row.disqualified);
    const finalCount = Math.min(5, eligible.length);
    $('submit-bot').disabled = !isOpen() || app.submitBusy;
    text('submit-bot', app.submitBusy ? t('Submitting…') : !isOpen() ? (app.online ? t('Submissions are closed') : t('Connecting to classroom…')) : t('Submit your bot'));
    $('test-bot').disabled = !isOpen() || app.submitBusy || app.practiceBusy || !app.state?.sandbox?.available;
    text('test-bot', app.practiceBusy ? t('Testing…') : t('Test this code'));
    $('start-session').disabled = !adminReady || !['waiting', 'open', 'closed'].includes(session) || Boolean(app.state?.leaderboard?.length);
    $('submission-duration').disabled = $('start-session').disabled;
    text('start-session', t(session === 'open' ? 'Set remaining time' : 'Open coding session'));
    $('close-session').disabled = !adminReady || session !== 'open';
    $('qualify').disabled = !adminReady || !app.state?.submissions?.length || !app.state?.sandbox?.available || ['qualified', 'finished', 'final'].includes(session);
    $('run-final').disabled = !adminReady || !app.state?.sandbox?.available || session !== 'qualified' || finalCount < 2;
    text('run-final', t(finalCount === 1 ? 'Run final · {count} pilot' : 'Run final · {count} pilots', { count: finalCount }));
    text('final-hint', session === 'qualified' ? finalCount < 2 ? t(finalCount === 1 ? 'Only {count} eligible pilot. At least 2 are required for a final.' : 'Only {count} eligible pilots. At least 2 are required for a final.', { count: finalCount }) : t('{eligible} eligible after qualification. The best {count} will race together without collisions.', { eligible: eligible.length, count: finalCount }) : t('At least 2 eligible pilots are required. The final takes up to 5 from the frozen qualification results.'));
    $('seed-demo').disabled = !adminReady || session !== 'waiting' || Boolean(app.state?.submissions?.length);
    $('reset').disabled = !adminReady;
    $('inspect-code').disabled = !app.online || !adminToken || app.adminBusy || !$('inspect-select').value;
    $('confirm-reset').disabled = app.adminBusy;
    document.querySelectorAll('.delete-submission').forEach(button => { button.disabled = !adminReady; });
    $('confirm-delete').disabled = !adminReady || !pendingDelete;
    $('cancel-delete').disabled = app.adminBusy;
    const invitationReady = view === 'teacher' && app.online && Boolean(adminToken) && !app.adminBusy;
    $('create-invitation').disabled = !invitationReady;
    $('revoke-invitation').disabled = !invitationReady;
  }
  function syncSelect(id, items, emptyLabel, label) {
    const select = $(id);
    const previous = select.value;
    const signature = JSON.stringify([window.PodLocale.language, emptyLabel, items.map(item => [item.id, label(item)])]);
    if (select.dataset.signature === signature) return;
    select.dataset.signature = signature;
    select.replaceChildren();
    if (!items.length) { const option = document.createElement('option'); option.value = ''; option.textContent = emptyLabel; select.append(option); }
    for (const item of items) { const option = document.createElement('option'); option.value = item.id; option.textContent = label(item); select.append(option); }
    if (items.some(item => item.id === previous)) select.value = previous;
    select.disabled = !items.length;
  }
  function renderRoster() {
    const entries = app.state?.submissions || [];
    text('roster-count', entries.length);
    $('roster-scroll-hint').hidden = entries.length <= 6;
    const signature = window.PodLocale.language + JSON.stringify(entries.map(entry => [entry.id, entry.alias, entry.version]));
    if ($('roster').dataset.signature === signature) return;
    $('roster').dataset.signature = signature;
    $('roster').replaceChildren();
    if (!entries.length) { const li = document.createElement('li'); li.textContent = t('No pilots on the grid yet.'); $('roster').append(li); }
    for (const entry of entries) {
      const li = document.createElement('li'); const name = document.createElement('strong'); name.textContent = entry.alias;
      const version = document.createElement('span'); version.textContent = `v${entry.version}`; li.append(name, version);
      if (view === 'teacher') {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'danger delete-submission';
        button.textContent = t('Delete'); button.setAttribute('aria-label', t('Delete submission by {alias}', { alias: entry.alias }));
        button.addEventListener('click', () => openDeleteDialog(entry)); li.append(button);
      }
      $('roster').append(li);
    }
    syncSelect('inspect-select', entries, t('No submissions'), entry => `${entry.alias} · v${entry.version}`);
  }
  function replayTitle(replay) {
    if (!replay) return '';
    // Final titles are generated metadata; qualification titles can contain aliases.
    if (replay.kind === 'final') { const match = /^(?:Final|Finale) · (\d+) [^·]+$/.exec(replay.title || ''); if (match) return t('Final · {count} pods', { count: match[1] }); }
    return replay.title;
  }
  function renderState() {
    const state = app.state;
    if (!submissionDurationInitialized && !submissionDurationEdited) {
      const minutes = Math.ceil(Number(state.session?.duration_seconds) / 60);
      if (Number.isFinite(minutes) && minutes >= 1 && minutes <= 1440) $('submission-duration').value = String(minutes);
      submissionDurationInitialized = true;
    }
    text('entry-count', state.submissions.length);
    text('sandbox-label', state.sandbox.available ? t('Docker ready') : t('Docker unavailable'));
    $('sandbox-label').title = state.sandbox.detail || '';
    document.querySelector('.sandbox-status').classList.toggle('offline', !state.sandbox.available);
    const job = state.job;
    text('job-heading', job.status === 'running' ? t('{phase} running', { phase: t(job.phase === 'final' ? 'Final' : 'Qualification') }) : job.status === 'failed' ? t('Job failed') : job.status === 'finished' ? t('Job complete') : t('No job running'));
    const total = Math.max(1, Number(job.total) || 0);
    $('job-progress').max = total;
    $('job-progress').value = Math.min(total, Number(job.completed) || 0);
    text('job-detail', [job.message || (job.status === 'idle' ? t('Ready when the classroom is.') : ''), job.total ? `${job.completed} / ${job.total}` : '', job.error || ''].filter(Boolean).join(' · '));
    updateChampionLabel();
    // Projected playback must not reveal the winner before the race unfolds.
    syncSelect('replay-select', state.replays || [], t('No races yet'), replay => view === 'teacher' && replay.winner_alias ? t('{title} · Winner: {alias}', { title: replayTitle(replay), alias: replay.winner_alias }) : replayTitle(replay));
    if (app.replay) text('race-heading', replayTitle(app.localReplay ? app.replay : state.replays?.find(item => item.id === app.replayId)) || app.replay.track.name || t('Race replay'));
    if (app.follow) {
      const target = state.active_replay_id || (!app.replayId ? state.replays?.at(-1)?.id : app.replayId);
      if (target && target !== app.replayId) selectReplay(target);
    }
    if (app.replayId && (state.replays || []).some(replay => replay.id === app.replayId)) $('replay-select').value = app.replayId;
    if (!state.replays?.length && !state.active_replay_id && app.replayId && !app.localReplay) clearReplay();
    renderRoster(); updateClock(); updateClaimHint(); renderRankings();
    updateViewFocus();
    if (!app.replay && !app.replayId) renderEmptyState();
  }
  function renderEmptyState() {
    $('race-empty').hidden = false;
    $('race-empty').querySelector('h2').textContent = app.online ? t('No race has started.') : t('Arena connection unavailable.');
    $('race-empty').querySelector('p').textContent = app.online ? app.state?.sandbox?.available ? t(view === 'student' ? 'Test your code to watch your bot race here.' : view === 'teacher' ? 'Start qualification when the submissions are ready.' : 'The next classroom race will appear here.') : t('Submissions can be collected when the session is open, but racing is blocked until the teacher brings the Docker sandbox online.') : t('Reconnecting to the local classroom server. No results are being simulated.');
  }
  function updateViewFocus() {
    const hasReplay = Boolean(app.replay?.frames?.length);
    document.body.dataset.hasReplay = String(hasReplay);
    document.querySelector('.rank-panel').hidden = !hasReplay && !app.state?.leaderboard?.length;
    document.querySelector('.job-panel').hidden = !app.state?.job || app.state.job.status === 'idle';
    document.querySelector('.sandbox-status').hidden = view !== 'teacher' && Boolean(app.state?.sandbox?.available);
    $('final-hint').hidden = app.state?.session?.status !== 'qualified';
  }
  function lockClassroom() {
    document.body.dataset.access = 'unauthorized';
    $('join-panel').hidden = view === 'teacher';
    app.online = false; app.state = null; clearReplay();
    renderRoster(); renderRankings(); updateControls();
    text('entry-count', '—'); text('session-status', t('Classroom access required.'));
    $('replay-select').replaceChildren();
    delete $('replay-select').dataset.signature;
    if (view === 'teacher') { $('teacher-access').open = true; text('invitation-code', ''); text('invitation-status', ''); $('inspected-code').textContent = ''; }
  }
  $('join-form').addEventListener('submit', async event => {
    event.preventDefault();
    try {
      await api('/api/join', { method: 'POST', body: { code: $('join-code').value.trim() } });
      $('join-code').value = ''; message('join-message', ''); await pollState();
    } catch (error) { message('join-message', error.localized || error.message, 'error'); }
  });
  async function pollState() {
    if (app.stateBusy) return;
    app.stateBusy = true;
    const requestLanguage = window.PodLocale.language;
    try {
      const access = await api('/api/access');
      if (!access.authorized) { lockClassroom(); return; }
      document.body.dataset.access = 'authorized'; $('join-panel').hidden = true;
      const state = await api('/api/state');
      if (view === 'teacher' && adminToken) { const invitation = await api('/api/admin/access/invitation', { admin: true }); text('invitation-status', t(invitation.active ? 'Invitation active until {time}' : 'No active invitation', { time: invitation.active ? new Date(invitation.expires_at * 1000).toLocaleString(window.PodLocale.language) : '' })); }
      if (requestLanguage !== window.PodLocale.language) return;
      if (!state.session || !Array.isArray(state.submissions) || !state.sandbox || !state.job) throw localizedError(t('The classroom state is incomplete.'));
      const changedModeration = app.state && (app.state.moderation_revision || 0) !== (state.moderation_revision || 0);
      const removedReplay = app.replayId && !app.localReplay && !state.replays?.some(replay => replay.id === app.replayId);
      if (changedModeration || removedReplay) {
        clearReplay(); $('inspected-code').textContent = ''; $('inspected-code').hidden = true;
      }
      if (pendingDelete && !state.submissions.some(entry => entry.id === pendingDelete.id)) $('delete-dialog').close();
      app.state = state; app.online = true;
      app.clockOffset = Number.isFinite(state.server_time) ? state.server_time - Date.now() / 1000 : 0;
      text('connection-text', t('Server connected')); $('connection-dot').className = 'status-dot online'; notice('connection-error', '');
      renderState(); document.body.dataset.stateLanguage = requestLanguage;
    } catch (error) {
      app.online = false; text('connection-text', t('Disconnected')); $('connection-dot').className = 'status-dot offline';
      notice('connection-error', t(app.state ? '{error} Showing the last received classroom state; actions are disabled until reconnection.' : '{error} Waiting for the local server; no classroom data loaded.', { error: error.localized || error.message }));
      updateControls(); if (!app.replayId) renderEmptyState();
    } finally { app.stateBusy = false; if (requestLanguage !== window.PodLocale.language) pollState(); }
  }
  function setFollowing(follow) {
    app.follow = follow;
    $('follow-live').setAttribute('aria-pressed', String(follow));
    text('follow-live', follow ? t('Auto-follow: ON') : t('Auto-follow: OFF'));
  }
  function clearReplay() {
    app.replayId = null; app.replay = null; app.practiceReplay = null; app.localReplay = false; app.position = 0; app.finishTurns.clear(); app.processedFrames = 0;
    app.bounds = defaultBounds(); updateChampionLabel();
    text('race-heading', t('Waiting for the grid')); text('replay-status', t('NO REPLAY')); $('replay-status').classList.remove('live');
    text('track-name', t('Awaiting race')); text('race-format', '—');
    $('winner-overlay').hidden = true; text('winner-name', ''); text('winner-detail', ''); $('scrubber').disabled = true; $('play-pause').disabled = true; $('restart').disabled = true;
    text('turn-label', '0 / 0'); text('race-time', '00:00.0'); notice('replay-error', ''); renderEmptyState(); renderRankings();
    updateViewFocus();
  }
  function selectReplay(id) {
    if (!id || id === app.replayId) return;
    app.replayId = id; app.replay = null; app.practiceReplay = null; app.localReplay = false; app.position = 0; app.finishTurns.clear(); app.processedFrames = 0;
    app.bounds = defaultBounds(); updateChampionLabel();
    app.playing = !reducedMotion; app.lastRankingPaint = 0;
    $('race-empty').hidden = false; $('race-empty').querySelector('h2').textContent = t('Loading race…'); $('race-empty').querySelector('p').textContent = t('Fetching the recorded circuit and actual pod positions.');
    $('winner-overlay').hidden = true;
    text('replay-status', t('LOADING')); text('race-heading', replayTitle(app.state?.replays?.find(replay => replay.id === id)) || t('Race replay'));
    $('scrubber').disabled = true; $('play-pause').disabled = true; $('restart').disabled = true;
    updateViewFocus();
    refreshReplay(true);
  }
  async function refreshReplay(force = false) {
    if (!app.replayId || app.replayBusy || (!force && Date.now() - app.lastReplayFetch < 1000)) return;
    if (app.replay?.status !== 'running' && app.replay && !force) return;
    const id = app.replayId;
    const requestLanguage = window.PodLocale.language;
    app.replayBusy = true; app.lastReplayFetch = Date.now();
    try {
      const replay = app.localReplay ? app.practiceReplay : await api(`/api/replays/${encodeURIComponent(id)}`);
      if (!replay) throw localizedError(t('The replay could not be loaded. Choose a race or wait for the next server update.'));
      if (id !== app.replayId || requestLanguage !== window.PodLocale.language) return;
      if (!Array.isArray(replay.frames) || !Array.isArray(replay.entries) || !Array.isArray(replay.track?.checkpoints)) throw localizedError(t('The replay does not contain a valid circuit and frames.'));
      const firstLoad = !app.replay;
      const incomingFrames = replay.frames.length;
      if (incomingFrames < app.processedFrames) { app.processedFrames = 0; app.finishTurns.clear(); app.bounds = defaultBounds(); }
      for (let i = app.processedFrames; i < incomingFrames; i++) for (const pod of replay.frames[i].pods) {
        if (pod.finished && !app.finishTurns.has(pod.id)) app.finishTurns.set(pod.id, replay.frames[i].turn);
        if (Number.isFinite(pod.x) && Number.isFinite(pod.y)) {
          app.bounds.minX = Math.min(app.bounds.minX, pod.x - 1500);
          app.bounds.maxX = Math.max(app.bounds.maxX, pod.x + 1500);
          app.bounds.minY = Math.min(app.bounds.minY, pod.y - 1000);
          app.bounds.maxY = Math.max(app.bounds.maxY, pod.y + 1000);
        }
      }
      app.processedFrames = incomingFrames;
      app.replay = replay;
      updateViewFocus();
      if (firstLoad && replay.status === 'running' && !reducedMotion) app.position = Math.max(0, incomingFrames - 12);
      app.position = Math.min(app.position, Math.max(0, incomingFrames - 1));
      $('race-empty').hidden = incomingFrames > 0;
      if (!incomingFrames) { $('race-empty').querySelector('h2').textContent = t('Race is preparing…'); $('race-empty').querySelector('p').textContent = t('The worker has not published its first frame yet.'); }
      text('race-heading', replayTitle(app.localReplay ? replay : app.state?.replays?.find(item => item.id === id)) || replay.track.name || t('Race replay'));
      text('replay-status', ({ running: t('LIVE RACE'), finished: t('RECORDED'), interrupted: t('INTERRUPTED'), failed: t('RACE FAILED') }[replay.status] || t('REPLAY'))); $('replay-status').classList.toggle('live', replay.status === 'running');
      text('track-name', replay.track.name || replay.track.id || t('Classroom course'));
      text('race-format', t('{laps} laps · {pods} pods{contact}', { laps: replay.laps, pods: replay.entries.length, contact: t(replay.collisions ? ' · contact' : ' · ghosts') }));
      $('scrubber').max = Math.max(0, incomingFrames - 1); $('scrubber').disabled = incomingFrames < 2;
      $('play-pause').disabled = incomingFrames < 2; $('restart').disabled = incomingFrames < 1;
      notice('replay-error', ['interrupted', 'failed'].includes(replay.status) ? t('This race did not complete. Showing recorded frames only; no winner is declared.') : ''); renderRankings(); updatePlaybackUI();
    } catch (error) {
      if (id === app.replayId) {
        notice('replay-error', app.replay ? t('{error} Keeping the last received frames.', { error: error.localized || error.message }) : (error.localized || error.message));
        if (!app.replay) { $('race-empty').querySelector('h2').textContent = t('Replay unavailable'); $('race-empty').querySelector('p').textContent = t('The replay could not be loaded. Choose a race or wait for the next server update.'); text('replay-status', t('UNAVAILABLE')); }
      }
    } finally {
      app.replayBusy = false;
      if ((id !== app.replayId || requestLanguage !== window.PodLocale.language) && app.replayId) refreshReplay(true);
    }
  }
  function currentPods() {
    const frames = app.replay?.frames;
    if (!frames?.length) return [];
    const index = Math.max(0, Math.min(frames.length - 1, Math.floor(app.position)));
    return frames[index].pods;
  }
  function sortedPods() {
    const pods = [...currentPods()];
    const end = app.replay && app.position >= app.replay.frames.length - 1 && app.replay.status === 'finished';
    if (end && app.replay.results?.length) {
      const resultOrder = new Map(app.replay.results.map((result, index) => [result.id, index]));
      return pods.sort((a, b) => (resultOrder.get(a.id) ?? 99) - (resultOrder.get(b.id) ?? 99));
    }
    const checkpoints = app.replay?.track?.checkpoints || [];
    const distance = pod => { const cp = checkpoints[pod.next_checkpoint]; return cp ? Math.hypot(pod.x - cp[0], pod.y - cp[1]) : Infinity; };
    return pods.sort((a, b) => Number(a.disqualified) - Number(b.disqualified) || Number(b.finished) - Number(a.finished) || (a.finished && b.finished ? (app.finishTurns.get(a.id) ?? 0) - (app.finishTurns.get(b.id) ?? 0) : 0) || b.passed - a.passed || distance(a) - distance(b) || String(a.id).localeCompare(String(b.id)));
  }
  function pilotAlias(pilot) {
    const metadata = app.state?.replays?.find(item => item.id === app.replayId);
    const baseline = metadata?.kind === 'qualification' && app.replay?.entries?.length === 2 && pilot.id === app.replay.entries[1].id && !app.state?.submissions?.some(entry => entry.id === pilot.id);
    return baseline ? t('Reference ghost') : pilot.alias;
  }
  function colorFor(id) {
    const index = app.replay?.entries?.findIndex(entry => entry.id === id) ?? -1;
    return palette[index >= 0 ? index % palette.length : 0];
  }
  function cell(row, value, className = '') { const td = document.createElement('td'); td.textContent = String(value ?? '—'); td.className = className; row.append(td); return td; }
  function renderRankings() {
    const raceMode = app.ranking === 'race';
    const rows = raceMode ? sortedPods() : app.state?.leaderboard || [];
    text('rank-heading', raceMode ? t('Live race positions') : t('Qualification standings'));
    text('rank-eyebrow', raceMode ? t('ON THE CIRCUIT') : t('CLASSROOM RESULTS'));
    text('rank-count', t('{count} {kind}', { count: rows.length, kind: t(raceMode ? 'PODS' : 'ENTRIES') }));
    $('rankings').replaceChildren();
    if (!rows.length) { const p = document.createElement('p'); p.className = 'empty-copy'; p.textContent = raceMode ? t('Race positions appear when a replay has frames. No bots are being simulated in the browser.') : t('No qualifying results yet. Rankings appear after real races run.'); $('rankings').append(p); return; }
    const table = document.createElement('table'); table.className = 'rank-table';
    const caption = document.createElement('caption'); caption.className = 'visually-hidden'; caption.textContent = raceMode ? t('Positions in the displayed replay frame') : t('Qualification ranking across three courses'); table.append(caption);
    const thead = document.createElement('thead'); const heading = document.createElement('tr');
    for (const label of raceMode ? ['#', t('Pilot / status'), t('Lap'), t('Passed')] : ['#', t('Pilot'), t('Courses'), t('Turns')]) { const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; heading.append(th); }
    thead.append(heading); table.append(thead); const tbody = document.createElement('tbody');
    for (let index = 0; index < rows.length; index++) {
      const pilot = rows[index]; const row = document.createElement('tr');
      cell(row, raceMode ? index + 1 : pilot.rank ?? index + 1);
      const nameCell = cell(row, ''); const name = document.createElement('span'); name.className = 'pilot-name';
      const dot = document.createElement('span'); dot.className = 'pilot-dot'; dot.style.setProperty('--pod-color', raceMode ? colorFor(pilot.id) : 'var(--orange)');
      const alias = document.createElement('span'); alias.textContent = pilotAlias(pilot); name.append(dot, alias); nameCell.append(name);
      const meta = document.createElement('span'); meta.className = `pilot-meta status-text ${pilot.disqualified ? 'bad' : pilot.finished ? 'good' : ''}`;
      const finishedReplay = app.replay?.status === 'finished' && app.position >= app.replay.frames.length - 1;
      meta.textContent = pilot.disqualified ? `DQ${pilot.error ? ` · ${pilot.error}` : ''}` : raceMode ? pilot.finished ? t('Finished') : finishedReplay ? t('DNF · progress ranking') : pilot.boost_available ? t('Racing · boost ready') : t('Racing · boost used') : pilot.error || t('Eligible'); nameCell.append(meta);
      if (raceMode) { const cpCount = app.replay.track.checkpoints.length; const lap = pilot.finished ? app.replay.laps : Math.min(app.replay.laps, Math.floor((pilot.passed || 0) / Math.max(1, cpCount)) + 1); cell(row, `${lap}/${app.replay.laps}`, 'number'); cell(row, pilot.passed, 'number'); }
      else { cell(row, `${pilot.completed_tracks}/3`, 'number'); cell(row, pilot.total_turns, 'number'); }
      tbody.append(row);
    }
    table.append(tbody); $('rankings').append(table);
  }
  function chooseRanking(mode) {
    app.ranking = mode;
    for (const [name, buttonId] of [['qualification', 'tab-qualification'], ['race', 'tab-race']]) { $(buttonId).setAttribute('aria-selected', String(mode === name)); $(buttonId).tabIndex = mode === name ? 0 : -1; }
    $('rankings').setAttribute('aria-labelledby', mode === 'race' ? 'tab-race' : 'tab-qualification'); renderRankings();
  }
  function updateChampionLabel() {
    const champion = app.state?.champion;
    const finalReplay = !app.localReplay && app.state?.replays?.some(replay => replay.id === app.replayId && replay.id === app.replay?.id && replay.kind === 'final');
    const revealed = view === 'teacher' || (finalReplay && app.replay?.status === 'finished' && app.replay?.winner_id === champion?.id && app.replay.frames.length > 0 && app.position >= app.replay.frames.length - 1);
    text('champion-label', !champion ? t('No classroom champion yet.') : revealed ? t('CLASSROOM CHAMPION / {alias}', { alias: champion.alias }) : t('Final result revealed at the finish.'));
  }
  function updatePlaybackUI() {
    const frames = app.replay?.frames || [];
    const index = Math.min(frames.length - 1, Math.max(0, Math.floor(app.position)));
    const turn = frames[index]?.turn || 0;
    const lastTurn = frames[frames.length - 1]?.turn || 0;
    text('turn-label', `${turn} / ${lastTurn}`); $('scrubber').value = app.position;
    const seconds = turn / TURN_RATE;
    text('race-time', `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${(seconds % 60).toFixed(1).padStart(4, '0')}`);
    text('play-pause', app.playing ? t('Pause') : t('Play')); $('play-pause').setAttribute('aria-label', app.playing ? t('Pause replay') : t('Play replay'));
    const atEnd = app.replay?.status === 'finished' && frames.length && app.position >= frames.length - 1;
    const winnerId = app.replay?.winner_id;
    $('winner-overlay').hidden = !atEnd;
    if (atEnd) {
      const winner = app.replay.entries.find(entry => entry.id === winnerId);
      $('winner-overlay').querySelector('.eyebrow').textContent = winner ? t('RACE WINNER') : t('RACE COMPLETE');
      text('winner-name', winner ? winner.alias : t('No finishing winner'));
      text('winner-detail', winner ? t('{laps} laps · {pilots} pilots', { laps: app.replay.laps, pilots: app.replay.entries.length }) : t('See standings for finishing status and progress.'));
    }
    updateChampionLabel();
  }
  function togglePlay() {
    if (!app.replay?.frames?.length) return;
    if (!app.playing && app.position >= app.replay.frames.length - 1 && app.replay.status === 'finished') app.position = 0;
    app.playing = !app.playing; updatePlaybackUI();
  }
  function seek(position) {
    if (!app.replay?.frames?.length) return;
    app.position = Math.max(0, Math.min(app.replay.frames.length - 1, position)); app.playing = false;
    updatePlaybackUI(); renderRankings();
  }
  async function fullscreen() {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else if ($('race-canvas').closest('.race-panel').requestFullscreen) await $('race-canvas').closest('.race-panel').requestFullscreen(); else throw localizedError(t('Fullscreen is not supported by this browser.')); }
    catch (error) { notice('replay-error', error.localized || t('Fullscreen was denied by the browser.')); }
  }
  // Canvas rendering never evaluates student source; all geometry comes from server frames.
  const canvas = $('race-canvas');
  const ctx = canvas.getContext('2d');
  let canvasWidth = 1, canvasHeight = 1, dpr = 1;
  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect(); canvasWidth = Math.max(1, rect.width); canvasHeight = Math.max(1, rect.height); dpr = Math.min(3, devicePixelRatio || 1);
    canvas.width = Math.round(canvasWidth * dpr); canvas.height = Math.round(canvasHeight * dpr);
  }
  new ResizeObserver(resizeCanvas).observe($('race-stage')); window.addEventListener('resize', resizeCanvas); resizeCanvas();
  function paintRace() {
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, canvasWidth, canvasHeight);
    ctx.fillStyle = '#101a20'; ctx.fillRect(0, 0, canvasWidth, canvasHeight);
    const margin = Math.max(24, Math.min(45, canvasWidth * .045));
    // Replay-wide bounds keep drifting pods on screen without per-frame camera jitter.
    const bounds = app.bounds;
    const worldWidth = bounds.maxX - bounds.minX, worldHeight = bounds.maxY - bounds.minY;
    const scale = Math.min((canvasWidth - margin * 2) / worldWidth, (canvasHeight - margin * 2) / worldHeight);
    const offsetX = (canvasWidth - worldWidth * scale) / 2 - bounds.minX * scale, offsetY = (canvasHeight - worldHeight * scale) / 2 - bounds.minY * scale;
    const point = (x, y) => [offsetX + x * scale, offsetY + y * scale];
    ctx.strokeStyle = '#243139'; ctx.lineWidth = .6;
    const gridStep = Math.max(1000, Math.ceil(Math.max(worldWidth, worldHeight) / 20000) * 1000);
    for (let x = Math.ceil(bounds.minX / gridStep) * gridStep; x <= bounds.maxX; x += gridStep) { const [sx] = point(x, 0); ctx.beginPath(); ctx.moveTo(sx, point(0, bounds.minY)[1]); ctx.lineTo(sx, point(0, bounds.maxY)[1]); ctx.stroke(); }
    for (let y = Math.ceil(bounds.minY / gridStep) * gridStep; y <= bounds.maxY; y += gridStep) { const [, sy] = point(0, y); ctx.beginPath(); ctx.moveTo(point(bounds.minX, 0)[0], sy); ctx.lineTo(point(bounds.maxX, 0)[0], sy); ctx.stroke(); }
    ctx.strokeStyle = '#3c4a52'; ctx.strokeRect(offsetX, offsetY, 16000 * scale, 9000 * scale);
    const replay = app.replay;
    if (!replay) { ctx.fillStyle = '#778991'; ctx.font = '10px Consolas, monospace'; ctx.fillText(t('CIRCUIT / 16 000 × 9 000'), offsetX + 12, offsetY + 19); return; }
    const checkpoints = replay.track.checkpoints;
    if (!checkpoints.length) return;
    const pods = currentPods();
    const currentTargets = new Set(pods.filter(pod => !pod.finished && !pod.disqualified).map(pod => pod.next_checkpoint));
    const leader = sortedPods().find(pod => !pod.finished && !pod.disqualified);
    const path = () => { ctx.beginPath(); checkpoints.forEach(([x, y], i) => { const p = point(x, y); if (i === 0) ctx.moveTo(...p); else ctx.lineTo(...p); }); ctx.closePath(); };
    ctx.lineJoin = 'round'; path(); ctx.strokeStyle = '#243139'; ctx.lineWidth = Math.max(24, scale * 1100); ctx.stroke();
    path(); ctx.strokeStyle = '#61747d'; ctx.lineWidth = 1; ctx.setLineDash([5, 9]); ctx.stroke(); ctx.setLineDash([]);
    checkpoints.forEach(([x, y], index) => {
      const [sx, sy] = point(x, y); const radius = Math.max(12, scale * 600); const active = currentTargets.has(index);
      ctx.beginPath(); ctx.arc(sx, sy, radius + 5, 0, Math.PI * 2); ctx.fillStyle = '#101a20e8'; ctx.fill();
      ctx.beginPath(); ctx.arc(sx, sy, radius, 0, Math.PI * 2); ctx.strokeStyle = active ? '#ffb268' : '#9dabb0'; ctx.lineWidth = leader?.next_checkpoint === index ? 2.7 : 1.3; ctx.stroke();
      if (active) { ctx.beginPath(); ctx.arc(sx, sy, radius + 5, -.6, .6); ctx.strokeStyle = '#ffb268'; ctx.lineWidth = 2; ctx.stroke(); }
      ctx.fillStyle = active ? '#ffce9f' : '#d3dbe0'; ctx.font = `600 ${Math.max(11, Math.min(17, canvasWidth / 65))}px Consolas, monospace`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(String(index + 1).padStart(2, '0'), sx, sy);
    });
    const frames = replay.frames;
    const frameIndex = Math.max(0, Math.min(frames.length - 1, Math.floor(app.position)));
    const next = frames[Math.min(frameIndex + 1, frames.length - 1)];
    const fraction = reducedMotion ? 0 : app.position - frameIndex;
    const nextPods = new Map((next?.pods || []).map(pod => [pod.id, pod]));
    const labelBoxes = [];
    for (const pod of pods) {
      const color = colorFor(pod.id); const future = nextPods.get(pod.id) || pod;
      const x = pod.x + (future.x - pod.x) * fraction, y = pod.y + (future.y - pod.y) * fraction;
      const [px, py] = point(x, y);
      if (!Number.isFinite(px) || !Number.isFinite(py)) continue;
      // A fixed 18-frame tail: bounded work as the replay grows.
      ctx.beginPath(); let started = false;
      for (let f = Math.max(0, frameIndex - 18); f <= frameIndex; f++) {
        const trailPod = frames[f]?.pods.find(p => p.id === pod.id); if (!trailPod) continue;
        const p = point(trailPod.x, trailPod.y); if (!started) { ctx.moveTo(...p); started = true; } else ctx.lineTo(...p);
      }
      ctx.lineTo(px, py); ctx.strokeStyle = color; ctx.globalAlpha = pod.disqualified ? .18 : .48; ctx.lineWidth = Math.max(1.5, scale * 90); ctx.stroke(); ctx.globalAlpha = 1;
      const podNumber = replay.entries.findIndex(entry => entry.id === pod.id) + 1;
      const radius = Math.max(7, scale * 260);
      let deltaAngle = ((future.angle - pod.angle + 540) % 360) - 180;
      if (!Number.isFinite(deltaAngle)) deltaAngle = 0;
      ctx.save(); ctx.translate(px, py); ctx.rotate((pod.angle + deltaAngle * fraction) * Math.PI / 180);
      ctx.globalAlpha = pod.disqualified ? .42 : 1;
      ctx.beginPath(); ctx.moveTo(radius * 1.65, 0); ctx.lineTo(-radius, -radius * .85); ctx.lineTo(-radius * .6, 0); ctx.lineTo(-radius, radius * .85); ctx.closePath();
      ctx.fillStyle = color; ctx.fill(); ctx.strokeStyle = '#081015'; ctx.lineWidth = 1.5; ctx.stroke();
      if (pod.disqualified) { ctx.beginPath(); ctx.moveTo(-radius, -radius); ctx.lineTo(radius, radius); ctx.moveTo(-radius, radius); ctx.lineTo(radius, -radius); ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.8; ctx.stroke(); }
      ctx.restore();
      const fontSize = Math.max(10, Math.min(14, canvasWidth / 75)); ctx.font = `600 ${fontSize}px Segoe UI, Arial, sans-serif`;
      const label = `${podNumber}. ${pilotAlias(pod)}${pod.disqualified ? t(' / DQ') : pod.finished ? t(' / FIN') : ''}`;
      const labelWidth = Math.min(canvasWidth - 12, ctx.measureText(label).width + 12), labelHeight = fontSize + 10;
      let lx = Math.max(6, Math.min(canvasWidth - labelWidth - 6, px + radius + 6));
      let ly = Math.max(6, Math.min(canvasHeight - labelHeight - 28, py - radius - labelHeight));
      for (let attempt = 0; attempt < 6 && labelBoxes.some(box => lx < box.x + box.w && lx + labelWidth > box.x && ly < box.y + box.h && ly + labelHeight > box.y); attempt++) ly = Math.min(canvasHeight - labelHeight - 28, ly + labelHeight + 3);
      labelBoxes.push({ x: lx, y: ly, w: labelWidth, h: labelHeight });
      ctx.fillStyle = '#101a20ec'; ctx.fillRect(lx, ly, labelWidth, labelHeight); ctx.strokeStyle = color; ctx.lineWidth = .8; ctx.strokeRect(lx, ly, labelWidth, labelHeight);
      ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillStyle = color; ctx.fillText(label, lx + 6, ly + labelHeight / 2, labelWidth - 12);
    }
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic'; ctx.globalAlpha = 1;
  }
  function animate(timestamp) {
    const delta = app.lastAnimation ? Math.min(.1, (timestamp - app.lastAnimation) / 1000) : 0; app.lastAnimation = timestamp;
    const frames = app.replay?.frames;
    if (app.playing && frames?.length) {
      app.position = Math.min(frames.length - 1, app.position + delta * TURN_RATE * app.speed);
      if (app.position >= frames.length - 1 && app.replay.status !== 'running') app.playing = false;
    }
    paintRace();
    if (timestamp - app.lastRankingPaint > 250) { app.lastRankingPaint = timestamp; updatePlaybackUI(); if (app.ranking === 'race') renderRankings(); }
    requestAnimationFrame(animate);
  }
  function sourceSize() {
    if ($('code').value.trim()) { $('code').setCustomValidity(''); delete $('code').dataset.validationKey; }
    const size = new TextEncoder().encode($('code').value).byteLength;
    text('code-size', `${(size / 1024).toLocaleString(window.PodLocale.language, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} / 32 KiB`); $('code-size').style.color = size > 32768 ? 'var(--red)' : ''; return size;
  }
  $('alias').value = safeGet(localStorage, `${storagePrefix}:last-alias`);
  const validationKeys = { alias: 'Enter your pilot alias.', code: 'Paste your Python code.', 'admin-token': 'Enter the teacher secret.', 'reset-confirm': 'Type RESET to confirm.' };
  for (const [id, key] of Object.entries(validationKeys)) {
    $(id).addEventListener('invalid', () => { $(id).setCustomValidity(String(t(key))); $(id).dataset.validationKey = key; });
    $(id).addEventListener('input', () => { $(id).setCustomValidity(''); delete $(id).dataset.validationKey; });
  }
  $('alias').addEventListener('input', updateClaimHint);
  $('code').addEventListener('input', sourceSize);
  $('code').addEventListener('keydown', event => {
    if (event.key === 'Tab' && !event.shiftKey && event.ctrlKey) { event.preventDefault(); const editor = event.target; editor.setRangeText('    ', editor.selectionStart, editor.selectionEnd, 'end'); sourceSize(); }
  });
  $('code-file').addEventListener('change', async event => {
    const file = event.target.files[0]; if (!file) return;
    if (!file.name.toLowerCase().endsWith('.py')) { message('submission-message', t('Choose a Python .py file.'), 'error'); event.target.value = ''; return; }
    if (file.size > 32768) { message('submission-message', t('The file exceeds 32 KiB. Choose a smaller Python source file.'), 'error'); event.target.value = ''; return; }
    try { $('code').value = await file.text(); sourceSize(); message('submission-message', t('Loaded {filename}. Review the code, then submit.', { filename: file.name })); }
    catch { message('submission-message', t('The selected file could not be read.'), 'error'); }
    event.target.value = '';
  });
  async function saveSubmission() {
    if (app.submitBusy) return false;
    if (!isOpen()) { message('submission-message', t('The submission window is closed. Ask the teacher to open it.'), 'error'); return false; }
    const alias = $('alias').value.trim(), code = $('code').value;
    if (!/^[\p{L}\p{N} _-]{1,24}$/u.test(alias)) { message('submission-message', t('Use 1–24 letters, numbers, spaces, _ or - for your alias.'), 'error'); $('alias').focus(); return false; }
    if (!code.trim() || sourceSize() > 32768) { message('submission-message', t('Paste Python code no larger than 32 KiB.'), 'error'); $('code').focus(); return false; }
    app.submitBusy = true; updateControls(); message('submission-message', t('Checking Python syntax and saving…'));
    try {
      const claim = claimFor(alias); const payload = { alias, code }; if (claim) payload.claim_token = claim;
      const result = await api('/api/submissions', { method: 'POST', body: payload });
      if (!result.id || !result.claim_token || !result.alias) throw localizedError(t('The server did not return a valid submission claim.'));
      memoryClaims.set(result.alias.trim().toLowerCase(), result.claim_token);
      const stored = safeSet(localStorage, aliasKey(result.alias), result.claim_token);
      safeSet(localStorage, `${storagePrefix}:last-alias`, result.alias); $('alias').value = result.alias;
      $('claim-token').value = result.claim_token;
      message('submission-message', t('{alias} saved · version {version}.{storage}', { alias: result.alias, version: result.version, storage: t(stored ? ' Claim token saved in this browser.' : ' Browser storage is unavailable. Download your private claim token now before leaving this tab.') }), 'success');
      if (!stored) { $('export-claim').disabled = false; $('export-claim').dataset.unsaved = result.claim_token; }
      await pollState(); updateClaimHint();
      if (!stored) $('export-claim').disabled = false;
      return true;
    } catch (error) { message('submission-message', error.localized || error.message, 'error'); return false; }
    finally { app.submitBusy = false; updateControls(); }
  }
  $('submission-form').addEventListener('submit', async event => { event.preventDefault(); await saveSubmission(); });
  $('test-bot').addEventListener('click', async () => {
    if (app.practiceBusy || !await saveSubmission()) return;
    const alias = $('alias').value.trim(), claim_token = claimFor(alias);
    if (!claim_token) { message('submission-message', t('Your private claim token is unavailable. Save your bot once, then try again.'), 'error'); return; }
    app.practiceBusy = true; updateControls(); message('submission-message', t('Testing your bot in the sandbox…'));
    try {
      const replay = await api('/api/practice', { method: 'POST', body: { alias, claim_token } });
      if (!Array.isArray(replay.frames) || !Array.isArray(replay.entries)) throw localizedError(t('The server returned an unreadable response.'));
      app.practiceReplay = replay; app.localReplay = true; app.replayId = replay.id; app.replay = null; app.position = 0; app.finishTurns.clear(); app.processedFrames = 0; app.bounds = defaultBounds();
      app.playing = !reducedMotion;
      setFollowing(false); chooseRanking('race'); await refreshReplay(true); message('submission-message', t('Practice replay ready.'), 'success');
    } catch (error) { message('submission-message', error.localized || error.message, 'error'); }
    finally { app.practiceBusy = false; updateControls(); }
  });
  $('save-claim').addEventListener('click', () => {
    const alias = $('alias').value.trim(), token = $('claim-token').value.trim();
    if (!alias || !token) { text('claim-message', t('Enter the pilot alias above and its existing private token.')); return; }
    const saved = safeSet(localStorage, aliasKey(alias), token);
    if (!saved) { text('claim-message', t('Browser storage is blocked. The token will be used for this tab only.')); memoryClaims.set(alias.toLowerCase(), token); }
    else text('claim-message', t('Private claim token saved for this alias.'));
    updateClaimHint();
  });
  function downloadClaim() {
    const alias = $('alias').value.trim(); const token = claimFor(alias) || memoryClaims.get(alias.toLowerCase()) || $('export-claim').dataset.unsaved;
    if (!token) { text('claim-message', t('No saved claim token for this alias.')); return; }
    const blob = new Blob([JSON.stringify({ alias, claim_token: token }, null, 2) + '\n'], { type: 'application/json' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'pod-lab-private-claim.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    text('claim-message', t('Private claim file downloaded. Keep it private; copy the claim_token value to restore on another browser.'));
  }
  $('export-claim').addEventListener('click', downloadClaim);
  async function loadRules() {
    const content = $('rules-content');
    if (content.hidden || content.dataset.loaded) return;
    content.textContent = t('Loading server rules…');
    const requestLanguage = window.PodLocale.language;
    try { const rules = await api('/api/rules'); if (requestLanguage !== window.PodLocale.language) return; const pre = document.createElement('pre'); pre.textContent = typeof rules === 'string' ? rules : JSON.stringify(rules, null, 2); content.replaceChildren(pre); content.dataset.loaded = 'true'; }
    catch (error) { content.textContent = error.message; }
  }
  $('rules-toggle').addEventListener('click', event => { event.preventDefault(); $('rules-content').hidden = !$('rules-content').hidden; loadRules(); });
  function authStatus() {
    $('admin-token').value = adminToken;
    $('teacher-access').open = !adminToken;
    text('auth-status', adminToken ? t('Key saved in this tab. Authorization is checked by the server on each admin request.') : t('Enter the teacher secret to enable controls.')); updateControls();
  }
  $('admin-auth').addEventListener('submit', event => { event.preventDefault(); adminToken = $('admin-token').value.trim(); const saved = safeSet(sessionStorage, `${storagePrefix}:admin`, adminToken); authStatus(); if (!saved) text('auth-status', t('Browser storage is blocked. Key kept only until this page reloads.')); pollState(); });
  $('forget-key').addEventListener('click', () => { adminToken = ''; text('invitation-code', ''); text('invitation-status', ''); safeSet(sessionStorage, `${storagePrefix}:admin`, ''); $('inspected-code').textContent = ''; $('inspected-code').hidden = true; authStatus(); pollState(); });
  async function adminAction(path, body, success, method = 'POST') {
    if (app.adminBusy) return false;
    app.adminBusy = true; updateControls(); message('admin-message', t('Sending request…'));
    try {
      await api(path, { method, body: method === 'DELETE' ? undefined : body ?? {}, admin: true });
      // A pre-delete poll must finish before the authoritative readback starts.
      if (method === 'DELETE') while (app.stateBusy) await new Promise(resolve => setTimeout(resolve, 25));
      await pollState();
      message('admin-message', app.online ? success : t('{success} The server accepted the action, but the public state refresh failed; verify after reconnection.', { success }), app.online ? 'success' : ''); return true;
    } catch (error) {
      message('admin-message', error.localized || error.message, 'error'); if (error.status === 401 || error.status === 403) { $('teacher-access').open = true; text('auth-status', t('The server rejected this key. Check the secret in the server console.')); } await pollState(); return false;
    } finally { app.adminBusy = false; updateControls(); }
  }
  async function invitationAction(revoke) {
    if (app.adminBusy || !adminToken) return;
    const duration = Number($('invitation-duration').value);
    if (!revoke && (!Number.isInteger(duration) || duration < 1 || duration > 86400)) { message('invitation-status', t('Use 1–86400 seconds.'), 'error'); return; }
    app.adminBusy = true; updateControls();
    try {
      const result = await api(revoke ? '/api/admin/access/revoke' : '/api/admin/access/invitation', { method: 'POST', admin: true, body: revoke ? {} : { duration_seconds: duration } });
      text('invitation-code', revoke ? '' : result.code); await pollState();
    } catch (error) { message('invitation-status', error.localized || error.message, 'error'); }
    finally { app.adminBusy = false; updateControls(); }
  }
  $('create-invitation').addEventListener('click', () => invitationAction(false));
  $('revoke-invitation').addEventListener('click', () => invitationAction(true));
  $('submission-duration').addEventListener('input', () => { submissionDurationEdited = true; });
  $('start-session').addEventListener('click', () => {
    if ($('start-session').disabled) return;
    const field = $('submission-duration');
    const minutes = Number(field.value);
    if (!field.value.trim() || !Number.isInteger(minutes) || minutes < 1 || minutes > 1440) {
      message('admin-message', t('Choose whole minutes from 1 to 1440.'), 'error'); field.focus(); return;
    }
    const success = t(app.state?.session?.status === 'open' ? 'Remaining submission time updated.' : 'Coding session opened.');
    adminAction('/api/admin/session/start', { duration_seconds: minutes * 60 }, success);
  });
  $('close-session').addEventListener('click', () => adminAction('/api/admin/session/close', {}, t('Submission session closed.')));
  $('seed-demo').addEventListener('click', () => adminAction('/api/admin/demo', {}, t('Example bots inserted. Run qualification to produce actual results.')));
  $('qualify').addEventListener('click', () => { if (app.state?.submissions?.length && confirm(t('Close submissions and freeze the current bots for qualification on 3 common courses?'))) { setFollowing(true); adminAction('/api/admin/qualify', {}, t('Qualification accepted. Follow worker progress and live replays.')); } });
  $('run-final').addEventListener('click', () => { setFollowing(true); chooseRanking('race'); adminAction('/api/admin/final', {}, t('Final accepted. The eligible finalists race together on the showcase circuit.')); });
  $('reset').addEventListener('click', () => { $('reset-confirm').value = ''; $('reset-dialog').showModal(); $('reset-confirm').focus(); });
  $('cancel-reset').addEventListener('click', () => $('reset-dialog').close());
  $('reset-form').addEventListener('submit', async event => { event.preventDefault(); if ($('reset-confirm').value !== 'RESET') return; if (await adminAction('/api/admin/reset', { confirm: 'RESET' }, t('Classroom reset. Open a new session when ready.'))) { $('reset-dialog').close(); setFollowing(true); clearReplay(); $('inspected-code').textContent = ''; $('inspected-code').hidden = true; } });
  let pendingDelete = null;
  function openDeleteDialog(entry) {
    if (view !== 'teacher' || !adminToken || app.adminBusy || !app.online || app.state?.job?.status === 'running') return;
    pendingDelete = { id: entry.id, alias: entry.alias };
    text('delete-alias', entry.alias); $('delete-dialog').showModal(); updateControls(); $('cancel-delete').focus();
  }
  $('cancel-delete').addEventListener('click', () => $('delete-dialog').close());
  $('delete-dialog').addEventListener('cancel', event => { if (app.adminBusy) event.preventDefault(); });
  $('delete-dialog').addEventListener('close', () => { pendingDelete = null; updateControls(); });
  $('delete-form').addEventListener('submit', async event => {
    event.preventDefault(); const target = pendingDelete;
    if (!target || app.adminBusy || $('confirm-delete').disabled) return;
    if (await adminAction(`/api/admin/submissions/${encodeURIComponent(target.id)}`, undefined, t('Submission deleted. Other pilots are kept.'), 'DELETE')) {
      $('delete-dialog').close(); $('inspected-code').textContent = ''; $('inspected-code').hidden = true;
    }
  });
  $('inspect-select').addEventListener('change', updateControls);
  $('inspect-code').addEventListener('click', async () => {
    const id = $('inspect-select').value; if (!id || app.adminBusy) return;
    const revision = app.state?.moderation_revision || 0;
    app.adminBusy = true; updateControls();
    try { const data = await api(`/api/admin/submissions/${encodeURIComponent(id)}`, { admin: true }); if (revision !== (app.state?.moderation_revision || 0) || !app.state?.submissions?.some(entry => entry.id === id)) return; if (typeof data.code !== 'string') throw localizedError(t('This submission has no readable source code.')); $('inspected-code').textContent = data.code; $('inspected-code').hidden = false; message('admin-message', t('Teacher-only source loaded.'), 'success'); }
    catch (error) { message('admin-message', error.localized || error.message, 'error'); }
    finally { app.adminBusy = false; updateControls(); }
  });
  $('replay-select').addEventListener('change', event => { setFollowing(false); selectReplay(event.target.value); });
  $('follow-live').addEventListener('click', () => { setFollowing(!app.follow); if (app.follow) { const id = app.state?.active_replay_id || app.state?.replays?.at(-1)?.id; if (id) selectReplay(id); } });
  $('play-pause').addEventListener('click', togglePlay);
  $('restart').addEventListener('click', () => seek(0));
  $('scrubber').addEventListener('input', event => seek(Number(event.target.value)));
  $('speed').addEventListener('change', event => { app.speed = Number(event.target.value); });
  $('fullscreen').addEventListener('click', fullscreen);
  document.addEventListener('fullscreenchange', () => { text('fullscreen', document.fullscreenElement ? t('Exit fullscreen') : t('Fullscreen')); resizeCanvas(); });
  $('tab-qualification').addEventListener('click', () => chooseRanking('qualification')); $('tab-race').addEventListener('click', () => chooseRanking('race'));
  document.querySelector('.ranking-tabs').addEventListener('keydown', event => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); const mode = event.key === 'Home' ? 'qualification' : event.key === 'End' ? 'race' : app.ranking === 'race' ? 'qualification' : 'race'; chooseRanking(mode); $(mode === 'race' ? 'tab-race' : 'tab-qualification').focus(); }
  });
  document.addEventListener('keydown', event => {
    if (event.target.closest('input,textarea,select,button,a,summary,dialog') || event.ctrlKey || event.altKey || event.metaKey) return;
    if (event.code === 'Space' && app.replay) { event.preventDefault(); togglePlay(); }
    else if (event.key === 'ArrowLeft' && app.replay) { event.preventDefault(); seek(app.position - 10); }
    else if (event.key === 'ArrowRight' && app.replay) { event.preventDefault(); seek(app.position + 10); }
    else if (event.key.toLowerCase() === 'f') fullscreen();
  });
  function changeLanguage(value) {
    window.PodLocale.setLanguage(value); updateTitle();
    // Keep shared-link overrides in step with an explicit user choice.
    const url = new URL(location.href); url.searchParams.set('lang', window.PodLocale.language); history.replaceState(null, '', url);
    for (const [id, value] of localizedFields) $(id).textContent = String(value ?? '');
    for (const id of Object.keys(validationKeys)) if ($(id).dataset.validationKey) $(id).setCustomValidity(String(t($(id).dataset.validationKey)));
    setFollowing(app.follow); updateClock(); updateClaimHint(); updatePlaybackUI(); renderRankings(); renderRoster(); sourceSize();
    text('fullscreen', t(document.fullscreenElement ? 'Exit fullscreen' : 'Fullscreen'));
    if (!app.replayId) renderEmptyState();
    const rules = $('rules-content'); delete rules.dataset.loaded; if (!rules.hidden) loadRules();
    // Localized API copies must be fetched again; do not change replay transport.
    pollState(); refreshReplay(true);
  }
  $('language-switch').addEventListener('change', event => changeLanguage(event.target.value));
  authStatus(); updateClaimHint(); sourceSize(); chooseRanking(app.ranking);
  pollState(); setInterval(pollState, 2000); setInterval(() => refreshReplay(), 1000); setInterval(updateClock, 500); requestAnimationFrame(animate);
})();
