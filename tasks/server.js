// Tasks — a 10-foot task list app.  Start with:  node server.js
// No npm install needed (Node 18+). Data is stored in ./data.json.
'use strict';
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');

const PORT = Number(process.env.PORT) || 3000;
const DATA_FILE = process.env.TASKS_DATA || path.join(__dirname, 'data.json');
const PUBLIC = path.join(__dirname, 'public');
const REMIND_LEAD_MIN = Number(process.env.REMIND_LEAD_MIN) || 15; // pop up this many minutes before due

// ---------- storage ----------
const blank = () => ({ lists: [], frequent: {}, pinned: [], webhooks: [], version: 1 });
let db = blank();
try { db = Object.assign(blank(), JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'))); }
catch (e) { if (e.code !== 'ENOENT') console.error('Could not read data file, starting fresh:', e.message); }

let saveTimer = null;
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const tmp = DATA_FILE + '.tmp';
    fs.writeFile(tmp, JSON.stringify(db, null, 2), err => {
      if (err) return console.error('save failed', err);
      fs.rename(tmp, DATA_FILE, e => e && console.error('save failed', e));
    });
  }, 150);
}
const id = () => crypto.randomBytes(6).toString('base64url');
const now = () => Date.now();

// ---------- live events (SSE) ----------
const clients = new Set();
function broadcast(type, data) {
  const msg = `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const res of clients) res.write(msg);
}
function changed(listId) { save(); broadcast('change', { listId, at: now() }); }

// ---------- webhooks (tie-in for other apps) ----------
function fireWebhooks(event, payload) {
  for (const url of db.webhooks) {
    try {
      const body = JSON.stringify({ event, ...payload });
      fetch(url, { method: 'POST', headers: { 'content-type': 'application/json' }, body, signal: AbortSignal.timeout(5000) })
        .catch(err => console.warn('webhook failed', url, err.message));
    } catch (e) { console.warn('bad webhook', url, e.message); }
  }
}

// ---------- anTV pop-up protocol (https://… see anTV_Popup_Protocol_Spec.md) ----------
// anTV (and any app that speaks the protocol) listens to /api/events for 'popup' events and shows them
// on top of whatever is running. Action URLs are relative: the listener resolves them against this server.
function toPopup({ task: t, overdue, test }) {
  const when = new Date(t.due).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  const u = `/api/lists/${t.listId}/tasks/${t.id}`;
  return {
    id: `task:${t.id}:${t.due}:${t.snoozeUntil || 0}`, title: t.text,
    tag: `${t.listName} \u00b7 ${overdue ? 'Overdue' : 'Due ' + when}`, color: t.color,
    priority: overdue ? 'high' : 'normal', test: !!test,
    actions: test ? [] : [
      { label: '\u2713 Done', method: 'PATCH', url: u, body: { done: true } },
      { label: '\u23f0 10 min', method: 'POST', url: u + '/snooze', body: { minutes: 10 } },
      { label: 'Open', kind: 'open' },
    ],
  };
}
const MANIFEST = { protocol: 1, name: 'Tasks', color: '#ffb84d', events: '/api/events', open: '/',
  description: 'Reminders for tasks that are due' };

// ---------- reminders ----------
function taskView(list, t) {
  return { listId: list.id, listName: list.name, color: list.color, ...t };
}
function dueTasks(withinMin) {
  const limit = now() + withinMin * 60000;
  const out = [];
  for (const l of db.lists) if (!l.archived) for (const t of l.tasks)
    if (!t.done && t.due && t.due <= limit) out.push(taskView(l, t));
  return out.sort((a, b) => a.due - b.due);
}
setInterval(() => {
  const lead = now() + REMIND_LEAD_MIN * 60000;
  for (const l of db.lists) if (!l.archived) for (const t of l.tasks) {
    if (t.done || !t.due || t.notified) continue;
    if (t.snoozeUntil ? t.snoozeUntil <= now() : t.due <= lead) {
      t.notified = true;
      const payload = { task: taskView(l, t), overdue: t.due < now() };
      broadcast('due', payload);
      broadcast('popup', toPopup(payload));
      fireWebhooks('task.due', payload);
      save();
    }
  }
}, 20000);

// ---------- helpers ----------
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.webmanifest': 'application/manifest+json' };
const COLORS = ['#ffb84d', '#5ec8ff', '#7ee08a', '#ff7aa8', '#b49bff', '#ffd95e', '#4fe0c8', '#ff8a5c'];

function send(res, code, body, type = 'application/json') {
  res.writeHead(code, { 'content-type': type, 'cache-control': 'no-store' });
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    let s = '';
    req.on('data', c => { s += c; if (s.length > 1e6) { reject(new Error('too large')); req.destroy(); } });
    req.on('end', () => { try { resolve(s ? JSON.parse(s) : {}); } catch { reject(new Error('bad json')); } });
  });
}
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const findList = lid => db.lists.find(l => l.id === lid);
const cleanText = s => String(s || '').trim().replace(/\s+/g, ' ').slice(0, 300);
function normDue(v) {
  if (v === null || v === '' || v === undefined) return null;
  const n = typeof v === 'number' ? v : Date.parse(v);
  return Number.isFinite(n) ? n : null;
}
function remember(text) {
  const k = text.toLowerCase();
  db.frequent[k] = (db.frequent[k] || 0) + 1;
}
function frequentList() {
  const pinnedSet = new Set(db.pinned.map(p => p.toLowerCase()));
  const top = Object.entries(db.frequent).filter(([k, n]) => n >= 2 && !pinnedSet.has(k))
    .sort((a, b) => b[1] - a[1]).slice(0, 16).map(([text, count]) => ({ text, count, pinned: false }));
  return [...db.pinned.map(text => ({ text, count: db.frequent[text.toLowerCase()] || 0, pinned: true })), ...top];
}
function addTask(list, body) {
  const text = cleanText(body.text);
  if (!text) throw Object.assign(new Error('text required'), { code: 400 });
  const t = { id: id(), text, due: normDue(body.due), done: false, createdAt: now(), notes: cleanText(body.notes) || undefined };
  list.tasks.push(t);
  remember(text);
  fireWebhooks('task.created', { task: taskView(list, t) });
  return t;
}
function patchTask(list, t, b) {
  if ('text' in b) { const x = cleanText(b.text); if (x) t.text = x; }
  if ('notes' in b) t.notes = cleanText(b.notes) || undefined;
  if ('due' in b) { t.due = normDue(b.due); t.notified = false; delete t.snoozeUntil; }
  if ('done' in b) {
    t.done = !!b.done; t.doneAt = t.done ? now() : undefined;
    if (t.done) fireWebhooks('task.completed', { task: taskView(list, t) });
  }
}
function publicList(l) { return { id: l.id, name: l.name, color: l.color, tasks: l.tasks, share: l.share ? { mode: l.share.mode } : null }; }

// ---------- printable page ----------
function printPage(l, includeDone) {
  const fmt = ms => new Date(ms).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  const tasks = l.tasks.filter(t => includeDone || !t.done)
    .sort((a, b) => (a.done - b.done) || ((a.due || Infinity) - (b.due || Infinity)));
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(l.name)}</title>
<style>
 body{font:16px/1.4 system-ui,-apple-system,Segoe UI,sans-serif;color:#000;margin:40px;max-width:720px}
 h1{font-size:28px;margin:0 0 4px} .meta{color:#555;margin-bottom:24px;font-size:13px}
 ul{list-style:none;padding:0;margin:0} li{display:flex;gap:14px;align-items:flex-start;padding:10px 0;border-bottom:1px solid #ddd}
 .box{width:18px;height:18px;border:2px solid #000;border-radius:3px;flex:none;margin-top:2px;text-align:center;line-height:16px;font-size:14px}
 .done .txt{text-decoration:line-through;color:#777} .due{margin-left:auto;color:#333;white-space:nowrap;font-size:14px}
 .notes{color:#555;font-size:13px} .bar{margin-bottom:20px} @media print{.bar{display:none} body{margin:0}}
 button{font:inherit;padding:8px 16px;margin-right:8px;cursor:pointer}
</style></head><body>
<div class="bar"><button onclick="print()">Print</button><button onclick="location.search='${includeDone ? '' : '?all=1'}'">${includeDone ? 'Hide' : 'Include'} completed</button><button onclick="history.length>1?history.back():close()">Close</button></div>
<h1>${esc(l.name)}</h1><div class="meta">${tasks.length} item${tasks.length === 1 ? '' : 's'} · printed ${esc(new Date().toLocaleDateString())}</div>
<ul>${tasks.map(t => `<li class="${t.done ? 'done' : ''}"><span class="box">${t.done ? '✓' : ''}</span><div><div class="txt">${esc(t.text)}</div>${t.notes ? `<div class="notes">${esc(t.notes)}</div>` : ''}</div>${t.due ? `<span class="due">${esc(fmt(t.due))}</span>` : ''}</li>`).join('')}</ul>
<script>if(new URLSearchParams(location.search).has('auto'))addEventListener('load',()=>setTimeout(print,300))</script>
</body></html>`;
}

// ---------- router ----------
async function api(req, res, parts, url) {
  const m = req.method;
  const [, , a, b, c, d, e] = parts; // '', 'api', ...

  if (a === 'state' && m === 'GET')
    return send(res, 200, { lists: db.lists, frequent: frequentList(), webhooks: db.webhooks, remindLeadMin: REMIND_LEAD_MIN, hosts: lanHosts() });

  if (a === 'test-popup' && m === 'POST') {
    const payload = { test: true, overdue: false, task: { id: 'test', listId: null, listName: 'Tasks', color: '#ffb84d', text: 'This is what a task pop-up looks like', due: now() + 10 * 60000 } };
    broadcast('due', payload); broadcast('popup', toPopup(payload)); fireWebhooks('task.due', payload); return send(res, 200, { ok: true });
  }

  if (a === 'events' && m === 'GET') {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' });
    res.write('retry: 3000\n\n');
    clients.add(res);
    const ping = setInterval(() => res.write(': ping\n\n'), 25000);
    req.on('close', () => { clearInterval(ping); clients.delete(res); });
    return;
  }

  if (a === 'due' && m === 'GET') return send(res, 200, dueTasks(Number(url.searchParams.get('within')) || 0));

  // frequent items
  if (a === 'frequent') {
    const body = m === 'GET' ? {} : await readBody(req);
    const text = cleanText(body.text);
    if (m === 'GET') return send(res, 200, frequentList());
    if (!text) return send(res, 400, { error: 'text required' });
    if (m === 'POST') { // pin / unpin
      db.pinned = db.pinned.filter(p => p.toLowerCase() !== text.toLowerCase());
      if (body.pinned !== false) db.pinned.push(text);
    } else if (m === 'DELETE') {
      delete db.frequent[text.toLowerCase()];
      db.pinned = db.pinned.filter(p => p.toLowerCase() !== text.toLowerCase());
    }
    changed(null); return send(res, 200, frequentList());
  }

  // webhooks
  if (a === 'webhooks') {
    if (m === 'GET') return send(res, 200, db.webhooks);
    const { url: hook } = await readBody(req);
    try { new URL(hook); } catch { return send(res, 400, { error: 'valid url required' }); }
    if (m === 'POST' && !db.webhooks.includes(hook)) db.webhooks.push(hook);
    if (m === 'DELETE') db.webhooks = db.webhooks.filter(h => h !== hook);
    save(); return send(res, 200, db.webhooks);
  }

  // shared lists:  /api/shared/:token[/tasks[/:tid]]
  if (a === 'shared') {
    const l = db.lists.find(x => x.share && x.share.token === b);
    if (!l) return send(res, 404, { error: 'share not found' });
    if (m === 'GET' && !c) return send(res, 200, publicList(l));
    if (l.share.mode !== 'edit') return send(res, 403, { error: 'view only' });
    if (c === 'tasks' && !d && m === 'POST') { const t = addTask(l, await readBody(req)); changed(l.id); return send(res, 201, t); }
    const t = l.tasks.find(x => x.id === d);
    if (c === 'tasks' && t && m === 'PATCH') { patchTask(l, t, await readBody(req)); changed(l.id); return send(res, 200, t); }
    return send(res, 404, { error: 'not found' });
  }

  // lists
  if (a === 'lists') {
    if (!b && m === 'POST') {
      const body = await readBody(req);
      const name = cleanText(body.name);
      if (!name) return send(res, 400, { error: 'name required' });
      const l = { id: id(), name, color: COLORS[db.lists.length % COLORS.length], archived: false, createdAt: now(), tasks: [] };
      db.lists.push(l); changed(l.id); return send(res, 201, l);
    }
    const l = findList(b);
    if (!l) return send(res, 404, { error: 'list not found' });

    if (!c) {
      if (m === 'GET') return send(res, 200, l);
      if (m === 'PATCH') {
        const body = await readBody(req);
        if (body.name) l.name = cleanText(body.name) || l.name;
        if (body.color) l.color = String(body.color).slice(0, 20);
        if ('archived' in body) { l.archived = !!body.archived; l.archivedAt = l.archived ? now() : undefined; }
        changed(l.id); return send(res, 200, l);
      }
      if (m === 'DELETE') { db.lists = db.lists.filter(x => x !== l); changed(l.id); return send(res, 200, { ok: true }); }
    }
    if (c === 'duplicate' && m === 'POST') {
      const copy = { ...l, id: id(), name: l.name + ' (copy)', archived: false, archivedAt: undefined, share: undefined, createdAt: now(),
        tasks: l.tasks.map(t => ({ id: id(), text: t.text, notes: t.notes, due: null, done: false, createdAt: now() })) };
      db.lists.push(copy); changed(copy.id); return send(res, 201, copy);
    }
    if (c === 'clear-done' && m === 'POST') { l.tasks = l.tasks.filter(t => !t.done); changed(l.id); return send(res, 200, l); }
    if (c === 'share') {
      if (m === 'POST') {
        const { mode } = await readBody(req);
        l.share = { token: (l.share && l.share.token) || crypto.randomBytes(9).toString('base64url'), mode: mode === 'edit' ? 'edit' : 'view' };
      } else if (m === 'DELETE') delete l.share;
      changed(l.id); return send(res, 200, { share: l.share || null });
    }
    if (c === 'tasks') {
      if (!d && m === 'POST') {
        const body = await readBody(req);
        const items = Array.isArray(body.items) ? body.items : [body];
        const made = items.map(it => addTask(l, it));
        changed(l.id); return send(res, 201, Array.isArray(body.items) ? made : made[0]);
      }
      const t = l.tasks.find(x => x.id === d);
      if (!t) return send(res, 404, { error: 'task not found' });
      if (!e && m === 'PATCH') { patchTask(l, t, await readBody(req)); changed(l.id); return send(res, 200, t); }
      if (!e && m === 'DELETE') { l.tasks = l.tasks.filter(x => x !== t); changed(l.id); return send(res, 200, { ok: true }); }
      if (e === 'snooze' && m === 'POST') {
        const { minutes } = await readBody(req);
        t.snoozeUntil = now() + (Number(minutes) || 10) * 60000; // reminder pops up again at snooze end
        t.notified = false; changed(l.id); return send(res, 200, t);
      }
      if (e === 'move' && m === 'POST') {
        const { toList, index } = await readBody(req);
        const dest = findList(toList) || l;
        l.tasks = l.tasks.filter(x => x !== t);
        const i = Number.isInteger(index) ? Math.max(0, Math.min(index, dest.tasks.length)) : dest.tasks.length;
        dest.tasks.splice(i, 0, t);
        changed(l.id); return send(res, 200, t);
      }
    }
  }
  return send(res, 404, { error: 'not found' });
}

function serveStatic(req, res, p) {
  const file = path.normalize(path.join(PUBLIC, p === '/' ? 'index.html' : p));
  if (!file.startsWith(PUBLIC)) return send(res, 403, 'forbidden', 'text/plain');
  fs.readFile(file, (err, buf) => {
    if (err) return send(res, 404, 'not found', 'text/plain');
    res.writeHead(200, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream', 'cache-control': 'no-cache',
      ...(p === '/popup.js' ? { 'access-control-allow-origin': '*' } : {}) });
    res.end(buf);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const p = decodeURIComponent(url.pathname);
  const parts = p.split('/');
  // CORS so other apps on your network can read tasks / show pop-ups
  if (p.startsWith('/api/')) {
    res.setHeader('access-control-allow-origin', '*');
    res.setHeader('access-control-allow-methods', 'GET,POST,PATCH,DELETE,OPTIONS');
    res.setHeader('access-control-allow-headers', 'content-type');
    if (req.method === 'OPTIONS') return send(res, 204, '');
  }
  try {
    if (p === '/antv.json') { res.setHeader('access-control-allow-origin', '*'); return send(res, 200, MANIFEST); }
    if (parts[1] === 'api') return await api(req, res, parts, url);
    if (parts[1] === 'print' && parts[2]) {
      const l = findList(parts[2]) || db.lists.find(x => x.share && x.share.token === parts[2]);
      return l ? send(res, 200, printPage(l, url.searchParams.has('all')), MIME['.html']) : send(res, 404, 'list not found', 'text/plain');
    }
    if (parts[1] === 'share' && parts[2]) return serveStatic(req, res, '/shared.html');
    return serveStatic(req, res, p);
  } catch (err) {
    send(res, err.code === 400 ? 400 : 500, { error: err.message });
  }
});

function lanHosts() {
  return Object.values(os.networkInterfaces()).flat().filter(i => i && i.family === 'IPv4' && !i.internal).map(i => `${i.address}:${PORT}`);
}

server.listen(PORT, () => {
  const ips = lanHosts();
  console.log(`\n  Tasks is running\n  On this computer:  http://localhost:${PORT}`);
  ips.forEach(ip => console.log(`  On your network:   http://${ip}`));
  console.log(`  Data file:         ${DATA_FILE}\n`);
});
