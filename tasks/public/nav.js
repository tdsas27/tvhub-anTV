// 10-foot navigation: arrow keys / D-pad / Fire TV remote / gamepad move focus spatially.
(function (g) {
  const SEL = 'button:not([disabled]), input:not([disabled]):not([type=hidden]), select, textarea, [tabindex="0"]';
  const handlers = { back: null, action: {} };
  let usingPointer = false;

  function layer() {
    const modals = document.querySelectorAll('#modalRoot .modal');
    return modals.length ? modals[modals.length - 1] : document.getElementById('app');
  }
  function visible(el) {
    if (el.closest('[hidden]')) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  }
  function focusables(scope = layer()) {
    return [...scope.querySelectorAll(SEL)].filter(visible);
  }
  function focus(el) {
    if (!el) return;
    el.focus({ preventScroll: true });
    el.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
  }
  function focusFirst(scope) {
    const els = focusables(scope);
    const pref = els.find(e => e.hasAttribute('data-autofocus')) || els[0];
    focus(pref);
  }

  function move(dir) {
    const cur = document.activeElement;
    const els = focusables();
    if (!cur || !els.includes(cur)) return focusFirst();
    const a = cur.getBoundingClientRect();
    const ac = { x: a.left + a.width / 2, y: a.top + a.height / 2 };
    let best = null, bestScore = Infinity;
    for (const el of els) {
      if (el === cur) continue;
      const b = el.getBoundingClientRect();
      const bc = { x: b.left + b.width / 2, y: b.top + b.height / 2 };
      let main, cross, overlap;
      if (dir === 'left' || dir === 'right') {
        main = dir === 'right' ? b.left - a.right : a.left - b.right;
        if ((dir === 'right' ? bc.x <= ac.x : bc.x >= ac.x)) continue;
        overlap = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        cross = overlap > 0 ? 0 : Math.abs(bc.y - ac.y);
      } else {
        main = dir === 'down' ? b.top - a.bottom : a.top - b.bottom;
        if ((dir === 'down' ? bc.y <= ac.y : bc.y >= ac.y)) continue;
        overlap = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        cross = overlap > 0 ? Math.abs(bc.x - ac.x) * 0.2 : Math.abs(bc.x - ac.x);
      }
      const score = Math.max(main, 0) + cross * 2.5;
      if (score < bestScore) { bestScore = score; best = el; }
    }
    if (best) focus(best);
  }

  function back() {
    if (handlers.back && handlers.back() !== false) return true;
    return false;
  }

  function isTyping(el) {
    return el && (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && !['button', 'checkbox', 'radio', 'submit', 'color', 'range'].includes(el.type)));
  }

  document.addEventListener('keydown', e => {
    usingPointer = false; document.body.classList.remove('pointer');
    const el = document.activeElement;
    const typing = isTyping(el);
    const k = e.key, code = e.keyCode;
    const dirs = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' };
    if (dirs[k]) {
      if (typing) {
        if (el.tagName === 'TEXTAREA' && (k === 'ArrowUp' || k === 'ArrowDown')) return;
        if (k === 'ArrowLeft' && !(el.selectionStart === 0 && el.selectionEnd === 0)) return;
        if (k === 'ArrowRight' && el.selectionStart !== el.value.length) return;
        if (el.type === 'datetime-local' || el.type === 'date' || el.type === 'time') return;
      }
      e.preventDefault(); move(dirs[k]); return;
    }
    if (k === 'Escape' || k === 'GoBack' || k === 'BrowserBack' || code === 4 || (k === 'Backspace' && !typing)) {
      if (back()) e.preventDefault();
      return;
    }
    if (k === 'Enter' && el && el.matches('[tabindex="0"]') && !typing) { e.preventDefault(); el.click(); return; }
    // Fire TV / media keys
    const act = handlers.action;
    if ((k === 'MediaPlayPause' || code === 179 || code === 85) && act.voice) { e.preventDefault(); act.voice(); return; }
    if ((k === 'MediaFastForward' || code === 228 || code === 90) && act.next) { e.preventDefault(); act.next(); return; }
    if ((k === 'MediaRewind' || code === 227 || code === 89) && act.prev) { e.preventDefault(); act.prev(); return; }
    if ((k === 'ContextMenu' || code === 82 || code === 93) && act.menu) { e.preventDefault(); act.menu(); return; }
    if (!typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (k === 'n' && act.add) { e.preventDefault(); act.add(); }
      else if (k === 'v' && act.voice) { e.preventDefault(); act.voice(); }
      else if (k === 'q' && act.quick) { e.preventDefault(); act.quick(); }
      else if (k === 'p' && act.print) { e.preventDefault(); act.print(); }
    }
  });
  document.addEventListener('pointermove', () => { if (!usingPointer) { usingPointer = true; document.body.classList.add('pointer'); } }, { passive: true });

  // ---- gamepad ----
  const held = {};
  const REPEAT_DELAY = 380, REPEAT_RATE = 120;
  function press(name, isDown, fn) {
    const t = performance.now();
    if (!isDown) { delete held[name]; return; }
    if (!held[name]) { held[name] = { next: t + REPEAT_DELAY }; fn(); }
    else if (t >= held[name].next && /^(up|down|left|right)$/.test(name)) { held[name].next = t + REPEAT_RATE; fn(); }
  }
  function poll() {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const p of pads) {
      if (!p) continue;
      const b = i => !!(p.buttons[i] && p.buttons[i].pressed);
      const ax = p.axes[0] || 0, ay = p.axes[1] || 0;
      press('up', b(12) || ay < -0.6, () => move('up'));
      press('down', b(13) || ay > 0.6, () => move('down'));
      press('left', b(14) || ax < -0.6, () => move('left'));
      press('right', b(15) || ax > 0.6, () => move('right'));
      press('a', b(0), () => { const el = document.activeElement; if (el && el !== document.body) { if (isTyping(el)) el.form ? el.form.requestSubmit() : el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })); else el.click(); } else focusFirst(); });
      press('b', b(1), back);
      press('x', b(2), () => handlers.action.voice && handlers.action.voice());
      press('y', b(3), () => handlers.action.add && handlers.action.add());
      press('lb', b(4), () => handlers.action.prev && handlers.action.prev());
      press('rb', b(5), () => handlers.action.next && handlers.action.next());
      press('start', b(9), () => handlers.action.menu && handlers.action.menu());
      press('select', b(8), () => handlers.action.quick && handlers.action.quick());
      break; // first connected pad only
    }
    requestAnimationFrame(poll);
  }
  addEventListener('gamepadconnected', () => { document.body.classList.add('gamepad'); });
  requestAnimationFrame(poll);

  g.Nav = {
    focusFirst, focus, focusables, move,
    onBack(fn) { handlers.back = fn; },
    actions(map) { Object.assign(handlers.action, map); },
  };
})(window);
