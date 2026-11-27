// Natural-language due dates: "milk tomorrow at 5pm", "call mom friday", "pay rent in 3 days"
(function (g) {
  const DAYS = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
  const NUM = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11, twelve: 12, fifteen: 15, twenty: 20, thirty: 30, a: 1, an: 1 };
  const num = s => (s in NUM ? NUM[s] : parseInt(s, 10));

  function setTime(d, h, m) { d.setHours(h, m || 0, 0, 0); return d; }

  function parse(input) {
    let text = ' ' + input + ' ';
    let date = null, hasTime = false, h = 9, min = 0;
    const take = re => { const m = text.match(re); if (m) text = text.replace(m[0], ' '); return m; };

    // time: "at 5", "at 5pm", "5:30 pm", "noon", "tonight"
    let m;
    if ((m = take(/\s(?:at\s+)?(noon|midday)\s/i))) { h = 12; hasTime = true; }
    else if ((m = take(/\s(?:at\s+)?(midnight)\s/i))) { h = 23; min = 59; hasTime = true; }
    else if ((m = take(/\s(?:at|by|@)\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\s/i)) ||
             (m = take(/\s(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\s/i))) {
      h = +m[1]; min = +(m[2] || 0); const ap = (m[3] || '').toLowerCase()[0];
      if (ap === 'p' && h < 12) h += 12; if (ap === 'a' && h === 12) h = 0;
      if (!ap && h < 7) h += 12; // "at 5" probably means 5pm
      hasTime = h < 24 && min < 60;
    }
    if ((m = take(/\s(this\s+)?(morning)\s/i))) { h = hasTime ? h : 9; hasTime = true; date = date || new Date(); }
    if ((m = take(/\s(this\s+)?(afternoon)\s/i))) { h = hasTime ? h : 14; hasTime = true; date = date || new Date(); }
    if ((m = take(/\s(tonight|this\s+evening)\s/i))) { h = hasTime ? h : 20; hasTime = true; date = new Date(); }

    // dates
    const today = new Date();
    if ((m = take(/\s(?:by\s+|on\s+)?today\s/i))) date = new Date();
    else if ((m = take(/\s(?:by\s+|on\s+)?(?:tomorrow|tmrw)\s/i))) { date = new Date(); date.setDate(date.getDate() + 1); }
    else if ((m = take(/\sin\s+(\d+|a|an|one|two|three|four|five|six|seven|ten|fifteen|twenty|thirty)\s+(minute|min|hour|hr|day|week|month)s?\s/i))) {
      const n = num(m[1].toLowerCase()), u = m[2].toLowerCase(); date = new Date();
      if (u.startsWith('min')) { date = new Date(Date.now() + n * 60000); hasTime = true; h = date.getHours(); min = date.getMinutes(); }
      else if (u.startsWith('h')) { date = new Date(Date.now() + n * 3600000); hasTime = true; h = date.getHours(); min = date.getMinutes(); }
      else if (u === 'day') date.setDate(date.getDate() + n);
      else if (u === 'week') date.setDate(date.getDate() + 7 * n);
      else date.setMonth(date.getMonth() + n);
    }
    else if ((m = take(/\s(?:by\s+|on\s+)?next\s+week\s/i))) { date = new Date(); date.setDate(date.getDate() + ((8 - date.getDay()) % 7 || 7)); }
    else if ((m = take(/\s(?:by\s+|on\s+)?(?:this\s+)?weekend\s/i))) { date = new Date(); date.setDate(date.getDate() + ((6 - date.getDay() + 7) % 7)); }
    else if ((m = take(new RegExp('\\s(?:by\\s+|on\\s+)?(this\\s+|next\\s+)?(' + DAYS.join('|') + '|sun|mon|tue|tues|wed|thu|thur|thurs|fri|sat)\\s', 'i')))) {
      const key = m[2].toLowerCase().slice(0, 3), idx = DAYS.findIndex(d => d.startsWith(key));
      date = new Date(); let add = (idx - date.getDay() + 7) % 7; if (add === 0) add = 7; if (m[1] && /next/i.test(m[1]) && add < 7) add += 7;
      date.setDate(date.getDate() + add);
    }
    else if ((m = take(/\s(?:on\s+|by\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s/i))) {
      const mo = 'janfebmaraprmayjunjulaugsepoctnovdec'.indexOf(m[1].toLowerCase().slice(0, 3)) / 3;
      date = new Date(today.getFullYear(), mo, +m[2]); if (date < new Date(today.toDateString())) date.setFullYear(date.getFullYear() + 1);
    }
    else if ((m = take(/\s(?:on\s+|by\s+)?(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?\s/))) {
      let y = m[3] ? +m[3] : today.getFullYear(); if (y < 100) y += 2000;
      date = new Date(y, +m[1] - 1, +m[2]); if (!m[3] && date < new Date(today.toDateString())) date.setFullYear(y + 1);
    }

    if (!date && hasTime) { date = new Date(); if (setTime(new Date(), h, min) < new Date()) date.setDate(date.getDate() + 1); }
    if (!date) return { text: input.trim(), due: null };
    if (!hasTime) {
      // date with no time: today -> 5pm (or an hour from now if later), other days -> 9am
      const isToday = date.toDateString() === today.toDateString();
      if (isToday) { h = 17; if (today.getHours() >= 17) { const t = new Date(Date.now() + 3600000); h = t.getHours(); min = 0; } }
    }
    setTime(date, h, min);
    const clean = text.replace(/\s+(by|on|at|due)\s*$/i, '').replace(/\s+/g, ' ').trim();
    return { text: clean || input.trim(), due: date.getTime() };
  }

  function fmt(ms) {
    if (!ms) return '';
    const d = new Date(ms), n = new Date();
    const day = new Date(d.toDateString()), today = new Date(n.toDateString());
    const diff = Math.round((day - today) / 86400000);
    const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).replace(':00', '');
    let label;
    if (diff === 0) label = 'Today'; else if (diff === 1) label = 'Tomorrow'; else if (diff === -1) label = 'Yesterday';
    else if (diff > 1 && diff < 7) label = d.toLocaleDateString([], { weekday: 'long' });
    else label = d.toLocaleDateString([], { month: 'short', day: 'numeric', year: d.getFullYear() === n.getFullYear() ? undefined : 'numeric' });
    return label + ' · ' + time;
  }
  function status(ms) {
    if (!ms) return '';
    const left = ms - Date.now();
    if (left < 0) return 'overdue';
    if (left < 3600000 * 3 || new Date(ms).toDateString() === new Date().toDateString()) return 'soon';
    return '';
  }
  g.TaskDates = { parse, fmt, status };
})(window);
