# anTV (tvhub.py) Handoff Specification

Version 0.26.1 · handoff for continuing work in a new chat. Attach `tvhub.py`, the `backgrounds/` folder, `Setup-TVHub.ps1`, and `Setup-TVHub.bat` (or the zip) alongside this document. Also attach `anTV_Popup_Protocol_Spec.md` (the contract for pop-ups from apps) and the Tasks app (`tasks.zip`, the reference app).

## 1. What it is

A single-file Python 3 + GTK3 (PyGObject) "10-foot" media launcher. It runs on Linux Mint (Cinnamon/X11) and Windows 10/11 (via MSYS2), and it's meant for a PC connected to a TV, often on a dual-monitor setup.

- **Branding:** the main screen title is "anTV". The file name stays `tvhub.py`.
- **Versioning:** versions live in the code, not the file name. `VERSION` and a `CHANGELOG` list sit near the top of the file. They show in Settings (About, and the classic dialog's About tab) and via `tvhub.py --version`.
- **Release rule:** bump `VERSION`, add one `CHANGELOG` line, and rebuild the zip as `TVHub-all-files-<version>.zip`. The zip contains `tvhub.py`, the `backgrounds/` folder, `Setup-TVHub.ps1`, `Setup-TVHub.bat`, the `tasks/` folder (the Tasks app, reference app for pop-ups), this handoff document and `anTV_Popup_Protocol_Spec.md`. Unzip it all into one folder: the setup script finds `tvhub.py` and `tasks\` next to itself. Since 0.25.1 the zip includes the setup scripts again.
- **Numbering:** versions are 0.x because nothing has run on real hardware yet. The changelog lists each release 0.1 to 0.26.1.
- **Files:** `Setup-TVHub.ps1` and `.bat` are the Windows installer. They set up MSYS2, GTK, VLC, and optionally Node.js, Chrome, adb, and a firewall rule. They have never been run. Updated in 0.25.1: switch `-Tasks` (or the question) installs Node.js and runs `tvhub.py --add-node-app Tasks <tasks folder> http://localhost:3000`, which adds a Tasks card with pop-ups and keep-running on (the script refuses while anTV is open, because anTV's next save would overwrite the config); `-Firewall` also opens `node.exe` on Private networks so a phone can open Tasks; `-Check` also reports the anTV version, the tasks folder and whether the Tasks card is configured. The PowerShell changes were only checked by eye (no PowerShell in the test sandbox). There is no Linux setup script, only apt commands in the replies.

## 2. User preferences and constraints

- **Everything as an option, in Settings.** Settings should be readable: dark, with thick text.
- **TV-friendly (10-foot) UI.** It must work with a remote, a gamepad, and a phone.
- **Honesty about limits.**
  - The launcher itself is ad-free.
  - anTV does not and will not strip ads from Netflix, Hulu, or Peacock. Their ad-free tiers need a subscription and DRM.
  - SmartTube is the user's own choice of third-party app. Its APK should come only from the author's official GitHub releases.
- **Android apps** may be Linux-only. The user doesn't yet know their graphics card.
- **Current focus:** reliability and the TV experience. The user writes tersely, often says "continue", and expects a status line on long runs.

## 3. Features (all in `tvhub.py`)

### Main screen

- The header holds the title, a settings cog, a clock (12-hour, 24-hour, or off), and a status toast line.
- The favorites row either scrolls sideways or wraps as a grid. Below it is an "All apps" grid.
- Starred items anywhere, including inside folders, appear in the favorites row.
- "Show other apps" can be switched off in Settings.
- Folders are navigable. Back, Esc, or a "◂ Back" card goes up a level, and a breadcrumb shows the path.
- Cards can be small, medium, large, or extra large, in wide, classic, square, or poster shapes. All cards share one size.
- A card can have a picture (fill or fit) and an optional "picture only" mode.
- There is an idle fade of the cards and a background picture or slideshow folder (interval and shuffle).
- **Default backgrounds (0.23):** `backgrounds/` next to `tvhub.py` ships three pictures. On startup `seed_backgrounds()` copies each one once into the config folder's `backgrounds/` (`BG_DIR`), tracked in `.seeded` so a deleted picture stays deleted. `Hub.bg_files` uses the chosen slideshow folder first, then the single chosen picture, then `BG_DIR` (unless `background_default` is off). Settings > Look can toggle this, add pictures (`add_backgrounds`) and open the folder (`open_path`).
- **Node.js default (0.24):** the Start command defaults to `node server.js` (form, launch fallback), filled in when the type is Node.js and the field is empty.
- **Popular links (0.24):** `POPULAR_LINKS` (name, address, color) feeds the Popular apps menu: Tiedye Sasquatch (https://yeti.tiedyesasquatch.online) and FreeBirth (https://freebirth.ai.studio). Add more tuples there. `choose_dialog` scrolls when there are more than 8 options.
- **Your data (0.24):** Settings section/tab "Your data": *Save a backup* (`make_backup`: zip of `config.json`, `images/`, `backgrounds/`, `backup-info.json`; browser profiles are deliberately left out), *Restore from a backup* (`restore_backup`: rejects zips without config.json, ignores unsafe paths, rewrites picture paths from another config folder), and *Delete all data and start new* (`Hub.wipe_flow`: warning 1 offers "Save a backup first", warning 2 defaults to "No"; `wipe_data` removes config, images, backgrounds, profiles, logs; then DEFAULT is restored and backgrounds reseeded). After restore or wipe both settings screens close.
- **Command line (0.25.1):** `--add-node-app NAME FOLDER [URL]` (`add_node_app`) adds or fixes a Node.js card with `popups` and `keepalive` on; prints `added`, `updated` or `exists`. Run it while anTV is closed.
- **Hide and Quit (0.23):** both settings screens have Hide (saves, then `Hub.hide_to_taskbar`, which iconifies) and Quit (asks first, then `Hub.quit_app`). The TV screen has them as list entries and footer buttons; the classic dialog has them as buttons. On the main screen the H key hides and Esc/Q quits.
- Add, Node.js, and Install APK cards sit in the grid. `+ Add app` opens a menu: Popular apps, website or program, folder, Node.js app, or APK.

### Pop-ups from apps (0.25)

Full contract: `anTV_Popup_Protocol_Spec.md`. Summary of what the code does:

- **Feeds (pull):** `PopupFeed` (one daemon thread per source) reads `<origin>/antv.json`, then the SSE stream it names (default `/api/events`), and reconnects forever with 3 to 30 s back-off (70 s read timeout; apps ping every 25 s). Only `popup` events are used. If the manifest is 404, `legacy_due()` converts old Tasks `due` events.
- **Push:** `PopupCenter.start_push` serves `POST /notify` (header `X-Antv-Token`, max 8 KB) on `popup_port` (8767), localhost only unless `popup_lan`. Off by default (`popup_push`). Token is `popup_token`.
- **Validation:** `popup_clean` (pure function) limits lengths, accepts only `#rrggbb`, max 3 actions, and for feeds keeps only action URLs on the feed's own origin (relative URLs are resolved against it); pushed pop-ups need absolute URLs.
- **Display:** `PopupWindow` is a `Gtk.WindowType.POPUP` (override-redirect on X11) so a fullscreen kiosk browser or Waydroid cannot stack above it (a normal keep-above toplevel ended up underneath in the openbox test). It never takes focus. One card at a time; queue max 20; `high` priority jumps the queue; duplicate `(source, id)` ignored for 5 min.
- **Answering:** `Hub.gamepad_action` and `Hub.remote_key` call `PopupCenter.handle` first: left/right choose, select runs, back/escape dismiss; up/down/menu/home are never consumed. Mouse clicks work on the buttons. `Hub.other_windows()` ignores the pop-up (it has `_antv_popup = True`) for idle fade, `remote_launch` and `remote_key`.
- **Sources:** `PopupCenter.sources()` = `popup_sources` (Settings) plus any app card with `"popups": true` (its URL origin). `sync()` starts/stops feeds; `apply()` also starts/stops the push server. Both run at startup and after settings are saved.
- **Open button:** `Hub.open_source_app` finds the card by origin or name, runs `kill_current` if an app is running, waits 3 s, then `launch`.
- **Keep running:** Node.js cards with `"keepalive": true` are started by `Hub.start_keepalive_servers` at startup (detached, `bg_servers`), reused by `node_worker` (never killed with the browser, never in `current.json`), and stopped by `stop_bg_servers` when anTV exits (`__main__` after `Gtk.main()`).
- **UI:** TV settings section "Pop-ups" (`rows_popups`, `set_popup_sources`), classic dialog tab "Pop-ups", app form checkboxes "Show this app's pop-ups" (web and Node.js) and "Keep its server running" (Node.js), `Hub.show_push_info`.

### Updates (0.26)

Settings section/tab "Updates" (`rows_updates`; classic tab built next to the Pop-ups tab). Config keys `update_mode` (`off`, `ask` default, `auto`; list `UPDATE_MODES`) and `update_repo` (`owner/name`, `owner/name@branch` or a github.com URL; `parse_repo`). Public repositories only.

- **Default repository (0.26.1):** `UPDATE_REPO_DEFAULT = "tdsas27/tvhub-anTV"`, read through `update_repo(cfg)`. It applies only while config.json has no `update_repo` key; a saved empty string means "no repository" and stops checking. That repo (public, default branch `master`, `tvhub.py` at the top, no releases at the time of writing) is followed in branch mode, so pushing a higher `VERSION` to `master` is enough to offer an update; real GitHub check and package download verified from the sandbox.
- **Check (`github_check`):** `releases/latest` of the repo. Asset choice: a `.zip` whose name contains `tvhub` or `antv`, else an asset named `tvhub.py`, else the release's `zipball_url`. A tag like `v0.27.0` gives the version (`ver_tuple` compares numerically); an unparseable tag means the version is read after the download. With `@branch`, or when the repo has no releases (default branch), only the first 12 KB of `raw.githubusercontent.com/.../tvhub.py` is read for `VERSION`, and the branch zip is downloaded to install. `http_get` turns network and HTTP errors into `UpdateError` with plain messages.
- **Automatic:** `Hub.update_first` runs 30 s after start, then `update_tick` hourly; it only checks when 12 hours have passed (`UPDATE_EVERY`, last check kept in `updates/state.json`, not in config.json, so it never saves unsaved TV-settings changes). Mode `ask` shows a green button next to the clock (`upd_btn`, also the U key) and a toast; mode `auto` downloads, tests and installs in the background thread and the button then says "Restart to finish updating". Network failures are silent and retried.
- **From a file:** `Hub.update_file_flow` takes a `tvhub.py` or the all-files zip (also a GitHub zip with one folder around it). A file that is not newer asks first (default No).
- **Package (`read_package`):** takes `tvhub.py`, `Setup-TVHub.ps1/.bat`, `*.md` next to it and everything in `tasks/` and `backgrounds/`; ignores `..`, drive letters, `node_modules` and `data.json` (the Tasks data file), and caps sizes. New pictures in `backgrounds/` reach the user's folder through `seed_backgrounds` at the next start.
- **Install (`install_package`):** writes `tvhub.py.new`, runs it with `--version` (`console_python`: python.exe, because pythonw has no stdout; must print the claimed version, 60 s limit), copies the running file to `updates/tvhub-<old>_<timestamp>.py` (5 kept), writes the extra files, then `os.replace`s `tvhub.py` last and writes `updates/pending.json`. A failed test changes nothing. A read-only app folder is refused with a message.
- **Safety net:** `update_boot_guard` counts starts while `pending.json` exists; the third start without a clean run restores the backup and restarts. `update_failed_start` does the same when `Hub()` raises right after an update (without a marker the error is raised as before). The marker is removed by `update_confirm`: 45 s after start, or after a normal exit. **Go back** (`rollback_update`, `Hub.update_rollback_flow`) restores the newest backup and consumes it, so repeating it goes further back.
- **Restart:** `Hub.restart_app` sets `RESTART["want"]` and quits; `__main__` stops the keep-running servers and calls `spawn_self`, which starts a new process 2 s later so the old one has let go of the ports (phone remote, pop-up push, Node servers).
- **Publishing a release (for the user):** push `tvhub.py` with a higher `VERSION`, create a GitHub release with a tag like `v0.27.0`, and attach `TVHub-all-files-<version>.zip` (or attach nothing: GitHub's source zip works too). Releases marked pre-release or draft are not seen.

### Launching

- **Web apps:** kiosk Chromium or Firefox, with one browser profile per service.
- **Commands:** run as local programs.
- **Node.js apps:** install, start, wait for the port, open in the browser, and stop the server afterwards.
- **Android apps:** adb to a Fire TV or Android device, or Waydroid on this PC.
- **Local media and USB:** a Local Media browser and USB drive cards. Drives are detected via GIO on Linux and polled on Windows, with eject.
- **Web Browser card:** has a picker and a separate profile.
- **Process handling:** every app runs in its own process group. State is saved in `current.json`.
- **Close app:** Ctrl+Alt+K or Super+Esc (Linux, via a Cinnamon shortcut set up by `--install`), Ctrl+Alt+K (Windows), `tvhub.py --kill`, the Xbox button, or the phone's Close button. These kill the process tree and then run `stop_cmds`.

### Input

- **Fire TV remote:** keys are mapped by action (select, back, menu, playpause, home) with a Learn screen.
- **Xbox controller:** read from `/dev/input/js*` on Linux (xpad layout) and from XInput on Windows. Inputs become synthetic key events for anTV windows. While Android is open they are forwarded to it with `os_key`.
- **Phone remote:** an opt-in, PIN-protected HTTP server (default port 8765) serving a mobile page. Endpoints are `/api/key`, `/api/launch`, `/api/volume`, `/api/type`, and `/api/mouse`. Wrong PINs lock out an IP for a minute.
  - **Tabbed page (0.22):** a bottom tab bar with D-pad (arrows, OK, Back/Esc/Play/Menu, volume, Close app), Touchpad (pad, click and scroll buttons, Hold), Type (text box, Send, Backspace, Enter), and Apps. `body` is `overflow:hidden` and `#main` is `100dvh` flex, so the page never scrolls. The Apps grid picks its columns from the app count (2, 3, or 4) with equal-height rows, and gets an inner scroll only above 20 apps. The last tab is remembered in `localStorage` (`tvtab`).
  - **Address badge (0.22):** while the remote is running, the main screen header shows `ip:port`, the PIN, and a QR code next to the clock (`Hub.refresh_remote_badge`, run from `tick_clock`). Clicking it (or pressing I) hides it until the remote is turned off and on again or anTV restarts. The QR comes from a built-in encoder, `qr_matrix` (byte mode, error correction L, versions 1-5), so no `qrcode` package is needed.
- **Phone touchpad:** a touchpad plus mouse buttons that control the cursor in any app.

### Android

- `adb` install, launch, and device discovery work, including Fire TV by IP.
- On Waydroid, anTV runs weston nested under X11:
  - Flags are `--backend=x11 --socket=antv-android --width --height --shell=kiosk`, plus `--use-pixman` for software rendering.
  - `wmctrl` places the weston window on the TV screen.
  - The app is started with `waydroid show-full-ui` and `waydroid app launch`, and stopped with `waydroid session stop`.
- Software rendering is automatic when an NVIDIA card is detected. The setting is `android_display`: auto, software, or hardware.
- Settings has an "Android check" that reports the graphics card, Waydroid, weston, and wmctrl status.
- **Popular apps:** YouTube (the web version at `youtube.com/tv`), FreeTube (the Flatpak `io.freetubeapp.FreeTube`, Linux only), a Piped or Invidious URL the user enters, and SmartTube (a guided install into Waydroid).

### Settings

- **Classic dialog:** dark and tabbed (Apps, Main screen, Look, System, About), with Save and Cancel.
- **TV-friendly (10-foot) screen:** off by default. Sections are Apps & favorites, Layout, Look, Screen & browser, Remote & devices, and About, plus "Save and close" and "Discard changes". It also has footer Discard and Save buttons. The Menu or Start key saves and closes. Changes stay in memory until saved. Back with unsaved changes asks Save, Discard, or Keep editing.
- **Hub screens opened from the TV menu:** the Popular apps, Install APK, and Add screens save by themselves, so unsaved TV changes are saved first.
- **Folders in both menus:** New folder, Open, Up, and "Move to folder…" (nested folders supported; a folder can't be moved into itself).

## 4. Config and files

- **Config location:** Linux `~/.config/tvhub/config.json`, Windows `%APPDATA%\tvhub`.
- **Other paths there:** `updates/` (`state.json`, `pending.json`, old versions `tvhub-<ver>_<time>.py`), `profiles/`, `images/` (copies of chosen pictures), `logs/`, `current.json`, and `current.json.killed` (a marker for deliberate stops).
- **Top-level config keys:** `monitor`, `apps`, `media_dirs`, `favorite_builtins`, `show_others`, `fav_layout` (scroll or grid), `clock`, `tile_font`, `tile_size`, `tile_shape`, `picture_fit`, `background`, `background_dir`, `background_interval`, `background_shuffle`, `idle_delay`, `idle_fade`, `idle_min`, `browser`, `home_url`, `remote` (key overrides), `gamepad` (mapping overrides), `popups`, `popup_pos`, `popup_secs`, `popup_sound`, `popup_sources`, `popup_push`, `popup_lan`, `popup_port`, `popup_token`, `update_mode`, `update_repo`, `background_default`, `web_remote`, `web_port`, `web_pin`, `android_hosts`, `android_display`, `tenft_settings`.
- **App item fields:**
  - Common: `name`, `type`, `color`, `favorite`, `picture_only`, `image`.
  - Web: `url`.
  - Command: `cmd`.
  - Node.js: `dir`, `cmd`, `url`, optional `wait`, `keepalive`.
  - Web and Node.js: optional `popups` (listen to this app's pop-ups).
  - Android: `package`, `device` (`"waydroid"`, an adb serial, or `ip:port`).
  - Folder: `apps` (nested).

## 5. Code map

- **Platform layer:** `IS_WIN`, `NOWIN`, `NEWGRP`, `exe_path`, `shell_cmd`, `kill_tree`, `kill_match`, `os_key`, `os_type`, `os_volume`, `os_mouse_*`, `win_removable_drives`, `eject_drive`, and `win_hotkey_loop`.
- **Android layer:** `find_adb`, `adb_*`, `android_*`, `waydroid_*`, `gpu_info`, `AndroidSession`, `place_window`, and `android_report`.
- **Process state:** `kill_current` with `STATE` and `KILLED`.
- **Dialog and style helpers:** `ensure_tenft_css` (the `.andark`, `.tenft`, and `#tvs-*` rules), `tenft`, `hook_back`, `choose_dialog`, `ask_text`, `run_busy`, `show_text`, `show_history`, and `show_shortcuts`.
- **Pop-up layer:** `origin_of`, `popup_clean`, `legacy_due`, `popup_from_event`, `chime`, `PopupFeed`, `PopupWindow`, `PopupCenter`; Hub: `other_windows`, `open_source_app`, `start_background_server`, `start_keepalive_servers`, `stop_bg_servers`, `port_open`, `node_paths`, `show_push_info`.
- **Update layer:** `UpdateError`, `ver_tuple`, `parse_repo`, `http_get`, `source_version`, `check_source`, `github_check`, `read_package`, `console_python`, `list_backups`, `install_package`, `rollback_update`, `update_boot_guard`, `update_failed_start`, `update_confirm`, `spawn_self`; Hub: `update_first`, `update_tick`, `update_bg`, `update_found`, `update_installed`, `update_check_flow`, `update_offer`, `update_apply`, `update_file_flow`, `update_rollback_flow`, `update_set_repo`, `update_badge_click`, `refresh_update_badge`, `restart_app`; TVSettings: `rows_updates`, `restart_after_update`.
- **Classes:**
  - `TVSettings`
  - `Splash`
  - `Browser` (the media browser)
  - `Gamepad` and `XInputPad`
  - `WebRemote` (plus the `PAGE` HTML and its JavaScript, the `qr_matrix` QR encoder, and `local_ips`)
  - `Hub` (the main window)
- **Folder and card helpers:** `is_folder`, `find_parent`, `remove_item`, `move_item`, `flatten_apps`, `folder_choices`, `collect_favorites`, `describe_app`, `tile_dims`, and `split_tiles`.
- **Key Hub methods:** `rebuild`, `refresh_remote_badge`, `draw_qr`, `hide_remote_badge`, `cur_apps` (honors `add_target`, so add flows add into the list being edited), `open_folder`, `up_folder`, `on_key`, `nav`, `launch*`, `install_apk`, `quick_add`, `add_menu`, `settings_dialog`, `tv_settings`, and `app_form`.

## 6. Hard-won lessons

- **GTK key names:** `Gdk.keyval_name` returns "Back" for XF86Back. `remote_action` therefore compares key codes through `_canon_key`, not names. Always test key handling with real GDK names.
- **Settings and add flows:** the classic settings dialog edits a deep copy of `apps`. Hub add flows must write into that copy through `hub.add_target`, otherwise saving overwrites them.
- **Window placement:** weston windows can't be found by process ID, so `place_window` uses the window title "Weston Compositor" with `wmctrl`.
- **Sandbox quirk:** the virtual display dies between shell calls, so restart it inside the same command as the test.
- **Test hygiene:** importing the file via `spec_from_file_location` leaves a `__pycache__` in the output folder, so delete it before presenting.

## 7. How I tested, and what that did not cover

- **Environment setup:** run `apt-get update`, then install `python3-gi gir1.2-gtk-3.0 xvfb openbox wmctrl weston imagemagick fonts-dejavu-core pciutils`. Run `Xvfb :99 -screen 0 1920x1080x24` plus `openbox`.
- **Screenshots:** `import -window root file.png`.
- **UI drivers:** import the module, create a `Hub()`, and drive it with `GLib.timeout_add`. A `pump()` timer auto-answers dialogs: click the big buttons (size request 680 wide) or fill the entry (380 wide).
- **Stubs and fakes:**
  - A stub `gi` module for pure-logic tests.
  - A fake `adb` script (devices, connect, install, pm list, monkey) and a fake `waydroid` script (status, show-full-ui, app launch/install/list, session stop).
  - A fake sysfs and `lspci` text for the graphics-card detection.
- **Checks:** `py_compile`, `pyflakes` (the "redefinition of 'after'" warning is expected), and `node --check` on the phone page's JavaScript.
- **Patching style:** small Python `replace` scripts with asserts.
- **0.26 checks:** logic tests with a temp app folder and a faked `http_get` (version ordering, `parse_repo` forms, release asset choice, zipball fallback, no-release branch fallback, `@branch`, rate-limit message; zips with and without a GitHub folder, `..` entries, `data.json`, `node_modules`, corrupt zip, syntax error and import-time crash in a new `tvhub.py`, a claimed version that doesn't match; backup, marker, boot guard 1-2-3, confirm, failed-start rollback, 5-backup limit, repeated go-back); `http_get` against a local HTTP server (200, partial read, 404, too big, connection refused); GUI flows in the Xvfb harness with scripted dialogs (check, up to date, install, Later, file install, older file, garbage file, rollback, background `ask` and `auto` checks, 12-hour limit, `off`, offline, TV Updates section and the classic tab, green button screenshot); real-process runs of `tvhub.py` in a temp folder (third unconfirmed start rolls back and relaunches, constructor failure rolls back, no marker means the error is not hidden, a clean Esc quit clears the marker); `spawn_self` starts the new process 2 s later without making the parent wait.
- **0.25 checks:** `popup_clean` (foreign action URLs dropped, push needs absolute URLs, bad colors), the real Tasks server on a test port with a feed connected through the manifest, test and overdue pop-ups, Done action changing the Tasks data, left/right/up handling, push with right and wrong token, queue, `high` jump, duplicate ids, pop-ups off, a keep-running Node server started and stopped, the Pop-ups section/tab in both settings screens, the app form checkboxes. Screenshot over the fullscreen hub (openbox) confirmed the card is on top.
- **0.24 checks:** popular links and the duplicate message, node form default, backup contents (no profiles), both wipe warnings (cancel, backup-first, No at warning 2, Yes), restore with a rewritten foreign config path, a zip with `..` entries, a non-backup zip, and the Your data section/tab in both settings screens.
- **0.23 checks:** seeding, delete-and-reseed, add pictures, the fallback order in `bg_files`, the Hide state change (Normal to Iconic and back, still fullscreen under openbox), the Quit confirm for No and Yes in both settings screens, and screenshots of the background and the TV Look section. Needs `x11-utils xdotool` and the gdk-pixbuf loaders (`librsvg2-common`) in the harness, otherwise images silently do not draw.
- **0.22 checks:** `qr_matrix` was verified against the `qrcode` library module for module (versions 2-4) and decoded with OpenCV, including from a screenshot of the header. The badge show/hide/re-enable flow was exercised in the Xvfb harness.
- **Never tested on real hardware or systems:**
  - Updates: a real GitHub repository and release (only a faked `http_get` and a local HTTP server); Windows (`pythonw.exe` to `python.exe` for the start-up test, `os.replace` of a running script, `spawn_self` flags); the refusal for a read-only app folder (the sandbox runs as root); the 12-hour timer over days; private repositories (not supported: no token).
  - Pop-ups: stacking above a real fullscreen Chromium kiosk, Waydroid and VLC on Cinnamon (Muffin) and on Windows; rounded corners need a compositor (square without one); the sound (`canberra-gtk-play`/`paplay`/`winsound`); the Open button's 3 s wait after closing an app; a Node.js server started by anTV on Windows.
  - Hide on Cinnamon and on Windows (only tested under openbox), and the Windows taskbar button of a borderless fullscreen window.
  - Windows (only simulated, with a mocked `ctypes.windll`, and the PowerShell script never run).
  - Real Waydroid, NVIDIA/AMD/Intel behavior, and SmartTube's UI on Waydroid.
  - A real Fire TV over adb, and what keys the Fire TV remote actually sends.
  - A physical Xbox controller, the phone page's touch gestures, and Cinnamon (Muffin) window stacking.
  - Netflix HD via Widevine, which Edge or Chrome should handle.

## 8. Known gaps and ideas

- **Updates:** no signature or checksum check (trust is the repository and HTTPS); no token for private repositories; no release-notes screen beyond the first 700 characters; a Linux package install into a root-owned folder can't be updated; the setup scripts are replaced but not re-run (a new dependency still needs `Setup-TVHub.bat`).
- **Dialogs:** the Add/Edit form and the file pickers are still normal dialogs, though they get the dark, big styling. In-window overlays would be more TV-like.
- **Built-in cards:** they can't have pictures or be dragged around.
- **Folders:** reordering is only possible in Settings, and open folders reset after Settings closes.
- **USB drives:** Windows only lists removable drives.
- **Phone page layout:** 0.22 was checked for script errors and tab/grid logic only (jsdom). Its real layout on a phone has not been seen; check the D-pad tab on a small phone (about 360x640) and the Apps tab with many apps.
- **Windows hotkey:** a learned Fire TV "Home" key can't become a global hotkey on Windows.
- **Android:** a Cage compositor as an alternative if weston misbehaves, an in-app "download SmartTube" helper (official GitHub only), and a Linux setup script.
- **Pop-ups:** apps on Android/Fire TV cannot be listened to (use push from a bridge); no icons or pictures on cards, no per-app mute, no quiet hours, no history of missed pop-ups. Fire TV remote keys go to the running app, not to the card (use the controller, the phone remote or the mouse).
- **Possible features:** HDMI-CEC TV control, Wake-on-LAN, and "continue watching" rows from Jellyfin and Plex.

## 9. First steps in the new chat

1. Run `py_compile` and `pyflakes` on the attached file and print `--version` to confirm 0.26.1.
2. Recreate the Xvfb harness (section 7) and run a smoke test before changing anything.
3. Ask what the user saw on the real machine, then fix real-hardware findings before adding features.
4. For every release: bump the version, update the changelog, rebuild the zip, delete `__pycache__`, and present `tvhub.py` and the zip.
