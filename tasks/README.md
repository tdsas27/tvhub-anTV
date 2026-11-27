# Tasks

A big-screen (10-foot) task list app. No installs: just Node 18+.

```
node server.js
```

Open **http://localhost:3000** on this computer, or the "On your network" address it prints from a TV, Fire TV (Silk browser), phone or tablet.
Settings via environment: `PORT=8080`, `REMIND_LEAD_MIN=30` (how early pop-ups fire, default 15), `TASKS_DATA=/path/data.json`.

## Features
- **Lists**: create, rename, recolor, duplicate, delete. Switch with the sidebar, LB/RB, or ⏪ ⏩.
- **Due dates**: type them naturally ("milk tomorrow at 5pm", "call mom friday", "pay rent in 3 days", "dentist dec 12 at 10:30") or use the 📅 picker (quick choices, made for a remote). Overdue tasks turn red and sort to the top.
- **Print**: 🖨 Print opens a clean black-and-white checklist. More → "Print with completed" includes the checked items too.
- **Archive**: More → Archive list. The sidebar's Archived view lets you restore, print or delete.
- **Voice**: 🎤 Voice (or X on a gamepad, Play/Pause on a remote). Say a task with a date, "new list Groceries", "switch to Chores", or several items with "next" between them.
- **Quick add**: anything you add twice shows up as a chip. ⚡ Quick add lets you ★ pin items for good, remove them or create your own.
- **Share**: Share → View only / Can edit gives a link anyone on your network can open (live updates). You can also copy the list as text, email it or text it.
- **Reminders**: a pop-up with a chime appears 15 minutes before a task is due, with Done / Snooze 10 min / Open.

## Controls
| | Keyboard | Fire TV remote | Gamepad |
|---|---|---|---|
| Move | Arrows | D-pad | D-pad / left stick |
| Select | Enter | OK | A |
| Back / close | Esc | Back | B |
| Voice | V | Play/Pause | X |
| Add task | N | | Y |
| Prev / next list | | ⏪ / ⏩ | LB / RB |
| List menu | | Menu | Start |
| Quick add | Q | | Select |

## Working with anTV (TV launcher)
Tasks speaks the **anTV Pop-up Protocol** (see `anTV_Popup_Protocol_Spec.md`). It serves `GET /antv.json` and sends `popup` events on `/api/events`, so anTV shows due tasks as a card on top of whatever is running (Netflix, VLC, the home screen), with Done / 10 min / Open buttons you press with the controller, phone remote or mouse.

Set up in anTV (0.25+): add Tasks as a **Node.js app** (project folder = this folder, start command `node server.js`, open at `http://localhost:3000`), then tick **Show this app's pop-ups** and **Keep its server running in the background** on its card. Check Settings > Pop-ups: it should say "1 of 1 connected". Use ⚙ Connect apps > 🔔 Send test pop-up to try it.

## Hooking Tasks into another app
Open **⚙ Connect apps** in the sidebar. There are three ways:

1. **Drop-in pop-up**: add one line to any web page and due tasks pop up there with Done / Snooze buttons:
   ```html
   <script src="http://YOUR-PC-IP:3000/popup.js"></script>
   ```
   Options: `data-position="top-right"`, `data-lists="Groceries,Chores"`, `data-sound="off"`.
   For your own code: `TasksPopup.on(task => …)`, `TasksPopup.due(60)`, `TasksPopup.add(listId, text, due)`.
2. **Webhooks**: Tasks POSTs JSON to your URL on `task.due`, `task.created` and `task.completed`.
3. **REST + live stream**:
   - `GET /api/due?within=60` returns tasks due in the next 60 minutes (and overdue ones)
   - `GET /api/events` is a Server-Sent Events stream with `due` and `change` events
   - `GET /api/state` returns everything
   - `POST /api/lists/:id/tasks` with `{"text":"…","due":"2026-12-01T17:00"}`
   - `PATCH /api/lists/:id/tasks/:taskId` with `{"done":true}`
   - `POST /api/lists/:id/tasks/:taskId/snooze` with `{"minutes":10}`

## Notes
- **Voice** only works in Chrome, Edge or Safari, and only on `http://localhost` or an `https://` address, because browsers block the mic on plain-http network addresses. On a TV or phone, use the on-screen keyboard's own mic button instead.
- Everything is saved in `data.json`. Back up that file to keep your lists.
- There's no login. Anyone on your network who can reach the port can use it, so don't expose it to the internet.
