// Tasks — main UI
(() => {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const store = {
    get(k, d) { try { const v = localStorage.getItem('tasks.' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('tasks.' + k, JSON.stringify(v)); } catch {} },
  };

  let S = { lists: [], frequent: [], webhooks: [], hosts: [] };
  let currentId = store.get('current', null);
  let showArchive = false;
  let showDone = store.get('showDone', false);
  let manualDue; // undefined = auto from text, null = explicitly none, number = chosen

  // ---------- API ----------
  async function api(method, url, body) {
    const r = await fetch(url, { method, headers: body ? { 'content-type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
  }
  async function load() {
    S = await api('GET', '/api/state');
    if (!S.lists.length) { await api('POST', '/api/lists', { name: 'To Do' }); S = await api('GET', '/api/state'); }
    const active = S.lists.filter(l => !l.archived);
    if (!S.lists.find(l => l.id === currentId) || (!showArchive && current()?.archived)) currentId = (active[0] || S.lists[0]).id;
    render();
  }
  const current = () => S.lists.find(l => l.id === currentId);
  const activeLists = () => S.lists.filter(l => !l.archived);

  // ---------- render ----------
  function render() {
    const focusKey = document.activeElement && document.activeElement.dataset.key;
    renderLists(); renderMain(); renderFreq();
    if (focusKey) { const el = document.querySelector(`[data-key="${CSS.escape(focusKey)}"]`); if (el && !$('#modalRoot .modal')) el.focus({ preventScroll: true }); }
  }

  function renderLists() {
    const nav = $('#lists');
    nav.innerHTML = activeLists().map(l => {
      const open = l.tasks.filter(t => !t.done);
      const overdue = open.some(t => t.due && t.due < Date.now());
      return `<button class="list-btn ${l.id === currentId && !showArchive ? 'active' : ''}" data-key="list-${l.id}" data-id="${l.id}" style="--c:${l.color}">
        <span class="dot"></span><span class="name">${esc(l.name)}</span>
        ${l.share ? '<span class="shared" title="Shared">↗</span>' : ''}
        <span class="count ${overdue ? 'over' : ''}">${open.length || ''}</span></button>`;
    }).join('');
    nav.querySelectorAll('.list-btn').forEach(b => b.onclick = () => selectList(b.dataset.id));
    const n = S.lists.length - activeLists().length;
    $('#archiveLabel').textContent = showArchive ? 'Back to lists' : `Archived${n ? ' (' + n + ')' : ''}`;
    $('#archiveToggle').classList.toggle('active', showArchive);
  }

  function selectList(id) {
    currentId = id; showArchive = false; store.set('current', id); manualDue = undefined; render();
  }
  function cycleList(step) {
    const a = activeLists(); if (!a.length) return;
    const i = a.findIndex(l => l.id === currentId);
    selectList(a[(i + step + a.length) % a.length].id);
    const el = document.querySelector(`[data-key="list-${currentId}"]`); if (el) Nav.focus(el);
  }

  function sortTasks(tasks) {
    const open = tasks.filter(t => !t.done).map((t, i) => [t, i])
      .sort(([a, ia], [b, ib]) => (a.due ? 0 : 1) - (b.due ? 0 : 1) || (a.due || 0) - (b.due || 0) || ia - ib).map(x => x[0]);
    const done = tasks.filter(t => t.done).sort((a, b) => (b.doneAt || 0) - (a.doneAt || 0));
    return { open, done };
  }

  function renderMain() {
    $('#archiveView').hidden = !showArchive;
    $('#taskWrap').hidden = showArchive;
    $('#addBar').hidden = showArchive; $('#freqRow').hidden = showArchive;
    document.querySelector('.toolbar').hidden = showArchive;
    if (showArchive) {
      $('#listTitle').textContent = 'Archive'; $('#listMeta').textContent = 'Restore, print or delete old lists';
      document.documentElement.style.setProperty('--accent', '#9aa3b5');
      return renderArchive();
    }
    const l = current(); if (!l) return;
    document.documentElement.style.setProperty('--accent', l.color);
    $('#listTitle').textContent = l.name;
    const { open, done } = sortTasks(l.tasks);
    const overdue = open.filter(t => t.due && t.due < Date.now()).length;
    $('#listMeta').innerHTML = `${open.length} to do${done.length ? ` · ${done.length} done` : ''}${overdue ? ` · <b class="over">${overdue} overdue</b>` : ''}${l.share ? ` · shared (${l.share.mode === 'edit' ? 'can edit' : 'view only'})` : ''}`;

    const row = t => {
      const st = t.done ? '' : TaskDates.status(t.due);
      return `<li class="task ${t.done ? 'done' : ''} ${st}">
        <button class="check" data-key="chk-${t.id}" data-id="${t.id}" aria-label="${t.done ? 'Mark not done' : 'Mark done'}"><svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></button>
        <button class="task-main" data-key="task-${t.id}" data-id="${t.id}">
          <span class="txt">${esc(t.text)}</span>
          ${t.notes ? `<span class="notes">${esc(t.notes)}</span>` : ''}
          ${t.due ? `<span class="due">${st === 'overdue' ? 'Overdue · ' : ''}${esc(TaskDates.fmt(t.due))}</span>` : ''}
        </button></li>`;
    };
    let html = open.map(row).join('');
    if (done.length) {
      html += `<li class="done-head"><button class="link-btn" id="toggleDone" data-key="toggleDone">${showDone ? '▾' : '▸'} Completed (${done.length})</button>
        ${showDone ? '<button class="link-btn" id="clearDone" data-key="clearDone">Clear completed</button>' : ''}</li>`;
      if (showDone) html += done.map(row).join('');
    }
    $('#tasks').innerHTML = html;
    $('#empty').hidden = open.length > 0;
    $('#empty').innerHTML = done.length ? '🎉 All done! Nothing left on this list.' : 'This list is empty. Add a task above, say one with 🎤 Voice, or use ⚡ Quick add.';

    $('#tasks').querySelectorAll('.check').forEach(b => b.onclick = () => toggleDone(b.dataset.id));
    $('#tasks').querySelectorAll('.task-main').forEach(b => b.onclick = () => taskModal(b.dataset.id));
    const td = $('#toggleDone'); if (td) td.onclick = () => { showDone = !showDone; store.set('showDone', showDone); renderMain(); $('#toggleDone').focus(); };
    const cd = $('#clearDone'); if (cd) cd.onclick = async () => { await api('POST', `/api/lists/${l.id}/clear-done`); toast('Cleared completed tasks'); load(); };
    updateDueChip();
  }

  function renderArchive() {
    const arch = S.lists.filter(l => l.archived).sort((a, b) => (b.archivedAt || 0) - (a.archivedAt || 0));
    $('#archived').innerHTML = arch.length ? arch.map(l => `<li class="arch-row" style="--c:${l.color}">
        <div class="arch-info"><span class="dot"></span><b>${esc(l.name)}</b><span class="meta">${l.tasks.length} items${l.archivedAt ? ' · archived ' + new Date(l.archivedAt).toLocaleDateString() : ''}</span></div>
        <button data-act="restore" data-id="${l.id}" data-key="ar-${l.id}">Restore</button>
        <button data-act="print" data-id="${l.id}" data-key="ap-${l.id}">Print</button>
        <button data-act="delete" data-id="${l.id}" class="danger" data-key="ad-${l.id}">Delete</button></li>`).join('')
      : '<li class="empty">No archived lists. Use “More → Archive list” to tuck a list away.</li>';
    $('#archived').querySelectorAll('button').forEach(b => b.onclick = async () => {
      const l = S.lists.find(x => x.id === b.dataset.id);
      if (b.dataset.act === 'restore') { await api('PATCH', `/api/lists/${l.id}`, { archived: false }); toast(`Restored “${l.name}”`); currentId = l.id; showArchive = false; await load(); Nav.focus(document.querySelector(`[data-key="list-${l.id}"]`)); }
      if (b.dataset.act === 'print') printList(l.id);
      if (b.dataset.act === 'delete' && await confirmModal(`Delete “${l.name}” forever?`, 'Delete')) { await api('DELETE', `/api/lists/${l.id}`); load(); }
    });
  }

  function renderFreq() {
    const row = $('#freqRow');
    const items = S.frequent.slice(0, 10);
    row.innerHTML = items.length ? '<span class="freq-label">Quick:</span>' + items.map((f, i) =>
      `<button class="chip ${f.pinned ? 'pinned' : ''}" data-key="fq-${esc(f.text)}" data-i="${i}">${f.pinned ? '★ ' : '+ '}${esc(f.text)}</button>`).join('') : '';
    row.querySelectorAll('.chip').forEach(b => b.onclick = () => quickAdd(items[b.dataset.i].text, b));
  }

  // ---------- actions ----------
  async function addTask(text, due) {
    const l = current(); if (!l || !text.trim()) return;
    await api('POST', `/api/lists/${l.id}/tasks`, { text, due });
    await load();
  }
  async function quickAdd(text, el) {
    const l = current();
    if (l.tasks.some(t => !t.done && t.text.toLowerCase() === text.toLowerCase())) return toast(`“${text}” is already on ${l.name}`);
    await addTask(text, null);
    toast(`Added “${text}”`);
    if (el && el.dataset.key) { const again = document.querySelector(`[data-key="${CSS.escape(el.dataset.key)}"]`); if (again) again.focus(); }
  }
  async function toggleDone(id) {
    const l = current(); const t = l.tasks.find(x => x.id === id);
    t.done = !t.done; renderMain(); // instant feedback
    const el = document.querySelector(`[data-key="chk-${id}"]`) || document.querySelector('#tasks .check');
    if (el) el.focus({ preventScroll: true });
    await api('PATCH', `/api/lists/${l.id}/tasks/${id}`, { done: t.done });
    if (t.done) toast(`Done: ${t.text}`, [{ label: 'Undo', fn: async () => { await api('PATCH', `/api/lists/${l.id}/tasks/${id}`, { done: false }); load(); } }]);
    load();
  }
  function printList(id) {
    const w = window.open(`/print/${id}?auto`, '_blank');
    if (!w) location.href = `/print/${id}?auto`;
  }

  // ---------- add bar ----------
  const input = $('#addInput');
  function updateDueChip() {
    const chip = $('#dueChip'), txt = $('#dueChipText');
    if (manualDue !== undefined) { txt.textContent = manualDue ? TaskDates.fmt(manualDue) : 'No date'; chip.classList.toggle('set', !!manualDue); chip.classList.remove('auto'); return; }
    const p = TaskDates.parse(input.value);
    txt.textContent = p.due ? TaskDates.fmt(p.due) : 'No date';
    chip.classList.toggle('set', !!p.due); chip.classList.toggle('auto', !!p.due);
  }
  input.addEventListener('input', updateDueChip);
  $('#addBar').addEventListener('submit', async e => {
    e.preventDefault();
    const raw = input.value.trim(); if (!raw) return input.focus();
    let text = raw, due = null;
    if (manualDue !== undefined) due = manualDue; else { const p = TaskDates.parse(raw); text = p.text; due = p.due; }
    input.value = ''; manualDue = undefined;
    await addTask(text, due);
    toast(`Added “${text}”${due ? ' · ' + TaskDates.fmt(due) : ''}`);
    input.focus();
  });
  $('#dueChip').onclick = async () => {
    const auto = manualDue === undefined ? TaskDates.parse(input.value).due : manualDue;
    const r = await duePicker(auto);
    if (r !== undefined) { manualDue = r; if (manualDue !== null || TaskDates.parse(input.value).due) { /* explicit choice wins */ } }
    updateDueChip(); $('#dueChip').focus();
  };

  // ---------- modals ----------
  const modalStack = [];
  function modal({ title, body, buttons = [], wide, onClose }) {
    const el = document.createElement('div');
    el.className = 'modal-wrap';
    el.innerHTML = `<div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <h2>${esc(title)}</h2><div class="modal-body"></div><div class="modal-actions"></div></div>`;
    const m = el.querySelector('.modal');
    const bodyEl = el.querySelector('.modal-body');
    if (typeof body === 'string') bodyEl.innerHTML = body; else if (body) bodyEl.append(body);
    const prevFocus = document.activeElement;
    let closed = false;
    const api = {
      el: m, body: bodyEl,
      close(fromPop) {
        if (closed) return; closed = true;
        el.classList.add('out'); setTimeout(() => el.remove(), 160);
        modalStack.splice(modalStack.indexOf(api), 1);
        if (!fromPop && history.state && history.state.modal) { ignorePop++; history.back(); }
        onClose && onClose();
        if (prevFocus && document.contains(prevFocus)) setTimeout(() => prevFocus.focus({ preventScroll: true }), 0);
        else setTimeout(() => Nav.focusFirst(), 0);
      },
    };
    const actions = el.querySelector('.modal-actions');
    buttons.forEach(b => {
      const btn = document.createElement('button');
      btn.textContent = b.label; if (b.primary) btn.className = 'primary'; if (b.danger) btn.className = 'danger';
      btn.onclick = () => b.onClick ? b.onClick(api) : api.close();
      actions.append(btn);
    });
    if (!buttons.length) actions.remove();
    el.addEventListener('mousedown', e => { if (e.target === el) api.close(); });
    $('#modalRoot').append(el);
    modalStack.push(api);
    history.pushState({ modal: true }, '');
    setTimeout(() => Nav.focusFirst(m), 30);
    return api;
  }
  let ignorePop = 0;
  addEventListener('popstate', () => {
    if (ignorePop) { ignorePop--; return; }
    const top = modalStack[modalStack.length - 1]; if (top) top.close(true);
  });
  Nav.onBack(() => {
    const top = modalStack[modalStack.length - 1];
    if (top) { top.close(); return true; }
    if (showArchive) { showArchive = false; render(); return true; }
    if (document.activeElement === input && input.value) { input.value = ''; updateDueChip(); return true; }
    return false;
  });

  function promptModal(title, value = '', placeholder = '', okLabel = 'Save') {
    return new Promise(res => {
      const form = document.createElement('form');
      form.innerHTML = `<input class="big-input" data-autofocus maxlength="300" placeholder="${esc(placeholder)}" value="${esc(value)}">`;
      let done = false;
      const m = modal({ title, body: form, onClose: () => !done && res(null), buttons: [
        { label: 'Cancel' }, { label: okLabel, primary: true, onClick: () => form.requestSubmit() }] });
      form.onsubmit = e => { e.preventDefault(); done = true; res(form.querySelector('input').value.trim() || null); m.close(); };
    });
  }
  function confirmModal(text, okLabel = 'OK') {
    return new Promise(res => {
      let done = false;
      modal({ title: text, onClose: () => !done && res(false), buttons: [
        { label: 'Cancel' }, { label: okLabel, danger: true, onClick: m => { done = true; res(true); m.close(); } }] });
      setTimeout(() => { const c = document.querySelector('#modalRoot .modal-actions button'); c && c.focus(); }, 40);
    });
  }

  function at(daysAhead, h, m = 0) { const d = new Date(); d.setDate(d.getDate() + daysAhead); d.setHours(h, m, 0, 0); return d.getTime(); }
  function duePicker(currentDue) {
    return new Promise(res => {
      const now = new Date();
      const toSat = (6 - now.getDay() + 7) % 7 || 7, toMon = (8 - now.getDay()) % 7 || 7;
      const opts = [
        ['In 1 hour', Date.now() + 3600000],
        ['Today 5 PM', at(0, 17)], ['Tonight 8 PM', at(0, 20)],
        ['Tomorrow 9 AM', at(1, 9)], ['Tomorrow 5 PM', at(1, 17)],
        ['This weekend', at(toSat, 10)], ['Next week', at(toMon, 9)], ['In 2 weeks', at(14, 9)],
      ].filter(([, t]) => t > Date.now());
      const pad = n => String(n).padStart(2, '0');
      const loc = ms => { const d = new Date(ms); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; };
      const body = document.createElement('div');
      body.innerHTML = `${currentDue ? `<p class="cur">Currently: <b>${esc(TaskDates.fmt(currentDue))}</b></p>` : ''}
        <div class="grid">${opts.map(([l, t], i) => `<button data-t="${t}" ${i === 0 ? 'data-autofocus' : ''}><b>${l}</b><small>${esc(TaskDates.fmt(t))}</small></button>`).join('')}</div>
        <div class="custom"><label>Pick a date &amp; time<input type="datetime-local" id="dtPick" value="${loc(currentDue || at(1, 9))}"></label><button id="dtSet" class="primary">Set</button></div>
        <div class="custom"><input id="dtWords" placeholder="or type: “friday at 3pm”, “in 3 days”, “dec 12”"><button id="dtWordsSet">Use</button></div>`;
      let done = false;
      const finish = v => { done = true; res(v); m.close(); };
      const m = modal({ title: 'When is it due?', body, wide: true, onClose: () => !done && res(undefined), buttons: [
        { label: 'Cancel' }, { label: 'No date', onClick: () => finish(null) }] });
      body.querySelectorAll('.grid button').forEach(b => b.onclick = () => finish(+b.dataset.t));
      body.querySelector('#dtSet').onclick = () => { const v = Date.parse(body.querySelector('#dtPick').value); if (v) finish(v); };
      const words = () => { const p = TaskDates.parse('x ' + body.querySelector('#dtWords').value); if (p.due) finish(p.due); else toast('Could not understand that date'); };
      body.querySelector('#dtWordsSet').onclick = words;
      body.querySelector('#dtWords').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); words(); } };
    });
  }

  function taskModal(id) {
    const l = current(); const t = l.tasks.find(x => x.id === id); if (!t) return;
    const others = activeLists().filter(x => x.id !== l.id);
    const body = document.createElement('div');
    body.innerHTML = `<p class="task-big">${esc(t.text)}</p>
      ${t.due ? `<p class="cur">Due <b>${esc(TaskDates.fmt(t.due))}</b></p>` : ''}${t.notes ? `<p class="cur">${esc(t.notes)}</p>` : ''}
      <div class="grid actions-grid">
        <button data-a="done" data-autofocus>${t.done ? '↺ Mark not done' : '✓ Mark done'}</button>
        <button data-a="due">📅 ${t.due ? 'Change date' : 'Set due date'}</button>
        <button data-a="edit">✎ Edit text</button>
        <button data-a="notes">🗒 ${t.notes ? 'Edit note' : 'Add note'}</button>
        ${others.length ? '<button data-a="move">⇄ Move to list</button>' : ''}
        <button data-a="pin">★ Save as quick item</button>
        <button data-a="delete" class="danger">🗑 Delete</button>
      </div>`;
    const m = modal({ title: l.name, body, wide: true, buttons: [{ label: 'Close' }] });
    const patch = async b => { await api('PATCH', `/api/lists/${l.id}/tasks/${t.id}`, b); await load(); };
    body.querySelectorAll('[data-a]').forEach(b => b.onclick = async () => {
      const a = b.dataset.a;
      if (a === 'done') { m.close(); toggleDone(t.id); }
      if (a === 'due') { const r = await duePicker(t.due); if (r !== undefined) { await patch({ due: r }); m.close(); toast(r ? `Due ${TaskDates.fmt(r)}` : 'Date cleared'); } }
      if (a === 'edit') { const v = await promptModal('Edit task', t.text); if (v) { await patch({ text: v }); m.close(); } }
      if (a === 'notes') { const v = await promptModal('Note', t.notes || '', 'Details, quantity, link…'); if (v !== null || t.notes) { await patch({ notes: v || '' }); m.close(); } }
      if (a === 'pin') { await api('POST', '/api/frequent', { text: t.text, pinned: true }); toast(`“${t.text}” saved to Quick add`); load(); }
      if (a === 'delete') { await api('DELETE', `/api/lists/${l.id}/tasks/${t.id}`); m.close(); toast('Task deleted'); load(); }
      if (a === 'move') {
        const pick = modal({ title: 'Move to…', body: `<div class="grid">${others.map(o => `<button data-to="${o.id}" style="--c:${o.color}"><span class="dot"></span> ${esc(o.name)}</button>`).join('')}</div>`, buttons: [{ label: 'Cancel' }] });
        pick.body.querySelectorAll('[data-to]').forEach(x => x.onclick = async () => {
          await api('POST', `/api/lists/${l.id}/tasks/${t.id}/move`, { toList: x.dataset.to }); pick.close(); m.close();
          toast(`Moved to ${others.find(o => o.id === x.dataset.to).name}`); load();
        });
      }
    });
  }

  function listMenu() {
    const l = current(); if (!l || showArchive) return;
    const body = `<div class="grid actions-grid">
      <button data-a="rename" data-autofocus>✎ Rename list</button>
      <button data-a="color">🎨 Change color</button>
      <button data-a="printall">🖨 Print with completed</button>
      <button data-a="dup">⧉ Duplicate list</button>
      <button data-a="clear">✓ Clear completed</button>
      <button data-a="archive">🗄 Archive list</button>
      <button data-a="delete" class="danger">🗑 Delete list</button></div>`;
    const m = modal({ title: l.name, body, wide: true, buttons: [{ label: 'Close' }] });
    m.body.querySelectorAll('[data-a]').forEach(b => b.onclick = async () => {
      const a = b.dataset.a;
      if (a === 'rename') { const v = await promptModal('Rename list', l.name); if (v) { await api('PATCH', `/api/lists/${l.id}`, { name: v }); m.close(); load(); } }
      if (a === 'color') {
        const cols = ['#ffb84d', '#5ec8ff', '#7ee08a', '#ff7aa8', '#b49bff', '#ffd95e', '#4fe0c8', '#ff8a5c', '#9aa3b5'];
        const c = modal({ title: 'Pick a color', body: `<div class="swatches">${cols.map(x => `<button data-c="${x}" style="--c:${x}" aria-label="${x}"></button>`).join('')}</div>`, buttons: [{ label: 'Cancel' }] });
        c.body.querySelectorAll('[data-c]').forEach(x => x.onclick = async () => { await api('PATCH', `/api/lists/${l.id}`, { color: x.dataset.c }); c.close(); m.close(); load(); });
      }
      if (a === 'printall') { m.close(); window.open(`/print/${l.id}?all&auto`, '_blank'); }
      if (a === 'dup') { const c = await api('POST', `/api/lists/${l.id}/duplicate`); m.close(); currentId = c.id; toast('List duplicated (dates cleared)'); load(); }
      if (a === 'clear') { await api('POST', `/api/lists/${l.id}/clear-done`); m.close(); toast('Cleared completed tasks'); load(); }
      if (a === 'archive') {
        await api('PATCH', `/api/lists/${l.id}`, { archived: true }); m.close();
        toast(`Archived “${l.name}”`, [{ label: 'Undo', fn: async () => { await api('PATCH', `/api/lists/${l.id}`, { archived: false }); currentId = l.id; load(); } }]);
        currentId = null; load();
      }
      if (a === 'delete' && await confirmModal(`Delete “${l.name}” and its ${l.tasks.length} tasks?`, 'Delete')) { await api('DELETE', `/api/lists/${l.id}`); m.close(); currentId = null; load(); }
    });
  }

  // ---------- share ----------
  function shareBase() {
    const h = location.hostname;
    if ((h === 'localhost' || h === '127.0.0.1') && S.hosts && S.hosts.length) return `${location.protocol}//${S.hosts[0]}`;
    return location.origin;
  }
  function listAsText(l) {
    const { open } = sortTasks(l.tasks);
    return `${l.name}\n` + open.map(t => `☐ ${t.text}${t.due ? ' — ' + TaskDates.fmt(t.due) : ''}`).join('\n');
  }
  function shareModal() {
    const l = current(); if (!l) return;
    const draw = () => {
      const link = l.share ? `${shareBase()}/share/${l.share.token}` : '';
      return `<p class="cur">Anyone on your network with the link can ${l.share ? (l.share.mode === 'edit' ? '<b>view, add and check off</b> tasks' : '<b>view</b> this list') : 'open it once you turn sharing on'}.</p>
        <div class="seg">
          <button data-mode="off" class="${!l.share ? 'on' : ''}">Off</button>
          <button data-mode="view" class="${l.share && l.share.mode === 'view' ? 'on' : ''}">View only</button>
          <button data-mode="edit" class="${l.share && l.share.mode === 'edit' ? 'on' : ''}">Can edit</button>
        </div>
        ${link ? `<div class="share-link"><code>${esc(link)}</code></div>` : ''}
        <div class="grid actions-grid">
          ${link ? '<button data-a="copy" data-autofocus>⧉ Copy link</button>' : ''}
          ${link && navigator.share ? '<button data-a="native">↗ Share link…</button>' : ''}
          <button data-a="text">☰ Copy as text</button>
          <button data-a="email">✉ Email list</button>
          <button data-a="sms">💬 Text message</button>
        </div>`;
    };
    const m = modal({ title: `Share “${l.name}”`, body: draw(), wide: true, buttons: [{ label: 'Done' }] });
    const wire = () => {
      m.body.querySelectorAll('[data-mode]').forEach(b => b.onclick = async () => {
        const mode = b.dataset.mode;
        const r = mode === 'off' ? await api('DELETE', `/api/lists/${l.id}/share`) : await api('POST', `/api/lists/${l.id}/share`, { mode });
        l.share = r.share; m.body.innerHTML = draw(); wire();
        const again = m.body.querySelector(`[data-mode="${mode}"]`); again && again.focus();
        load();
      });
      const link = l.share ? `${shareBase()}/share/${l.share.token}` : '';
      m.body.querySelectorAll('[data-a]').forEach(b => b.onclick = async () => {
        const a = b.dataset.a;
        if (a === 'copy') copy(link, 'Link copied');
        if (a === 'native') navigator.share({ title: l.name, text: `Tasks: ${l.name}`, url: link }).catch(() => {});
        if (a === 'text') copy(listAsText(l), 'List copied as text');
        if (a === 'email') location.href = `mailto:?subject=${encodeURIComponent(l.name)}&body=${encodeURIComponent(listAsText(l) + (link ? '\n\nLive list: ' + link : ''))}`;
        if (a === 'sms') location.href = `sms:?&body=${encodeURIComponent(listAsText(l) + (link ? '\n' + link : ''))}`;
      });
    };
    wire();
  }
  async function copy(text, msg) {
    try { await navigator.clipboard.writeText(text); toast(msg); }
    catch {
      const ta = document.createElement('textarea'); ta.value = text; document.body.append(ta); ta.select();
      try { document.execCommand('copy'); toast(msg); } catch { toast('Copy not available here'); } ta.remove();
    }
  }

  // ---------- quick add (frequent items) ----------
  function quickModal() {
    const l = current(); if (!l || showArchive) return;
    const draw = () => S.frequent.length
      ? `<p class="cur">Tap to add to <b>${esc(l.name)}</b>. ★ keeps an item here permanently.</p><div class="quick-grid">${S.frequent.map((f, i) => `
        <div class="quick-item ${f.pinned ? 'pinned' : ''}">
          <button class="qi-add" data-i="${i}" ${i === 0 ? 'data-autofocus' : ''}>${esc(f.text)}${f.count ? `<small>added ${f.count}×</small>` : ''}</button>
          <button class="qi-pin" data-i="${i}" aria-label="${f.pinned ? 'Unpin' : 'Pin'}">${f.pinned ? '★' : '☆'}</button>
          <button class="qi-del" data-i="${i}" aria-label="Remove">✕</button>
        </div>`).join('')}</div>`
      : '<p class="cur">Items you add twice show up here automatically. You can also save your own.</p>';
    const m = modal({ title: '⚡ Quick add', body: draw(), wide: true, buttons: [
      { label: '＋ New quick item', onClick: async () => { const v = await promptModal('New quick item', '', 'e.g. Take out trash'); if (v) { await api('POST', '/api/frequent', { text: v, pinned: true }); await load(); redraw(); } } },
      { label: 'Done', primary: true }] });
    const redraw = (focusSel) => { m.body.innerHTML = draw(); wire(); if (focusSel) { const el = m.body.querySelector(focusSel); el && el.focus(); } };
    const wire = () => {
      m.body.querySelectorAll('.qi-add').forEach(b => b.onclick = async () => {
        const f = S.frequent[b.dataset.i]; await quickAdd(f.text); b.classList.add('flash'); setTimeout(() => b.classList.remove('flash'), 500);
      });
      m.body.querySelectorAll('.qi-pin').forEach(b => b.onclick = async () => {
        const f = S.frequent[b.dataset.i]; await api('POST', '/api/frequent', { text: f.text, pinned: !f.pinned }); await load();
        const i = S.frequent.findIndex(x => x.text.toLowerCase() === f.text.toLowerCase()); redraw(`.qi-pin[data-i="${i}"]`);
      });
      m.body.querySelectorAll('.qi-del').forEach(b => b.onclick = async () => {
        const f = S.frequent[b.dataset.i]; await api('DELETE', '/api/frequent', { text: f.text }); await load(); redraw('.qi-add');
      });
    };
    wire();
  }

  // ---------- voice ----------
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  function voice() {
    if (showArchive) return;
    if (!SR) {
      return modal({ title: 'Voice input not available', body: `<p class="cur">This browser doesn't support speech recognition. Use Chrome or Edge on a computer or Android, or Safari on iPhone/iPad.</p>
        <p class="cur">On a phone or TV keyboard you can also use the keyboard's own 🎤 mic button in the Add box.</p>`, buttons: [{ label: 'OK', primary: true }] });
    }
    if (!window.isSecureContext) {
      return modal({ title: 'Voice needs a secure address', body: `<p class="cur">Browsers only allow the microphone on <b>http://localhost</b> or an <b>https://</b> address.
        Open Tasks on this device at http://localhost:${location.port || 80}, or use your keyboard's own 🎤 mic button.</p>`, buttons: [{ label: 'OK', primary: true }] });
    }
    const l = current();
    const body = document.createElement('div');
    body.innerHTML = `<div class="mic"><div class="pulse"></div>🎤</div>
      <p class="heard" id="heard">Listening… say a task like “pick up dry cleaning friday at 4”</p>
      <p class="cur small">Say <b>“new list …”</b> to make a list · <b>“switch to …”</b> to change lists · add several with <b>“next”</b> between them</p>`;
    const rec = new SR(); rec.lang = navigator.language || 'en-US'; rec.interimResults = true; rec.continuous = false;
    let finalText = '', stopped = false;
    const m = modal({ title: `Voice → ${l.name}`, body, onClose: () => { stopped = true; try { rec.abort(); } catch {} }, buttons: [
      { label: 'Cancel' }, { label: 'Again', onClick: () => { finalText = ''; try { rec.start(); } catch {} body.querySelector('#heard').textContent = 'Listening…'; } }] });
    rec.onresult = e => {
      let interim = ''; finalText = '';
      for (const r of e.results) (r.isFinal ? (finalText += r[0].transcript) : (interim += r[0].transcript));
      body.querySelector('#heard').textContent = finalText || interim;
    };
    rec.onerror = e => { if (!stopped) body.querySelector('#heard').textContent = e.error === 'not-allowed' ? 'Microphone permission was blocked.' : e.error === 'no-speech' ? 'Didn’t hear anything — press Again.' : 'Voice error: ' + e.error; };
    rec.onend = async () => {
      if (stopped || !finalText.trim()) return;
      const said = finalText.trim();
      let mm;
      if ((mm = said.match(/^(?:new|create|make)(?: a)? list(?: called| named)?\s+(.+)/i))) {
        const nl = await api('POST', '/api/lists', { name: cap(mm[1]) }); m.close(); currentId = nl.id; toast(`Created list “${nl.name}”`); return load();
      }
      if ((mm = said.match(/^(?:switch|go|open)(?: to)?(?: list)?\s+(.+)/i))) {
        const want = mm[1].toLowerCase().replace(/ list$/, '');
        const f = activeLists().find(x => x.name.toLowerCase() === want) || activeLists().find(x => x.name.toLowerCase().includes(want));
        m.close(); if (f) { selectList(f.id); toast(`Switched to ${f.name}`); } else toast(`No list called “${mm[1]}”`); return;
      }
      const parts = said.split(/\s+(?:next|next item|new item)\s+/i).map(s => s.trim()).filter(Boolean);
      const items = parts.map(p => { const r = TaskDates.parse(p); return { text: cap(r.text), due: r.due }; });
      await api('POST', `/api/lists/${l.id}/tasks`, { items });
      m.close();
      toast(items.length === 1 ? `Added “${items[0].text}”${items[0].due ? ' · ' + TaskDates.fmt(items[0].due) : ''}` : `Added ${items.length} tasks`);
      load();
    };
    try { rec.start(); } catch {}
  }
  const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

  // ---------- connect apps / integrations ----------
  function settingsModal() {
    const base = shareBase();
    const body = document.createElement('div');
    const draw = () => `
      <p class="cur">Make Tasks pop up inside your other apps when something is due (${S.remindLeadMin} min before).</p>
      <h3>anTV · pop-ups on top of any app on your TV</h3>
      <p class="cur small">In anTV, edit the Tasks card and tick <b>Show this app's pop-ups</b> and <b>Keep its server running in the background</b>. Reminders then appear over Netflix, VLC, anything. Use 🔔 Send test pop-up below to try it.</p>
      <h3>1 · Drop-in pop-up for any web app</h3>
      <p class="cur small">Paste this one line into the other app's HTML page:</p>
      <div class="share-link"><code>&lt;script src="${esc(base)}/popup.js"&gt;&lt;/script&gt;</code></div>
      <div class="grid actions-grid">
        <button data-a="copysnip" data-autofocus>⧉ Copy snippet</button>
        <button data-a="test">🔔 Send test pop-up</button>
        <button data-a="notify">🖥 ${'Notification' in window && Notification.permission === 'granted' ? 'Desktop alerts on' : 'Enable desktop alerts'}</button>
      </div>
      <h3>2 · Webhooks (server-to-server)</h3>
      <p class="cur small">Tasks POSTs JSON to these URLs on <code>task.due</code>, <code>task.created</code>, <code>task.completed</code>.</p>
      <ul class="hooks">${S.webhooks.map(h => `<li><code>${esc(h)}</code><button data-del="${esc(h)}" class="danger">Remove</button></li>`).join('') || '<li class="cur small">None yet.</li>'}</ul>
      <div class="custom"><input id="hookUrl" placeholder="http://192.168.1.20:4000/task-hook"><button id="hookAdd">Add</button></div>
      <h3>3 · REST API</h3>
      <pre class="api">GET  ${esc(base)}/api/due?within=60    tasks due in the next 60 min
GET  ${esc(base)}/api/events          live stream (SSE): "due", "change"
GET  ${esc(base)}/api/state           everything
POST ${esc(base)}/api/lists/:id/tasks {"text":"…","due":"2026-12-01T17:00"}</pre>`;
    body.innerHTML = draw();
    const m = modal({ title: 'Connect other apps', body, wide: true, buttons: [{ label: 'Done', primary: true }] });
    const wire = () => {
      body.querySelector('[data-a="copysnip"]').onclick = () => copy(`<script src="${base}/popup.js"></script>`, 'Snippet copied');
      body.querySelector('[data-a="test"]').onclick = () => api('POST', '/api/test-popup');
      body.querySelector('[data-a="notify"]').onclick = async () => {
        if (!('Notification' in window)) return toast('Desktop alerts not supported here');
        const p = await Notification.requestPermission(); toast(p === 'granted' ? 'Desktop alerts enabled' : 'Desktop alerts blocked');
      };
      body.querySelector('#hookAdd').onclick = async () => {
        const url = body.querySelector('#hookUrl').value.trim();
        try { S.webhooks = await api('POST', '/api/webhooks', { url }); body.innerHTML = draw(); wire(); toast('Webhook added'); } catch (e) { toast(e.message); }
      };
      body.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { S.webhooks = await api('DELETE', '/api/webhooks', { url: b.dataset.del }); body.innerHTML = draw(); wire(); });
    };
    wire();
  }

  // ---------- toasts & due alerts ----------
  function toast(msg, actions = [], opts = {}) {
    const el = document.createElement('div');
    el.className = 'toast' + (opts.cls ? ' ' + opts.cls : '');
    el.innerHTML = `<div class="toast-msg">${opts.html || esc(msg)}</div>`;
    if (actions.length) {
      const row = document.createElement('div'); row.className = 'toast-actions';
      actions.forEach(a => { const b = document.createElement('button'); b.textContent = a.label; b.onclick = () => { a.fn(); dismiss(); }; row.append(b); });
      el.append(row);
    }
    const dismiss = () => { el.classList.add('out'); setTimeout(() => el.remove(), 250); };
    $('#toasts').append(el);
    const plain = [...document.querySelectorAll('#toasts .toast:not(.due-toast):not(.out)')];
    plain.slice(0, Math.max(0, plain.length - 2)).forEach(x => { x.classList.add('out'); setTimeout(() => x.remove(), 250); });
    setTimeout(dismiss, opts.ms || (actions.length ? 7000 : 2800));
    return el;
  }
  function chime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [880, 1320].forEach((f, i) => {
        const o = ctx.createOscillator(), gn = ctx.createGain(); o.frequency.value = f; o.type = 'sine';
        gn.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.18); gn.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + i * 0.18 + 0.02);
        gn.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.18 + 0.5);
        o.connect(gn).connect(ctx.destination); o.start(ctx.currentTime + i * 0.18); o.stop(ctx.currentTime + i * 0.18 + 0.55);
      });
    } catch {}
  }
  function dueAlert({ task: t, overdue, test }) {
    chime();
    const el = toast('', [
      ...(test ? [] : [
        { label: '✓ Done', fn: async () => { await api('PATCH', `/api/lists/${t.listId}/tasks/${t.id}`, { done: true }); load(); } },
        { label: '⏰ 10 min', fn: () => api('POST', `/api/lists/${t.listId}/tasks/${t.id}/snooze`, { minutes: 10 }) },
        { label: 'Open', fn: () => { selectList(t.listId); setTimeout(() => taskModal(t.id), 50); } }]),
      ...(test ? [{ label: 'OK', fn: () => {} }] : []),
    ], { cls: 'due-toast', ms: 30000, html: `<span class="due-tag" style="--c:${t.color}">${esc(t.listName)} · ${overdue ? 'Overdue' : 'Due ' + esc(TaskDates.fmt(t.due))}</span><b>${esc(t.text)}</b>` });
    setTimeout(() => { const b = el.querySelector('button'); b && b.focus(); }, 50);
    if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
      try { new Notification(`${t.listName}: ${t.text}`, { body: overdue ? 'Overdue' : 'Due ' + TaskDates.fmt(t.due), icon: '/icon.svg', tag: t.id }); } catch {}
    }
  }

  // ---------- wiring ----------
  $('#newListBtn').onclick = async () => {
    const name = await promptModal('New list', '', 'Groceries, Chores, Weekend…', 'Create');
    if (name) { const l = await api('POST', '/api/lists', { name }); currentId = l.id; showArchive = false; await load(); input.focus(); }
  };
  $('#archiveToggle').onclick = () => { showArchive = !showArchive; render(); if (!showArchive) Nav.focus($('#archiveToggle')); };
  $('#settingsBtn').onclick = settingsModal;
  $('#voiceBtn').onclick = voice;
  $('#quickBtn').onclick = quickModal;
  $('#printBtn').onclick = () => current() && printList(current().id);
  $('#shareBtn').onclick = shareModal;
  $('#moreBtn').onclick = listMenu;
  Nav.actions({
    voice, quick: quickModal, menu: () => modalStack.length ? null : listMenu(),
    add: () => { if (!modalStack.length && !showArchive) Nav.focus(input); },
    next: () => !modalStack.length && cycleList(1), prev: () => !modalStack.length && cycleList(-1),
    print: () => current() && printList(current().id),
  });

  const tick = () => { $('#clock').textContent = new Date().toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' }); };
  tick(); setInterval(tick, 15000);
  setInterval(() => { if (!modalStack.length) renderMain(); }, 60000); // keep "overdue" labels fresh

  let reloadT;
  function connect() {
    const es = new EventSource('/api/events');
    es.addEventListener('change', () => { clearTimeout(reloadT); reloadT = setTimeout(load, 120); });
    es.addEventListener('due', e => dueAlert(JSON.parse(e.data)));
  }

  load().then(() => { connect(); Nav.focus(input); }).catch(e => toast('Could not reach the Tasks server: ' + e.message));
})();
