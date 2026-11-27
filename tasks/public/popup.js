/*  Tasks pop-up widget — drop into ANY web app:
 *    <script src="http://YOUR-TASKS-HOST:3000/popup.js"></script>
 *  Optional attributes on the script tag:
 *    data-position="top-right|top-left|bottom-right|bottom-left"   (default bottom-right)
 *    data-lists="Groceries,Chores"   only pop up tasks from these lists
 *    data-sound="off"                no chime
 *  Also exposes window.TasksPopup.on(fn) to receive due tasks in your own code.
 */
(function () {
  if (window.TasksPopup) return;
  const me = document.currentScript || [...document.scripts].find(s => /popup\.js/.test(s.src));
  const BASE = new URL(me.src).origin;
  const pos = (me.dataset.position || 'bottom-right').split('-');
  const only = (me.dataset.lists || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
  const sound = me.dataset.sound !== 'off';
  const listeners = [];

  const host = document.createElement('div');
  host.style.cssText = `position:fixed;${pos[0]}:24px;${pos[1]}:24px;z-index:2147483647;`;
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `<style>
    :host{all:initial}
    .stack{display:flex;flex-direction:column;gap:12px;font:16px/1.35 "Segoe UI",system-ui,sans-serif;width:min(380px,calc(100vw - 48px))}
    .card{background:#1c1f27;color:#f1f2f5;border-radius:16px;padding:16px 18px;box-shadow:0 18px 40px rgba(0,0,0,.45);border-left:6px solid var(--c);animation:in .25s ease-out}
    .tag{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--c)}
    .txt{font-size:20px;font-weight:600;margin:4px 0 12px;overflow-wrap:anywhere}
    .row{display:flex;gap:8px;flex-wrap:wrap}
    button{font:inherit;font-size:14px;border:0;border-radius:10px;padding:8px 14px;background:#2d3240;color:#f1f2f5;cursor:pointer}
    button:hover,button:focus{background:#3a4152;outline:none;box-shadow:0 0 0 3px var(--c)}
    .done{background:var(--c);color:#15171c;font-weight:700}
    @keyframes in{from{transform:translateY(12px);opacity:0}}
  </style><div class="stack"></div>`;
  const stack = root.querySelector('.stack');
  (document.body || document.documentElement).append(host);

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = ms => new Date(ms).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
  const post = (path, body) => fetch(BASE + path, { method: path.includes('snooze') ? 'POST' : 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });

  function chime() {
    if (!sound) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)(), o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = 988; g.gain.setValueAtTime(.18, ctx.currentTime); g.gain.exponentialRampToValueAtTime(.0001, ctx.currentTime + .6);
      o.connect(g).connect(ctx.destination); o.start(); o.stop(ctx.currentTime + .6);
    } catch (e) {}
  }

  function show({ task: t, overdue, test }) {
    if (only.length && !only.includes(String(t.listName).toLowerCase())) return;
    listeners.forEach(fn => { try { fn(t, { overdue, test }); } catch (e) {} });
    const card = document.createElement('div');
    card.className = 'card'; card.style.setProperty('--c', t.color || '#ffb84d');
    card.innerHTML = `<div class="tag">${esc(t.listName)} · ${overdue ? 'Overdue' : 'Due ' + esc(fmt(t.due))}</div>
      <div class="txt">${esc(t.text)}</div>
      <div class="row">${test ? '' : '<button class="done">✓ Done</button><button class="snz">⏰ 10 min</button><button class="open">Open</button>'}<button class="x">Dismiss</button></div>`;
    const close = () => card.remove();
    const q = s => card.querySelector(s);
    if (!test) {
      q('.done').onclick = () => { post(`/api/lists/${t.listId}/tasks/${t.id}`, { done: true }); close(); };
      q('.snz').onclick = () => { post(`/api/lists/${t.listId}/tasks/${t.id}/snooze`, { minutes: 10 }); close(); };
      q('.open').onclick = () => { window.open(BASE + '/', 'tasks'); close(); };
    }
    q('.x').onclick = close;
    stack.append(card); chime();
    setTimeout(() => q('button') && q('button').focus({ preventScroll: true }), 50);
    setTimeout(close, 60000);
  }

  const es = new EventSource(BASE + '/api/events');
  es.addEventListener('due', e => show(JSON.parse(e.data)));

  window.TasksPopup = {
    on(fn) { listeners.push(fn); },
    due(withinMin = 60) { return fetch(`${BASE}/api/due?within=${withinMin}`).then(r => r.json()); },
    add(listId, text, due) { return fetch(`${BASE}/api/lists/${listId}/tasks`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, due }) }).then(r => r.json()); },
    base: BASE,
  };
})();
