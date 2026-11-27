# anTV Pop-up Protocol v1: spec for building apps that work with anTV

Give this whole file to the AI that is building (or changing) an app for anTV. It is written to be followed literally.

anTV (`tvhub.py`, version 0.25.0 or newer) can show a pop-up card on top of whatever is on the TV (a kiosk browser, Waydroid, VLC, anTV's own home screen). The app that owns the information (Tasks, a doorbell app, a download manager) just announces it; anTV draws it, plays the sound, queues it, and lets the person answer with a controller, the phone remote, or the mouse. **Apps never draw their own overlay and never need to be in front.**

## 0. Paste-ready prompt (short version)

> Build this app so it works with anTV pop-ups. Follow `anTV_Popup_Protocol_Spec.md` exactly. In short: (1) the app runs a local web server (Node.js, `node server.js`, port from `PORT`, no login, no install step beyond `npm install` if needed); (2) it serves `GET /antv.json` with `{"protocol":1,"name":"...","color":"#rrggbb","events":"/api/events"}`; (3) its Server-Sent-Events stream at that path sends `event: popup` messages whose JSON follows section 4, with a stable unique `id`, a `: ping` comment every 25 seconds, and **relative** action URLs; (4) any time something deserves attention (a reminder, finished job, alert) it sends one `popup` event; (5) UI for the app itself follows the 10-foot rules in section 8; (6) include the checklist in section 10 in your final answer and run the tests in section 9.

## 1. How it fits together

```
 your app (server)                        anTV (tvhub.py)                          TV
 ─────────────────                        ───────────────                          ──
 GET  /antv.json            ◄── reads once per connect
 GET  /api/events (SSE)     ◄── stays connected, reconnects forever
   event: popup  ───────────────────────► checks it, queues it ─────────────────► card on top of any app
 PATCH /api/.../done        ◄── anTV calls it when the person presses "Done"
```

Two ways to deliver a pop-up. Use **A** unless you cannot run a server.

| | A. Feed (pull, preferred) | B. Push |
|---|---|---|
| Who connects | anTV connects to your app | your program POSTs to anTV |
| Needs | an SSE endpoint + `/antv.json` | anTV's push address and key |
| Answer buttons | yes, anTV calls your URLs back | only absolute URLs you give it |
| Works if your app starts later | yes (anTV retries every 3 to 30 s) | n/a |

## 2. Delivery A: the feed (what to implement)

### 2.1 Manifest: `GET /antv.json`

Return JSON, status 200, any origin allowed (`Access-Control-Allow-Origin: *`):

```json
{ "protocol": 1, "name": "Tasks", "color": "#ffb84d", "events": "/api/events", "open": "/" }
```

| Field | Required | Meaning |
|---|---|---|
| `protocol` | yes | the number `1` |
| `name` | yes | short app name shown on every card (max 40 chars) |
| `color` | no | default accent, `#rrggbb` only |
| `events` | no | path of the SSE stream (default `/api/events`) |
| `open` | no | path of the app's main page (information only for now) |

If the manifest answers 404, anTV falls back to the legacy Tasks format (see section 7). New apps must serve the manifest.

### 2.2 Stream: Server-Sent Events

`GET <events>` with `Content-Type: text/event-stream`, `Cache-Control: no-store`, kept open.

Rules:
1. Send `retry: 3000` once at the start.
2. Send a comment line `: ping` followed by a blank line **at least every 25 seconds**. anTV treats 70 seconds of silence as a dead connection and reconnects.
3. A pop-up is exactly: `event: popup`, then `data: <one line of JSON>`, then a blank line. The JSON must be on one line.
4. The same stream may carry other events (`change`, etc.). anTV ignores everything except `popup`.
5. Do not replay old pop-ups when anTV (re)connects. Send only new ones. (anTV also ignores a repeated `id` for 5 minutes, but do not rely on it.)

Minimal Node.js (no packages):

```js
const clients = new Set();
function popup(p) {                       // call this whenever something needs attention
  const msg = `event: popup\ndata: ${JSON.stringify(p)}\n\n`;
  for (const res of clients) res.write(msg);
}
// inside your http server's request handler:
if (url.pathname === '/antv.json') {
  res.writeHead(200, { 'content-type': 'application/json', 'access-control-allow-origin': '*' });
  return res.end(JSON.stringify({ protocol: 1, name: 'My App', color: '#5ec8ff', events: '/api/events' }));
}
if (url.pathname === '/api/events') {
  res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' });
  res.write('retry: 3000\n\n');
  clients.add(res);
  const ping = setInterval(() => res.write(': ping\n\n'), 25000);
  req.on('close', () => { clearInterval(ping); clients.delete(res); });
  return;
}
```

Minimal Python (standard library):

```python
# inside a BaseHTTPRequestHandler.do_GET for /api/events
self.send_response(200); self.send_header("Content-Type", "text/event-stream")
self.send_header("Cache-Control", "no-store"); self.end_headers()
self.wfile.write(b"retry: 3000\n\n")
# keep the connection; for each pop-up:  self.wfile.write(b"event: popup\ndata: " + json.dumps(p).encode() + b"\n\n"); self.wfile.flush()
# every <=25 s:                           self.wfile.write(b": ping\n\n"); self.wfile.flush()
```

## 3. Delivery B: push

Only if the program cannot serve a feed (a script, a cron job, a native program). The person turns it on in anTV: Settings > Pop-ups > "Let other programs on this PC send pop-ups". They then use "Show the address and key" to read the address and key.

```
POST http://127.0.0.1:8767/notify
X-Antv-Token: <key shown in anTV>
Content-Type: application/json

{ "app": "Backup script", "title": "Backup finished", "body": "42 GB copied", "color": "#7ee08a" }
```

* Same JSON as section 4, plus `app` (the name to show). The body must be under 8 KB.
* Answer: `200 {"ok":true}`, `401` wrong key, `400` nothing to show.
* The address is localhost only unless the person also turns on "...also from other devices on my network". Never hard-code the key; make it a setting of your program.
* Action URLs in pushed pop-ups must be **absolute** (`http://...`).

## 4. The pop-up object

```json
{
  "id": "task:abc123:1764345600000",
  "title": "Take out the trash",
  "body": "Optional second line, smaller",
  "tag": "Chores · Due 5:00 PM",
  "color": "#ffb84d",
  "priority": "normal",
  "timeout": 20,
  "sound": true,
  "actions": [
    { "label": "✓ Done",   "method": "PATCH", "url": "/api/lists/L1/tasks/abc123", "body": { "done": true } },
    { "label": "⏰ 10 min", "method": "POST",  "url": "/api/lists/L1/tasks/abc123/snooze", "body": { "minutes": 10 } },
    { "label": "Open",     "kind": "open" }
  ]
}
```

| Field | Required | Rules |
|---|---|---|
| `id` | strongly | Stable and unique per event (max 80 chars). anTV drops a repeated `id` from the same app for 5 minutes. **Include anything that should make it show again** (for example the snooze time) in the id. |
| `title` | one of `title`/`body` | Big text. Max 120 chars, one short sentence. Whitespace is collapsed. |
| `body` | one of `title`/`body` | Smaller text under the title. Max 400 chars. |
| `tag` | no | Small colored line above the title, shown after the app name (max 60). |
| `color` | no | `#rrggbb` only (anything else is ignored). Defaults to the manifest color. |
| `priority` | no | `low` (no sound), `normal`, `high` (jumps ahead of queued pop-ups and replaces a normal one on screen). Use `high` sparingly: overdue, alarm, failure. |
| `timeout` | no | Seconds on screen (0 to 600). `0` = until dismissed. Default is the person's setting (20 s). |
| `sound` | no | `false` for silent. |
| `test` | no | `true` skips duplicate checking. For "send a test pop-up" buttons. |
| `actions` | no | Up to 3 buttons (anTV always adds **Dismiss** unless you add a `dismiss` action). |

### Actions

| Field | Meaning |
|---|---|
| `label` | Button text, max 24 chars. Emoji are fine. Required. |
| `kind` | `"http"` (default), `"open"`, or `"dismiss"`. |
| `method` | `GET`, `POST`, `PATCH`, `PUT`, `DELETE` (default `POST`). `http` only. |
| `url` | `http` only. **Relative** (`/api/...`) for feeds, resolved against the app's own address. Absolute URLs are accepted only if they point to the same host and port as the app; anything else is silently dropped. |
| `body` | Any JSON, sent as the request body (`{}` if missing; none for `GET`). |
| `close` | `false` keeps the pop-up open after the button. Default `true`. |

* `open` closes whatever is running and launches the anTV card for this app, found by the card's address (or name). It only works if the person has an anTV card for the app.
* anTV ignores the HTTP response (a failure shows a short message on anTV's home screen). Make actions **idempotent**: pressing Done twice must be harmless.
* The first action is selected when the card appears. Order buttons so the safest, most common one is first.

## 5. What anTV does with it (so you can design for it)

* **One card at a time**, queued (max 20). `high` priority goes first.
* It is a separate always-on-top window that **never takes keyboard focus**, so a movie keeps its keys while the card is up.
* **Answering:** controller or phone-remote Left/Right chooses a button, OK runs it, Back dismisses. Up/Down/Menu/Home are never taken, so volume and "close app" keep working. Mouse or touchpad clicks work too. A card disappears after its timeout.
* Where it appears (corner), the sound and the on/off switch are the person's settings in anTV (Settings > Pop-ups). Apps must not try to control them.
* An app is listened to when its card in anTV has **"Show this app's pop-ups"** ticked, or when its address is added under Settings > Pop-ups > Pop-up sources.
* Pop-ups only arrive **while the app's server is running**. A reminder app must keep running when it is not on screen. For Node.js apps, tick **"Keep its server running in the background"** on the card: anTV starts the server when anTV starts, reuses it when the card is opened, and stops it only when anTV quits.

## 6. Rules for the app's author (must / must not)

1. **MUST** serve `/antv.json` and the SSE stream from the same server that serves the app.
2. **MUST** send each pop-up once. Create the `id` from the thing that happened, not from a random number or the clock.
3. **MUST** use relative action URLs in feeds.
4. **MUST NOT** put secrets, tokens or personal data in a pop-up. It is shown on a TV for the whole room.
5. **MUST NOT** require a login for the app's own pop-up endpoints or action URLs (anTV cannot log in). The app is meant for the home network. Say so in the README (as Tasks does).
6. **MUST NOT** spam. Batch noisy events (for example "3 downloads finished") and use `low` priority for FYI messages.
7. **SHOULD** honor the app's own mute/quiet-hours settings before sending.
8. **SHOULD** read `PORT` from the environment (anTV passes it when the card's URL has a port) and print the address it listens on.
9. Keep titles short enough to read from the couch: one sentence, no markdown, no HTML.

## 7. Compatibility: old Tasks builds

If `GET /antv.json` returns 404, anTV listens to `/api/events` and converts Tasks' original `due` event (`{task:{id,listId,listName,color,text,due},overdue,test}`) into a pop-up with Done, 10 min and Open buttons. New apps must not rely on this; it exists only so older Tasks builds work.

## 8. Rules for the app's own screens (10-foot UI)

Apps in anTV are used from a couch with a remote, a controller, or a phone. Follow the pattern Tasks uses (`public/nav.js`).

* Everything reachable by arrow keys / D-pad. Visible focus ring. Enter = select. Esc / Back = go back or close. No hover-only features.
* Text 24 px or larger for primary content, high contrast, dark theme by default.
* No page needs a mouse, no tiny close buttons, no scrolling that cannot be done with arrows.
* Support gamepad A (select), B (back), D-pad, and Fire TV media keys where it is natural.
* Typing: rely on the on-screen keyboard or the phone remote's "Type" tab. Voice only works on `localhost`/https in browsers; offer it as an extra, never the only way.
* Listen on `0.0.0.0` and print the LAN address, so a phone can open it too.
* Start with `node server.js` (anTV's default), no build step on the TV; commit built assets.

## 9. Test it (do all of these and report the results)

1. Start the app. `curl -s http://localhost:PORT/antv.json` returns valid JSON with `"protocol":1`.
2. `curl -N http://localhost:PORT/api/events` stays open and prints `retry: 3000`; a `: ping` appears within 25 s.
3. Trigger a pop-up (include a "send test pop-up" button or endpoint in the app, like Tasks' `POST /api/test-popup`). The stream prints one `event: popup` with one-line JSON.
4. Validate the JSON against section 4: has `title` or `body`; `color` is `#rrggbb`; at most 3 actions; every `http` action has `method` and a **relative** `url`; labels at most 24 chars.
5. Call each action's URL yourself with `curl -X <method> -d '<body>'` and confirm the app changes state, and that calling it twice is harmless.
6. Trigger the same event twice: the second one must have the same `id` (or not be sent).
7. In anTV: tick "Show this app's pop-ups" on the card (or add the address under Settings > Pop-ups > Pop-up sources), then Settings > Pop-ups shows "1 of 1 connected". Press the app's test button; the card appears over another running app.
8. Controller or phone remote: Left/Right selects, OK runs, Back dismisses.
9. Stop and restart the app. anTV reconnects on its own within 30 s and the next pop-up arrives.

## 10. Checklist to put at the end of your answer

- [ ] `/antv.json` served (protocol 1, name, color)
- [ ] SSE stream with `retry`, 25 s pings, one-line `event: popup` JSON
- [ ] Stable unique `id` on every pop-up
- [ ] Relative action URLs, idempotent actions, at most 3 buttons, labels at most 24 chars
- [ ] No secrets in pop-ups; no login on pop-up/action endpoints; README says "home network only"
- [ ] Test-pop-up button or endpoint
- [ ] Server starts with `node server.js` and honors `PORT`; works when kept running in the background
- [ ] 10-foot UI rules followed
- [ ] Tests in section 9 run, results listed

## 11. Reference implementation

`tasks/server.js` in the Tasks app: `MANIFEST`, `toPopup()`, `broadcast('popup', ...)`, `GET /antv.json`, `POST /api/test-popup`. Tasks also keeps its older, independent hooks (`/popup.js` for web pages, webhooks, REST). Those are unrelated to anTV and stay.

## 12. Version and limits

* Protocol version 1. Unknown fields are ignored, so future versions can add fields. Never rename or remove the fields above.
* Not covered yet: Android/Fire TV apps (they cannot run a feed; use push from a bridge program), images/icons on cards, text entry on a card, per-app mute. Do not invent fields for these.
* anTV is Linux (X11) and Windows. Windows stacking and Cinnamon were not tested on real hardware at the time of writing.
