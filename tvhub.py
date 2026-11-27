#!/usr/bin/env python3
"""TV Hub - a 10-foot media launcher for Linux Mint (Cinnamon/X11).

Kill running app + its browser windows from anywhere: Ctrl+Alt+K (or Super+Esc)
       (also: python3 tvhub.py --kill). The hotkey is set up by --install.
Keys:  arrows = move   Enter = open   A = add app   N = add Node app   S = settings   B = pick browser   E = eject USB   Delete = remove app
       F1 = move launcher to next monitor   Esc/Q = quit
Config: ~/.config/tvhub/config.json   (edit freely, or use the + tile)
Run `python3 tvhub.py --install` to add it to your Mint menu.
Windows 10/11: run Setup-TVHub.bat first (installs GTK, VLC, etc.), then start TV Hub from its shortcut.
"""
import ast, copy, glob, hmac, io, json, os, random, re, secrets, select, shlex, shutil, signal, socket, struct, subprocess, sys, threading, time, types, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, urljoin
import urllib.request, urllib.error
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Gio, Pango
try:
    import fcntl  # Linux joystick ioctl (not on Windows)
except ImportError:
    fcntl = None

VERSION = "0.26.1"
CHANGELOG = [  # (version, what changed). Add a line here and bump VERSION for each release.
    ("0.1.0", "Launcher for Linux Mint: app cards (Jellyfin, Plex, Emby, Netflix, Hulu, Peacock...), kiosk browser, TV screen choice"),
    ("0.2.0", "Close-app hotkey (Ctrl+Alt+K, or tvhub.py --kill)"),
    ("0.3.0", "Settings screen: add, edit, remove and reorder apps"),
    ("0.4.0", "Local media browser and USB drive cards with plug-in detection and eject"),
    ("0.5.0", "Web Browser card with a browser picker"),
    ("0.6.0", "Card fonts and per-card background images"),
    ("0.7.0", "Node.js app cards (install, start, open, stop)"),
    ("0.8.0", "Amazon Fire TV remote support with Learn mapping"),
    ("0.9.0", "Home background picture and idle fade of the cards"),
    ("0.10.0", "Xbox controller support"),
    ("0.11.0", "Background slideshow folder with interval and shuffle"),
    ("0.12.0", "Phone remote: PIN-protected web page on your Wi-Fi"),
    ("0.13.0", "Windows version with a setup script"),
    ("0.14.0", "Phone touchpad and mouse buttons"),
    ("0.15.0", "anTV title and the favorites row"),
    ("0.16.0", "Optional TV-friendly (10-foot) settings screen"),
    ("0.17.0", "Settings cog and clock next to anTV, scrolling or grid favorites row, Esc on the phone remote, "
               "show/hide other apps moved into Settings, version and history in Settings"),
    ("0.18.0", "Dark, thicker-text settings (classic settings now in tabs and 25% wider); TV-friendly settings rows readable "
               "before they are selected; keyboard shortcut hints moved from the top bar into Settings; clearer clock"),
    ("0.19.0", "Install APKs onto a connected Android / Fire TV device (adb) or Waydroid, with Android app cards that launch them"),
    ("0.20.0", "Run Android apps (such as SmartTube) on this PC with Waydroid shown fullscreen on the TV screen; graphics-card detection and an Android check; Popular apps menu (YouTube, FreeTube, Piped/Invidious, SmartTube)"),
    ("0.21.0", "Folders that hold apps (with their own card or picture), picture-only cards, card size and shape options, "
               "Save and Discard in the TV-friendly settings"),
    ("0.22.0", "Phone remote page now has tabs (D-pad, Touchpad, Type, Apps) and fits one screen with no scrolling; "
               "the remote's address, PIN and a QR code show next to the clock until clicked"),
    ("0.23.0", "Hide (minimize to the taskbar) and Quit buttons in Settings (also the H key); default backgrounds folder "
               "with ready-made pictures, add your own pictures to it from Settings"),
    ("0.24.0", "Node.js apps start with node server.js by default; Popular apps menu now has web links "
               "(Tiedye Sasquatch, FreeBirth); Settings can save a backup of your data, restore it, "
               "or delete everything and start new (two warnings first)"),
    ("0.25.0", "Pop-ups: anTV shows notifications from your apps (Tasks first) on top of whatever is running, "
               "using the anTV Pop-up Protocol (feeds and a push address); answer them with the controller, "
               "phone remote or mouse; Node.js apps can keep running in the background; Pop-ups section in Settings"),
    ("0.25.1", "Setup-TVHub scripts included and updated (Tasks card added for you, firewall rule for Tasks); "
               "tvhub.py --add-node-app NAME FOLDER [URL] adds a Node.js card with pop-ups and keep-running turned on"),
    ("0.26.0", "Updates: anTV can check a GitHub repository (its latest release, or a branch) and install new versions "
               "by itself, or install one from a file you pick (tvhub.py or the all-files zip); the old version is kept "
               "so you can go back, and a version that fails to start is rolled back; Updates section in Settings"),
    ("0.26.1", "Updates look at github.com/tdsas27/tvhub-anTV unless you change the repository (or clear it to stop checking)"),
]
IS_WIN = sys.platform == "win32"
CFG_DIR = (os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "tvhub") if IS_WIN
           else os.path.expanduser("~/.config/tvhub"))
CFG = os.path.join(CFG_DIR, "config.json")

# ---- platform layer: everything that differs between Linux (Mint) and Windows ----
import ctypes
if IS_WIN:
    from ctypes import wintypes
    _user32 = ctypes.windll.user32

    class _KI(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p)]

    class _IU(ctypes.Union):
        _fields_ = [("ki", _KI), ("pad", ctypes.c_byte * 32)]

    class _IN(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("u", _IU)]

NOWIN = {"creationflags": 0x08000000} if IS_WIN else {}  # CREATE_NO_WINDOW
NEWGRP = ({"creationflags": 0x08000000 | 0x00000200} if IS_WIN else {"start_new_session": True})  # own process group
WIN_ALIASES = {"vlc": [r"%ProgramFiles%\VideoLAN\VLC\vlc.exe", r"%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe"],
               "kodi": [r"%ProgramFiles%\Kodi\kodi.exe"]}
_WIN_VK = {"Up": 0x26, "Down": 0x28, "Left": 0x25, "Right": 0x27, "Return": 0x0D, "BackSpace": 0x08,
           "XF86Back": 0xA6, "XF86AudioPlay": 0xB3, "Escape": 0x1B}


def exe_path(x):
    """Resolve a program name or a (%ENV%-style) path to an existing executable, else None."""
    p = os.path.expandvars(x)
    if os.path.isabs(p):
        return p if os.path.isfile(p) else None
    return shutil.which(x)


def shell_cmd(cmd):
    return ["cmd", "/c", cmd] if IS_WIN else ["bash", "-lc", cmd]


def node_present():
    if IS_WIN:
        return shutil.which("node") is not None
    return subprocess.run(["bash", "-lc", "command -v node"], capture_output=True).returncode == 0


def kill_tree(pid, force=False):
    if IS_WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, **NOWIN)
        return
    try:
        os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def kill_match(text, force=False):
    """Kill any process whose command line contains `text` (catches browser helpers that left the group)."""
    if not text:
        return
    if IS_WIN:
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.ProcessId -ne $PID -and "
              "$_.CommandLine.Contains('%s') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force "
              "-ErrorAction SilentlyContinue }" % text.replace("'", "''"))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, **NOWIN)
    else:
        subprocess.run(["pkill", "-9" if force else "-15", "-f", text], stderr=subprocess.DEVNULL)


def os_input_available():
    return IS_WIN or shutil.which("xdotool") is not None


def os_key(name):
    """Press a key in whatever window is focused (xdotool on Linux, keybd_event on Windows)."""
    if IS_WIN:
        vk = _WIN_VK.get(name)
        if vk:
            ext = 1 if vk in (0x25, 0x26, 0x27, 0x28) else 0
            _user32.keybd_event(vk, 0, ext, 0)
            _user32.keybd_event(vk, 0, ext | 2, 0)
    elif shutil.which("xdotool"):
        subprocess.Popen(["xdotool", "key", name])


def os_type(text):
    if IS_WIN:
        data = text.encode("utf-16-le")
        evs = []
        for u in struct.unpack("<%dH" % (len(data) // 2), data):
            for flags in (0x0004, 0x0004 | 0x0002):  # KEYEVENTF_UNICODE, then key-up
                evs.append(_IN(1, _IU(ki=_KI(0, u, flags, 0, None))))
        if evs:
            arr = (_IN * len(evs))(*evs)
            _user32.SendInput(len(arr), arr, ctypes.sizeof(_IN))
    elif shutil.which("xdotool"):
        subprocess.Popen(["xdotool", "type", "--delay", "20", "--", text])


def os_volume(op):
    if IS_WIN:
        vk = {"up": 0xAF, "down": 0xAE, "mute": 0xAD}.get(op)
        if not vk:
            return False
        _user32.keybd_event(vk, 0, 0, 0)
        _user32.keybd_event(vk, 0, 2, 0)
        return True
    cmd = {"up": ["set-sink-volume", "@DEFAULT_SINK@", "+5%"], "down": ["set-sink-volume", "@DEFAULT_SINK@", "-5%"],
           "mute": ["set-sink-mute", "@DEFAULT_SINK@", "toggle"]}.get(op)
    if cmd and shutil.which("pactl"):
        subprocess.Popen(["pactl", *cmd])
        return True
    return False


_xlock = threading.Lock()
_x11 = None


def _xlib():
    """X11 pointer control via libX11 + libXtst (no xdotool needed). Returns (X11, Xtst, display) or False."""
    global _x11
    if _x11 is None:
        try:
            x, t = ctypes.CDLL("libX11.so.6"), ctypes.CDLL("libXtst.so.6")
            x.XOpenDisplay.restype = ctypes.c_void_p
            x.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x.XWarpPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_int]
            x.XFlush.argtypes = [ctypes.c_void_p]
            t.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
            d = x.XOpenDisplay(None)
            _x11 = (x, t, d) if d else False
        except (OSError, AttributeError):
            _x11 = False
    return _x11


_X_BTN = {"left": 1, "middle": 2, "right": 3}
_WIN_BTN = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}  # (down, up)


def os_mouse_move(dx, dy):
    """Move the pointer relative to where it is, over any window."""
    if IS_WIN:
        _user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)  # MOUSEEVENTF_MOVE
        return True
    x = _xlib()
    if x:
        with _xlock:
            x[0].XWarpPointer(x[2], 0, 0, 0, 0, 0, 0, int(dx), int(dy))
            x[0].XFlush(x[2])
        return True
    if shutil.which("xdotool"):
        subprocess.Popen(["xdotool", "mousemove_relative", "--", str(int(dx)), str(int(dy))])
        return True
    return False


def os_mouse_button(btn, act="click"):
    """btn: left | right | middle.  act: click | double | down | up."""
    steps = {"click": [1, 0], "double": [1, 0, 1, 0], "down": [1], "up": [0]}.get(act)
    if btn not in _X_BTN or steps is None:
        return False
    if IS_WIN:
        down, up = _WIN_BTN[btn]
        for st in steps:
            _user32.mouse_event(down if st else up, 0, 0, 0, 0)
        return True
    x = _xlib()
    if x:
        with _xlock:
            for st in steps:
                x[1].XTestFakeButtonEvent(x[2], _X_BTN[btn], st, 0)
            x[0].XFlush(x[2])
        return True
    if shutil.which("xdotool"):
        n = str(_X_BTN[btn])
        cmd = {"click": ["click", n], "double": ["click", "--repeat", "2", n],
               "down": ["mousedown", n], "up": ["mouseup", n]}[act]
        subprocess.Popen(["xdotool", *cmd])
        return True
    return False


def os_scroll(notches):
    """Mouse-wheel notches; positive scrolls down."""
    n = max(-20, min(20, int(notches)))
    if not n:
        return True
    if IS_WIN:
        _user32.mouse_event(0x0800, 0, 0, ctypes.c_ulong((-n * 120) & 0xFFFFFFFF), 0)  # MOUSEEVENTF_WHEEL
        return True
    btn = 5 if n > 0 else 4
    x = _xlib()
    if x:
        with _xlock:
            for _ in range(abs(n)):
                x[1].XTestFakeButtonEvent(x[2], btn, 1, 0)
                x[1].XTestFakeButtonEvent(x[2], btn, 0, 0)
            x[0].XFlush(x[2])
        return True
    if shutil.which("xdotool"):
        subprocess.Popen(["xdotool", "click", "--repeat", str(abs(n)), str(btn)])
        return True
    return False


# ---- Android (APK) support. Android apps cannot run on this PC directly, so anTV installs them on a connected
# Android / Fire TV device with adb (or into Waydroid on Linux) and its Android cards launch them there.
def find_adb():
    p = shutil.which("adb")
    if p:
        return p
    cands = [os.path.expanduser("~/Android/Sdk/platform-tools/adb"), "/usr/lib/android-sdk/platform-tools/adb",
             "/opt/android-sdk/platform-tools/adb", r"%LocalAppData%\Android\Sdk\platform-tools\adb.exe",
             r"%ProgramFiles%\platform-tools\adb.exe", r"C:\platform-tools\adb.exe", r"%UserProfile%\platform-tools\adb.exe"]
    cands += glob.glob(os.path.expandvars(r"%LocalAppData%\Microsoft\WinGet\Packages\Google.PlatformTools*\platform-tools\adb.exe"))
    return next((r for r in (exe_path(c) for c in cands) if r), None)


def adb_run(*args, serial=None, timeout=60):
    """Run adb; returns (exit code, combined output)."""
    adb = find_adb()
    if not adb:
        return 127, "adb not found"
    cmd = [adb] + (["-s", serial] if serial else []) + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **NOWIN)
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    except OSError as ex:
        return 126, str(ex)
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def adb_devices():
    rc, out = adb_run("devices", "-l", timeout=20)
    devs = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in ("device", "unauthorized", "offline"):
            model = next((q.split(":", 1)[1] for q in parts[2:] if q.startswith("model:")), "")
            devs.append({"serial": parts[0], "state": parts[1], "model": model.replace("_", " ")})
    return devs


def adb_connect(addr):
    if ":" not in addr:
        addr += ":5555"
    rc, out = adb_run("connect", addr, timeout=10)
    bad = any(w in out for w in ("cannot", "unable", "failed", "refused"))
    return (("connected to" in out or "already connected" in out) and not bad), out


def android_packages(serial):
    rc, out = adb_run("shell", "pm", "list", "packages", "-3", serial=serial, timeout=30)
    return {ln.split(":", 1)[1].strip() for ln in out.splitlines() if ln.startswith("package:")}


def android_install(serial, apk):
    """Install an APK with adb. Returns (ok, output, newly_installed_package_or_None)."""
    before = android_packages(serial)
    rc, out = adb_run("install", "-r", apk, serial=serial, timeout=600)
    ok = rc == 0 and "Success" in out
    added = (android_packages(serial) - before) if ok else set()
    return ok, out, (sorted(added)[0] if added else None)


def waydroid_available():
    return (not IS_WIN) and shutil.which("waydroid") is not None


def waydroid_packages():
    try:
        r = subprocess.run(["waydroid", "app", "list"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {ln.split(":", 1)[1].strip() for ln in r.stdout.splitlines() if ln.strip().startswith("packageName:")}


def waydroid_install(apk):
    before = waydroid_packages()
    try:
        r = subprocess.run(["waydroid", "app", "install", apk], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return False, str(ex), None
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    added = (waydroid_packages() - before) if r.returncode == 0 else set()
    return r.returncode == 0, out, (sorted(added)[0] if added else None)


def android_launch(device, pkg):
    """Start an installed Android app. device = adb serial / ip:port, or 'waydroid'. Returns (ok, output)."""
    if device == "waydroid":
        try:
            r = subprocess.run(["waydroid", "app", "launch", pkg], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired) as ex:
            return False, str(ex)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()
    if device and ":" in device:
        adb_connect(device)
    out = ""
    for cat in ("android.intent.category.LAUNCHER", "android.intent.category.LEANBACK_LAUNCHER"):  # TV apps use the 2nd
        rc, out = adb_run("shell", "monkey", "-p", pkg, "-c", cat, "1", serial=device or None, timeout=30)
        if rc == 0 and "No activities found" not in out:
            return True, out
    return False, out


def find_apks(roots, limit=12):
    """APK files in the given folders (two levels deep), newest first."""
    found = []
    for root in roots:
        base = root.rstrip("\\/").count(os.sep)
        for d, dirs, files in os.walk(root):
            if d.count(os.sep) - base >= 2:
                dirs[:] = []
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            found += [os.path.join(d, f) for f in files if f.lower().endswith(".apk")]
            if len(found) >= limit * 3:
                break
    found.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return found[:limit]


# ---- Waydroid on an X11 desktop (Linux Mint): a nested Wayland compositor (weston) shows Android on the TV screen
WAYDROID_SOCKET = "antv-android"
GPU_VENDORS = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}


def gpu_info(drm_root="/sys/class/drm", lspci_text=None):
    """Graphics cards found: [{'vendor': 'nvidia|amd|intel|other', 'id': '10de:2503', 'name': '...'}]."""
    gpus, seen = [], set()
    for card in sorted(glob.glob(os.path.join(drm_root, "card*"))):
        if not re.fullmatch(r"card\d+", os.path.basename(card)):
            continue
        try:
            vid = open(os.path.join(card, "device", "vendor")).read().strip().lower()
            did = open(os.path.join(card, "device", "device")).read().strip().lower()
        except OSError:
            continue
        if (vid, did) not in seen:
            seen.add((vid, did))
            gpus.append({"vendor": GPU_VENDORS.get(vid, "other"), "id": "%s:%s" % (vid[2:], did[2:]), "name": ""})
    if lspci_text is None:
        try:
            lspci_text = subprocess.run(["lspci", "-nn"], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            lspci_text = ""
    for ln in lspci_text.splitlines():
        if not re.search(r"VGA compatible|3D controller|Display controller", ln):
            continue
        m = re.search(r"\[([0-9a-f]{4}:[0-9a-f]{4})\]", ln)
        name = re.sub(r"^\S+\s+.*?\[[0-9a-f]{4}\]:\s*", "", ln)
        name = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\].*$", "", name).strip()
        known = next((g for g in gpus if m and g["id"] == m.group(1)), None)
        if known:
            known["name"] = name
        elif m:
            gpus.append({"vendor": GPU_VENDORS.get("0x" + m.group(1)[:4], "other"), "id": m.group(1), "name": name})
    return gpus


def use_software_display(cfg, gpus=None):
    """Auto = the safer software display only when an NVIDIA card is present."""
    mode = cfg.get("android_display", "auto")
    if mode == "software":
        return True
    if mode == "hardware":
        return False
    return any(g["vendor"] == "nvidia" for g in (gpu_info() if gpus is None else gpus))


def waydroid_status():
    """Parse `waydroid status`: {'installed', 'initialized', 'session', 'container', 'ip', 'raw'}."""
    st = {"installed": (not IS_WIN) and shutil.which("waydroid") is not None, "initialized": False,
          "session": None, "container": None, "ip": None, "raw": ""}
    if not st["installed"]:
        return st
    try:
        r = subprocess.run(["waydroid", "status"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return st
    st["raw"] = ((r.stdout or "") + (r.stderr or "")).strip()
    for ln in st["raw"].splitlines():
        if ":" in ln:
            k, v = ln.split(":", 1)
            k, v = k.strip().lower(), v.strip()
            if k == "session":
                st["session"] = v.upper()
            elif k == "container":
                st["container"] = v.upper()
            elif k == "ip address":
                st["ip"] = v
    st["initialized"] = bool(st["session"] or st["container"])
    return st


def waydroid_problem(cfg):
    """Why Android can't start right now (text), or None if it looks ready."""
    if IS_WIN:
        return "Waydroid only works on Linux."
    st = waydroid_status()
    if not st["installed"]:
        return ("Waydroid isn't installed. On Linux Mint:\n  curl -fsSL https://repo.waydro.id | sudo bash\n"
                "  sudo apt install waydroid\n  sudo waydroid init")
    if not st["initialized"]:
        return "Waydroid isn't set up yet. Run:  sudo waydroid init"
    if st["container"] not in ("RUNNING", "FROZEN"):
        return "The Waydroid service isn't running. Run:  sudo systemctl enable --now waydroid-container"
    if not shutil.which("weston"):
        return "anTV needs the 'weston' display helper to show Android. Run:  sudo apt install weston"
    return None


def android_report(cfg):
    """Markup for the 'Android check' screen: what was found and what to do about it."""
    esc = GLib.markup_escape_text
    if IS_WIN:
        return "Waydroid (Android on this PC) only works on Linux.\nOn Windows, use the YouTube web card, FreeTube, or an Android TV box."
    gpus, st = gpu_info(), waydroid_status()
    rows = []

    def row(ok, label, detail=""):
        rows.append("%s  <b>%s</b>   %s" % ({True: "\u2714", False: "\u2716", None: "\u2022"}[ok], esc(label), esc(detail)))
    nv = any(g["vendor"] == "nvidia" for g in gpus)
    row(None, "Graphics card", "; ".join("%s [%s]" % (g["name"] or g["id"], g["vendor"].upper()) for g in gpus)
        or "couldn't detect (run  lspci | grep -i vga  to see it)")
    if use_software_display(cfg, gpus):
        row(None, "Android display", "software (safest). " + ("NVIDIA found, so video may be less smooth." if nv else ""))
    else:
        row(None, "Android display", "hardware accelerated" + ("" if gpus else " (card unknown; if it fails, choose Software in Settings)"))
    row(None, "Desktop session", os.environ.get("XDG_SESSION_TYPE") or ("X11" if os.environ.get("DISPLAY") else "unknown"))
    row(st["installed"], "Waydroid installed", "" if st["installed"] else "curl -fsSL https://repo.waydro.id | sudo bash;  sudo apt install waydroid")
    if st["installed"]:
        row(st["initialized"], "Waydroid set up", "" if st["initialized"] else "sudo waydroid init")
        row(st["container"] in ("RUNNING", "FROZEN"), "Waydroid service", st["container"] or "not running: sudo systemctl enable --now waydroid-container")
    row(bool(shutil.which("weston")), "Display helper (weston)", "" if shutil.which("weston") else "sudo apt install weston")
    row(True if shutil.which("wmctrl") else None, "Screen placement (wmctrl)",
        "" if shutil.which("wmctrl") else "optional, puts Android on the TV screen: sudo apt install wmctrl")
    binder = any(glob.glob("/dev/*binder*")) or ("binder" in open("/proc/filesystems").read() if os.path.exists("/proc/filesystems") else False)
    row(True if binder else None, "Kernel support (binder)", "" if binder else "not detected; Waydroid normally sets this up itself on Mint kernels")
    return "\n".join(rows)


def place_window(title, x, y, w, h, fullscreen=True):
    """Best effort: move a window to a screen area and make it fullscreen there (X11, needs wmctrl)."""
    if not shutil.which("wmctrl"):
        return False
    for _ in range(40):  # the window can take a moment to appear (slow window managers)
        try:
            if title in subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=5).stdout:
                subprocess.run(["wmctrl", "-r", title, "-e", "0,%d,%d,%d,%d" % (x, y, w, h)], timeout=5)
                if fullscreen:
                    time.sleep(0.4)
                    subprocess.run(["wmctrl", "-r", title, "-b", "add,fullscreen"], timeout=5)
                return True
        except (OSError, subprocess.TimeoutExpired):
            return False
        time.sleep(0.3)
    return False


class AndroidSession:
    """Waydroid's Android inside a nested weston window. weston is the compositor the Mint how-to uses on X11."""

    def __init__(self, cfg, log):
        self.cfg, self.log, self.comp, self.pgids = cfg, log, None, []

    @staticmethod
    def runtime_dir():
        return os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid()

    def env(self):
        e = dict(os.environ)
        e["WAYLAND_DISPLAY"], e["XDG_RUNTIME_DIR"] = WAYDROID_SOCKET, self.runtime_dir()
        return e

    def _spawn(self, cmd, env=None):
        p = subprocess.Popen(cmd, stdout=self.log, stderr=subprocess.STDOUT, env=env, **NEWGRP)
        self.pgids.append(p.pid)
        with open(STATE, "w") as f:  # lets the close-app hotkey stop everything, including the Android session
            json.dump({"pgids": self.pgids, "match": None, "stop_cmds": [["waydroid", "session", "stop"]]}, f)
        return p

    def _alive(self, cancel):
        if cancel is not None and cancel.is_set():
            raise InterruptedError
        if self.comp.poll() is not None:
            raise RuntimeError("The display window closed. See the log for details.")

    def start(self, geom, fullscreen=True, say=lambda t: None, cancel=None, timeout=120):
        x, y, w, h = geom
        sock = os.path.join(self.runtime_dir(), WAYDROID_SOCKET)
        for stale in (sock, sock + ".lock"):
            try:
                os.remove(stale)
            except OSError:
                pass
        cmd = ["weston", "--backend=" + ("x11" if os.environ.get("DISPLAY") else "wayland"), "--socket=" + WAYDROID_SOCKET,
               "--width=%d" % w, "--height=%d" % h, "--shell=kiosk"]
        if use_software_display(self.cfg):
            cmd.append("--use-pixman")
        self.comp = self._spawn(cmd)
        t0 = time.time()
        while not os.path.exists(sock):
            self._alive(cancel)
            if time.time() - t0 > 20:
                raise RuntimeError("The display helper (weston) didn't start.")
            time.sleep(0.2)
        place_window("Weston Compositor", x, y, w, h, fullscreen)
        self._spawn(["waydroid", "show-full-ui"], env=self.env())
        say("Starting Android\u2026 (the first start can take a minute)")
        t0 = time.time()
        while waydroid_status()["session"] != "RUNNING":
            self._alive(cancel)
            if time.time() - t0 > timeout:
                raise RuntimeError("Android didn't start in time.")
            time.sleep(1.5)

    def launch_app(self, pkg, cancel=None, timeout=45):
        t0, out = time.time(), ""
        while time.time() - t0 < timeout:
            self._alive(cancel)
            r = subprocess.run(["waydroid", "app", "launch", pkg], env=self.env(), capture_output=True, text=True,
                               timeout=30, **NOWIN)
            out = ((r.stdout or "") + (r.stderr or "")).strip()
            self.log.write(out + "\n"); self.log.flush()
            if r.returncode == 0:
                return True
            time.sleep(2)
        raise RuntimeError("Android is running but couldn't open %s.\n%s" % (pkg, out.splitlines()[-1] if out else ""))

    def wait(self):
        self.comp.wait()

    def stop(self):
        for force in (False, True):
            for pg in self.pgids:
                kill_tree(pg, force)
            if not force:
                time.sleep(0.5)
        try:
            subprocess.run(["waydroid", "session", "stop"], capture_output=True, timeout=25, **NOWIN)
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            os.remove(STATE)
        except OSError:
            pass


def waydroid_install_in_session(cfg, apk, geom):
    """Waydroid needs a running session to install into: start one in a small window, install, then stop it."""
    os.makedirs(os.path.join(CFG_DIR, "logs"), exist_ok=True)
    with open(os.path.join(CFG_DIR, "logs", "waydroid.log"), "w") as log:
        sess = AndroidSession(cfg, log)
        try:
            sess.start(geom, fullscreen=False)
            return waydroid_install(apk)
        finally:
            sess.stop()


def win_removable_drives():
    """[(root, label)] for removable drives (USB sticks) on Windows."""
    out = []
    if not IS_WIN:
        return out
    k = ctypes.windll.kernel32
    mask = k.GetLogicalDrives()
    for i in range(26):
        root = f"{chr(65 + i)}:\\"
        if mask & (1 << i) and k.GetDriveTypeW(root) == 2 and os.path.isdir(root):  # DRIVE_REMOVABLE
            buf = ctypes.create_unicode_buffer(261)
            k.GetVolumeInformationW(root, buf, 260, None, None, None, None, 0)
            out.append((root, buf.value or root))
    return out


def eject_drive(path):
    if IS_WIN:
        ps = ("(New-Object -comObject Shell.Application).Namespace(17).ParseName('%s').InvokeVerb('Eject')" % path[:2])
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], **NOWIN)
    else:
        subprocess.Popen(["gio", "mount", "-e", path])  # safe eject


def win_hotkey_loop():
    """Windows: Ctrl+Alt+K kills the running app (the Linux build uses a Cinnamon shortcut instead)."""
    if not _user32.RegisterHotKey(None, 1, 0x0002 | 0x0001 | 0x4000, ord("K")):
        return
    msg = wintypes.MSG()
    while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == 0x0312:  # WM_HOTKEY
            threading.Thread(target=kill_current, daemon=True).start()

POPULAR_LINKS = [  # (name, address, card color): shown in the Popular apps menu. Add more here.
    ("Tiedye Sasquatch", "https://yeti.tiedyesasquatch.online", "#7b3fe4"),
    ("FreeBirth", "https://freebirth.ai.studio", "#e8833a"),
]

DEFAULT = {
    "monitor": None,  # None = last monitor (usually the TV); F1 cycles
    "media_dirs": ["~/Videos", "~/Music", "~/Pictures"],
    "apps": [
        {"name": "Jellyfin", "type": "web", "url": "http://localhost:8096", "color": "#00a4dc"},
        {"name": "Plex", "type": "web", "url": "https://app.plex.tv", "color": "#e5a00d"},
        {"name": "Emby", "type": "web", "url": "http://localhost:8097", "color": "#52b54b"},
        {"name": "Netflix", "type": "web", "url": "https://www.netflix.com", "color": "#e50914"},
        {"name": "Hulu", "type": "web", "url": "https://www.hulu.com", "color": "#1ce783"},
        {"name": "Peacock", "type": "web", "url": "https://www.peacocktv.com", "color": "#6f4cff"},
        {"name": "Disney+", "type": "web", "url": "https://www.disneyplus.com", "color": "#113ccf"},
        {"name": "YouTube", "type": "web", "url": "https://www.youtube.com/tv", "color": "#ff0000"},
        {"name": "Kodi", "type": "cmd", "cmd": "kodi", "color": "#17b2e7"},
        {"name": "VLC", "type": "cmd", "cmd": "vlc --fullscreen", "color": "#ff8800"},
    ],
}


def load():
    try:
        with open(CFG) as f:
            return json.load(f)
    except Exception:
        return json.loads(json.dumps(DEFAULT))


def save(cfg):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(CFG, "w") as f:
        json.dump(cfg, f, indent=2)


REMOTE_DEFAULTS = {  # remote button -> likely X11 key names (Fire TV remotes pair as Bluetooth keyboards)
    "select": ["Return", "KP_Enter", "XF86Select"],
    "back": ["XF86Back"],
    "menu": ["Menu", "XF86MenuKB", "XF86Menu"],
    "playpause": ["XF86AudioPlay", "XF86AudioPause"],
    "home": [],  # global: close the running app and return to TV Hub (set up with Learn)
}
REMOTE_LABELS = {"select": "Select (center)", "back": "Back", "menu": "Menu (\u2261)",
                 "playpause": "Play / Pause", "home": "Home (close app, return to TV Hub)"}


def _canon_key(name):
    """GTK names XF86Back "Back" but we store "XF86Back", so compare key codes, not names."""
    v = Gdk.keyval_from_name(name) if name else 0
    return name if v in (0, 0xFFFFFF) else v


def remote_action(cfg, keyname):
    m = cfg.get("remote", {})
    k = _canon_key(keyname)
    for act, default in REMOTE_DEFAULTS.items():
        if keyname and any(_canon_key(n) == k for n in m.get(act, default)):
            return act
    return None


_tenft_css_done = False


def ensure_tenft_css():
    global _tenft_css_done
    if _tenft_css_done:
        return
    c = Gtk.CssProvider()
    c.load_from_data(b"""
.andark{background-color:#12151d;color:#ffffff;}
.andark label{color:#ffffff;font-size:16px;font-weight:700;}
.andark button{background-image:none;background-color:#2a3350;color:#ffffff;border:1px solid #4a5a8c;border-radius:8px;box-shadow:none;text-shadow:none;font-weight:700;padding:6px 14px;}
.andark button label{color:#ffffff;font-weight:700;}
.andark button:hover,.andark button:focus{background-color:#2a6df4;border-color:#8fb4ff;}
.andark button:disabled label{color:#8a93a8;}
.andark entry,.andark spinbutton,.andark spinbutton entry{background-image:none;background-color:#1b2030;color:#ffffff;border:1px solid #4a5a8c;font-weight:700;font-size:16px;box-shadow:none;}
.andark spinbutton button{border-radius:0;}
.andark check,.andark radio{background-image:none;background-color:#1b2030;border:2px solid #8fb4ff;color:#ffffff;box-shadow:none;}
.andark check:checked,.andark radio:checked{background-color:#2a6df4;}
.andark treeview{background-color:#171b26;color:#ffffff;font-weight:700;font-size:16px;}
.andark treeview:selected{background-color:#2a6df4;color:#ffffff;}
.andark treeview header button{background-color:#2a3350;color:#ffffff;border-radius:0;}
.andark notebook,.andark notebook stack{background-color:#12151d;}
.andark button label,.andark combobox label,.andark filechooserbutton label{font-size:16px;font-weight:700;}
.andark cellview,.andark combobox cellview{font-size:16px;font-weight:700;color:#ffffff;}
.andark notebook header{background-color:#0d1017;}
.andark notebook tab{background-color:#1b2030;color:#ffffff;padding:10px 24px;border:none;}
.andark notebook tab label{font-size:17px;font-weight:800;}
.andark notebook tab:checked{background-color:#2a6df4;}
.andark scrolledwindow,.andark viewport{background-color:transparent;}
.andark separator{background-color:#3d4a73;}
.tenft label{font-size:26px;}
.tenft button{min-height:64px;min-width:160px;padding:6px 24px;}
.tenft button label{font-size:26px;}
.tenft entry,.tenft spinbutton{min-height:60px;font-size:26px;}
.tenft combobox button{min-height:60px;}
.tenft checkbutton{min-height:56px;}
.tenft check,.tenft radio{min-width:34px;min-height:34px;}
.tenft treeview{font-size:28px;}
#tvs-win{background-color:#0b0d12;}
#tvs-title{color:#ffffff;font-size:56px;font-weight:800;}
#tvs-hint{color:#c3cde0;font-size:24px;font-weight:700;}
#tvs-dlg-title{color:#ffffff;font-size:34px;font-weight:800;}
#tvs-cats,#tvs-opts{background-color:transparent;}
#tvs-cats row,#tvs-opts row{background-color:#1b2132;color:#ffffff;padding:14px 22px;margin:5px 0;border-radius:14px;min-height:72px;border:2px solid #2e3a5c;}
#tvs-cats row label{color:#ffffff;font-size:34px;font-weight:800;}
#tvs-opts row label{color:#ffffff;font-size:32px;font-weight:700;}
#tvs-opts row label.val{color:#cfe3ff;font-weight:800;}
#tvs-cats row{padding:10px 22px;margin:3px 0;min-height:54px;}
#tvs-cats row label{font-size:31px;}
#tvs-cats row:selected,#tvs-opts row:selected{background-color:#2c3a66;border-color:#6ea0ff;}
#tvs-cats row:focus,#tvs-opts row:focus{background-color:#2a6df4;border-color:#ffffff;outline:none;}
#tvs-cats row.tvs-save{border-color:#2fbf71;}
#tvs-cats row.tvs-save label{color:#9ef0b8;}
#tvs-cats row.tvs-discard label{color:#ffb4b4;}
#tvs-save,#tvs-discard{background-image:none;background-color:#1b2132;border:2px solid #4a5a8c;border-radius:12px;box-shadow:none;padding:12px 40px;}
#tvs-save{background-color:#1f8f5a;border-color:#7ae2ac;}
#tvs-save label,#tvs-discard label{color:#ffffff;font-size:26px;font-weight:800;}
#tvs-save:hover,#tvs-save:focus{background-color:#27b36f;}
#tvs-discard:hover,#tvs-discard:focus{background-color:#2a6df4;}
""")
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), c, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _tenft_css_done = True


def tenft(dlg, cfg):
    """Dark, thick-text styling on every anTV dialog; plus huge targets when the 10-foot option is on."""
    ensure_tenft_css()
    ctx = dlg.get_style_context()
    ctx.add_class("andark")
    if cfg.get("tenft_settings"):
        ctx.add_class("tenft")


def hook_back(dlg, cfg):
    """Remote 'Back' cancels a dialog."""
    tenft(dlg, cfg)
    def on_key(_w, e):
        if remote_action(cfg, Gdk.keyval_name(e.keyval)) == "back":
            dlg.response(Gtk.ResponseType.CANCEL)
            return True
        return False
    dlg.connect("key-press-event", on_key)


def store_image(path):
    """Copy a chosen background image into the config folder so it survives unplugged drives."""
    d = os.path.join(CFG_DIR, "images")
    os.makedirs(d, exist_ok=True)
    if os.path.dirname(os.path.abspath(path)) == d:
        return path
    dst = os.path.join(d, f"{int(time.time() * 1000)}_{os.path.basename(path)}")
    shutil.copy2(path, dst)
    return dst


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BG_DIR = os.path.join(CFG_DIR, "backgrounds")  # the default backgrounds folder: drop your own pictures in here too
BG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def list_images(d):
    """Image files directly inside folder d, sorted by name."""
    try:
        names = sorted(os.listdir(d), key=str.lower)
    except OSError:
        return []
    return [os.path.join(d, n) for n in names
            if not n.startswith(".") and os.path.splitext(n)[1].lower() in BG_EXT and os.path.isfile(os.path.join(d, n))]


def seed_backgrounds():
    """Make sure the default backgrounds folder exists and holds the pictures shipped in the 'backgrounds' folder
    next to tvhub.py. Each shipped picture is copied once, so one you delete is not brought back."""
    try:
        os.makedirs(BG_DIR, exist_ok=True)
        mark = os.path.join(BG_DIR, ".seeded")
        try:
            with open(mark, encoding="utf-8") as f:
                done = set(json.load(f))
        except Exception:
            done = set()
        for p in list_images(os.path.join(SCRIPT_DIR, "backgrounds")):
            n = os.path.basename(p)
            if n not in done:
                dst = os.path.join(BG_DIR, n)
                if not os.path.exists(dst):
                    shutil.copy2(p, dst)
                done.add(n)
        with open(mark, "w", encoding="utf-8") as f:
            json.dump(sorted(done), f)
    except Exception:
        pass


def add_backgrounds(paths):
    """Copy pictures into the default backgrounds folder. Returns how many were added."""
    os.makedirs(BG_DIR, exist_ok=True)
    n = 0
    for p in paths:
        if os.path.splitext(p)[1].lower() not in BG_EXT or not os.path.isfile(p):
            continue
        base, ext = os.path.splitext(os.path.basename(p))
        dst, k = os.path.join(BG_DIR, base + ext), 2
        if os.path.abspath(p) == os.path.abspath(dst):
            continue
        while os.path.exists(dst):
            dst, k = os.path.join(BG_DIR, "%s_%d%s" % (base, k, ext)), k + 1
        shutil.copy2(p, dst)
        n += 1
    return n


def open_path(path):
    """Show a folder in the system file manager."""
    try:
        if IS_WIN:
            os.startfile(path)  # noqa
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **NEWGRP)
    except Exception:
        pass


BACKUP_DIRS = ("images", "backgrounds")  # saved in a backup next to config.json (browser logins are not)


def make_backup(dest_dir):
    """Zip the settings, card pictures and backgrounds into dest_dir. Returns the zip's path."""
    path = os.path.join(dest_dir, "anTV-backup-%s.zip" % time.strftime("%Y%m%d-%H%M%S"))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.isfile(CFG):
            z.write(CFG, "config.json")
        for d in BACKUP_DIRS:
            for root, _dirs, files in os.walk(os.path.join(CFG_DIR, d)):
                for f in files:
                    full = os.path.join(root, f)
                    z.write(full, os.path.relpath(full, CFG_DIR).replace(os.sep, "/"))
        z.writestr("backup-info.json", json.dumps({"app": "anTV", "version": VERSION, "cfg_dir": CFG_DIR}))
    return path


def restore_backup(path):
    """Replace settings, pictures and backgrounds with the ones in a backup zip. Returns the restored config.
    Picture paths saved on another computer or account are pointed at this one's config folder."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "config.json" not in names:
            raise ValueError("This isn't an anTV backup (there is no config.json inside).")
        cfg = json.loads(z.read("config.json").decode("utf-8"))
        info = json.loads(z.read("backup-info.json").decode("utf-8")) if "backup-info.json" in names else {}
        for d in BACKUP_DIRS:
            shutil.rmtree(os.path.join(CFG_DIR, d), ignore_errors=True)
        for n in names:
            parts = n.split("/")
            if n.endswith("/") or n.startswith("/") or ".." in parts or parts[0] not in BACKUP_DIRS:
                continue
            dst = os.path.join(CFG_DIR, *parts)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(z.read(n))
    old = info.get("cfg_dir")
    if old and old != CFG_DIR:
        def fix(v):
            if isinstance(v, str) and v.startswith(old) and v[len(old):len(old) + 1] in ("/", "\\"):
                return CFG_DIR + v[len(old):].replace("\\", "/").replace("/", os.sep)
            if isinstance(v, list):
                return [fix(x) for x in v]
            if isinstance(v, dict):
                return {k: fix(x) for k, x in v.items()}
            return v
        cfg = fix(cfg)
    save(cfg)
    return cfg


def wipe_data():
    """Delete settings, card pictures, backgrounds, browser profiles (logins) and logs."""
    for n in ("images", "backgrounds", "profiles", "logs"):
        shutil.rmtree(os.path.join(CFG_DIR, n), ignore_errors=True)
    try:
        os.remove(CFG)
    except OSError:
        pass


# ---- updates: from a GitHub repository (latest release, or a branch) or from a file you pick ----
UPDATE_DIR = os.path.join(CFG_DIR, "updates")        # backups of replaced versions, state.json, pending.json
UPDATE_MARK = os.path.join(UPDATE_DIR, "pending.json")  # exists from an install until the new version has run fine
UPDATE_STATE = os.path.join(UPDATE_DIR, "state.json")
UPDATE_REPO_DEFAULT = "tdsas27/tvhub-anTV"           # used until Settings > Updates sets (or clears) a repository
UPDATE_MODES = ["off", "ask", "auto"]                # Settings: never / check and tell me / install automatically
UPDATE_EVERY = 12 * 3600                             # seconds between automatic checks
UPDATE_KEEP = 5                                      # old versions kept for "go back"
UPDATE_MAX = 100 * 1024 * 1024
UPDATE_TOP = ("Setup-TVHub.ps1", "Setup-TVHub.bat")  # besides tvhub.py, *.md next to it, and these folders:
UPDATE_DIRS = ("tasks", "backgrounds")
SELF_PATH = os.path.abspath(__file__)
RESTART = {"want": False}


class UpdateError(ValueError):
    pass


def ver_tuple(v):
    """'0.26.1' / 'v0.26.1-beta' -> (0, 26, 1, 0). Empty tuple if there are no digits."""
    nums = [int(x) for x in re.findall(r"\d+", str(v or "").split("-")[0])[:4]]
    return tuple(nums + [0] * (4 - len(nums))) if nums else ()


def update_repo(cfg):
    """The repository to update from: the saved one (empty = none), else the built-in default."""
    return cfg.get("update_repo", UPDATE_REPO_DEFAULT)


def parse_repo(text):
    """'owner/repo', 'owner/repo@branch' or a github.com URL (also .../tree/branch) -> (owner, repo, branch or None)."""
    t = re.sub(r"^https?://(www\.)?github\.com/", "", (text or "").strip()).strip("/")
    m = re.match(r"^([\w.-]+)/([\w.-]+)/tree/(.+)$", t)
    if m:
        owner, repo, branch = m.groups()
    else:
        branch = None
        if "@" in t:
            t, branch = t.split("@", 1)
        m = re.match(r"^([\w.-]+)/([\w.-]+)$", t)
        if not m:
            return None
        owner, repo = m.groups()
    repo = re.sub(r"\.git$", "", repo)
    return (owner, repo, (branch or "").strip() or None) if owner and repo else None


def http_get(url, limit=UPDATE_MAX, first=None):
    """Download a URL (https). first=N reads only the first N bytes. Raises UpdateError with a plain message."""
    req = urllib.request.Request(url, headers={"User-Agent": "anTV-updater", "Accept": "application/vnd.github+json, */*"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read(first) if first else r.read(limit + 1)
    except urllib.error.HTTPError as e:
        raise UpdateError({403: "GitHub is limiting requests right now (or the repository is private). Try again later.",
                           404: "Not found on GitHub. Check the repository name (private repositories can't be used)."}
                          .get(e.code, "GitHub answered HTTP %d." % e.code)) from None
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError("Couldn't reach GitHub. Is this PC online? (%s)" % getattr(e, "reason", e)) from None
    if not first and len(data) > limit:
        raise UpdateError("The download is too big to be an anTV update.")
    return data


def source_version(data):
    m = re.search(rb'^VERSION\s*=\s*"([^"]+)"', data, re.M)
    return m.group(1).decode() if m else None


def check_source(data):
    """Is this a whole, readable anTV tvhub.py? Returns its version or raises UpdateError."""
    try:
        text = data.decode("utf-8")
        ast.parse(text)
    except (UnicodeDecodeError, SyntaxError, ValueError):
        raise UpdateError("That isn't a working tvhub.py (it can't be read as Python).") from None
    v = source_version(data)
    if not v or "class Hub" not in text:
        raise UpdateError("That file isn't anTV's tvhub.py (no version number or main screen inside).")
    return v


def github_check(repo_text):
    """Ask GitHub what the newest version is. Returns {version (may be None), url, notes, source}."""
    p = parse_repo(repo_text)
    if not p:
        raise UpdateError("Write the GitHub repository as owner/name, for example myname/antv "
                          "(add @branch to follow a branch instead of releases).")
    owner, repo, branch = p
    base = "https://api.github.com/repos/%s/%s" % (owner, repo)
    if not branch:
        try:
            rel = json.loads(http_get(base + "/releases/latest", limit=4_000_000).decode("utf-8"))
        except UpdateError as e:
            if "Not found" not in str(e):
                raise
            rel = None  # no releases yet: follow the default branch instead
        if rel:
            tag = str(rel.get("tag_name") or "")
            assets = [a for a in rel.get("assets") or [] if a.get("browser_download_url")]
            pick = (next((a for a in assets if a["name"].lower().endswith(".zip") and re.search(r"tvhub|antv", a["name"], re.I)), None)
                    or next((a for a in assets if a["name"].lower() == "tvhub.py"), None))
            url = pick["browser_download_url"] if pick else rel.get("zipball_url")
            if not url:
                raise UpdateError("The latest release has nothing to download.")
            return {"version": tag.lstrip("vV") if ver_tuple(tag) else None, "url": url,
                    "notes": str(rel.get("body") or "").strip()[:700], "source": "GitHub release %s" % (tag or "?")}
        try:
            branch = json.loads(http_get(base, limit=2_000_000).decode("utf-8")).get("default_branch") or "main"
        except ValueError:
            branch = "main"
    q = urllib.parse.quote(branch, safe="/")
    head = http_get("https://raw.githubusercontent.com/%s/%s/%s/tvhub.py" % (owner, repo, q), first=12000)
    v = source_version(head)
    if not v:
        raise UpdateError("tvhub.py wasn't found at the top of branch %s of %s/%s." % (branch, owner, repo))
    return {"version": v, "url": "https://github.com/%s/%s/archive/refs/heads/%s.zip" % (owner, repo, q),
            "notes": "", "source": "GitHub branch %s" % branch}


def read_package(data):
    """data = bytes of a tvhub.py or of a zip (the all-files zip, or a GitHub zip with one folder around it).
    Returns {"version", "files": {relative path: bytes}}; only tvhub.py, the setup scripts, *.md, tasks/ and
    backgrounds/ are taken, with unsafe paths ignored."""
    if data[:2] != b"PK":
        return {"version": check_source(data), "files": {"tvhub.py": data}}
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        infos = [i for i in z.infolist() if not i.is_dir()]
    except zipfile.BadZipFile:
        raise UpdateError("That file isn't a valid zip.") from None
    norm = lambda i: i.filename.replace("\\", "/")
    found = [i for i in infos if norm(i).split("/")[-1] == "tvhub.py" and "__MACOSX" not in norm(i)]
    if not found:
        raise UpdateError("There is no tvhub.py inside that zip.")
    top = min(found, key=lambda i: norm(i).count("/"))
    prefix, files, total = norm(top)[:-len("tvhub.py")], {}, 0
    for i in infos:
        n = norm(i)
        if not n.startswith(prefix):
            continue
        rel = n[len(prefix):]
        parts = rel.split("/")
        if not rel or ".." in parts or ":" in parts[0] or parts[-1] in ("", "data.json") or "node_modules" in parts:
            continue
        if not (rel == "tvhub.py" or rel in UPDATE_TOP or (len(parts) == 1 and rel.lower().endswith(".md"))
                or (len(parts) > 1 and parts[0] in UPDATE_DIRS)):
            continue
        total += i.file_size
        if total > UPDATE_MAX or i.file_size > UPDATE_MAX // 3:
            raise UpdateError("That zip is too big to be an anTV update.")
        files[rel] = z.read(i)
    return {"version": check_source(files["tvhub.py"]), "files": files}


def console_python():
    """A python that can print (pythonw.exe on Windows can't), for the start-up test of a new version."""
    exe = sys.executable
    if IS_WIN and os.path.basename(exe).lower() == "pythonw.exe":
        c = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(c):
            return c
    return exe


def list_backups():
    return sorted(glob.glob(os.path.join(UPDATE_DIR, "tvhub-*_*.py")), key=lambda p: os.path.basename(p).split("_", 1)[1])


def backup_version(path):
    return os.path.basename(path)[len("tvhub-"):].split("_")[0]


def update_state():
    try:
        with open(UPDATE_STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def update_state_set(**kw):
    try:
        os.makedirs(UPDATE_DIR, exist_ok=True)
        st = update_state(); st.update(kw)
        with open(UPDATE_STATE, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except OSError:
        pass


def install_package(pkg):
    """Test the new tvhub.py by starting it, keep the running one as a backup, write the files (tvhub.py last),
    and leave a marker until the new version has run fine. Returns a summary. Nothing changes if the test fails."""
    files, new_v, root = pkg["files"], pkg["version"], os.path.dirname(SELF_PATH)
    if not (os.access(root, os.W_OK) and os.access(SELF_PATH, os.W_OK)):
        raise UpdateError("anTV's own folder (%s) can't be written to, so it can't be updated there." % root)
    tmp = SELF_PATH + ".new"
    try:
        with open(tmp, "wb") as f:
            f.write(files["tvhub.py"])
        try:
            out = subprocess.run([console_python(), tmp, "--version"], capture_output=True, text=True, timeout=60, **NOWIN)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise UpdateError("Couldn't test the new version (%s), so nothing was changed." % e) from None
        if out.returncode != 0 or ("anTV " + new_v) not in out.stdout:
            raise UpdateError("The new version didn't start properly, so nothing was changed.\n\n%s"
                              % ((out.stderr or out.stdout).strip()[-300:] or "(no message)"))
        os.makedirs(UPDATE_DIR, exist_ok=True)
        bk = os.path.join(UPDATE_DIR, "tvhub-%s_%s.py" % (VERSION, time.strftime("%Y%m%d-%H%M%S")))
        shutil.copyfile(SELF_PATH, bk)
        for old in list_backups()[:-UPDATE_KEEP]:
            try:
                os.remove(old)
            except OSError:
                pass
        extra, skipped = 0, []
        for rel, data in files.items():
            if rel == "tvhub.py":
                continue
            dst = os.path.join(root, *rel.split("/"))
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst + ".tmp", "wb") as f:
                    f.write(data)
                os.replace(dst + ".tmp", dst)
                extra += 1
            except OSError:
                skipped.append(rel)
        os.replace(tmp, SELF_PATH)
        with open(UPDATE_MARK, "w", encoding="utf-8") as f:
            json.dump({"from": VERSION, "to": new_v, "backup": bk, "boots": 0}, f)
        return {"from": VERSION, "to": new_v, "extra": extra, "skipped": skipped, "backup": bk}
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def update_confirm():
    """The new version ran fine: forget the rollback marker."""
    try:
        os.remove(UPDATE_MARK)
    except OSError:
        pass


def rollback_update(path=None):
    """Put the newest saved older tvhub.py back (or the one given). Returns its version."""
    bks = list_backups()
    path = path or (bks[-1] if bks else None)
    if not path or not os.path.isfile(path):
        raise UpdateError("There is no earlier version saved yet. One is saved each time anTV updates itself.")
    with open(path, "rb") as f:
        data = f.read()
    v = check_source(data)
    tmp = SELF_PATH + ".old"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, SELF_PATH)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    try:
        os.remove(path)  # so going back again goes one version further back
    except OSError:
        pass
    update_confirm()
    return v


def update_boot_guard():
    """At start-up: a just-installed version that has now started 3 times without running fine is replaced by the
    saved old one. True if that happened (the caller then restarts)."""
    try:
        with open(UPDATE_MARK, encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        return False
    m["boots"] = int(m.get("boots", 0)) + 1
    if m["boots"] >= 3:
        try:
            rollback_update(m.get("backup"))
        except Exception:
            update_confirm()
        return True
    try:
        with open(UPDATE_MARK, "w", encoding="utf-8") as f:
            json.dump(m, f)
    except OSError:
        pass
    return False


def update_failed_start():
    """The main window could not even be built right after an update: go back. True if it did."""
    try:
        with open(UPDATE_MARK, encoding="utf-8") as f:
            m = json.load(f)
        rollback_update(m.get("backup"))
        return True
    except Exception:
        return False


def spawn_self():
    """Start anTV again in 2 seconds (after this process has let go of its ports)."""
    code = "import sys,time,subprocess;time.sleep(2);subprocess.Popen(sys.argv[1:]%s)" % (
        ", creationflags=0x08000000" if IS_WIN else ", start_new_session=True")
    subprocess.Popen([sys.executable, "-c", code, sys.executable, SELF_PATH] + sys.argv[1:], close_fds=True, **NEWGRP)


def choose_path(parent, cfg, title, folder=False, pattern=None):
    """File or folder chooser. Returns the path or None."""
    dlg = Gtk.FileChooserDialog(title=title, transient_for=parent,
                                action=Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN)
    dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Choose", Gtk.ResponseType.OK)
    hook_back(dlg, cfg)
    if pattern:
        flt = Gtk.FileFilter(); flt.set_name(pattern); flt.add_pattern(pattern); dlg.add_filter(flt)
    dlg.set_default_size(1200, 800)
    r = dlg.run(); path = dlg.get_filename() if r == Gtk.ResponseType.OK else None
    dlg.destroy()
    return path


def find_browser():
    inst = installed_browsers()
    for _name, b, fam in inst:
        if fam == "chromium":
            return b, True
    return (inst[0][1], False) if inst else (None, False)


STATE = os.path.join(CFG_DIR, "current.json")


KILLED = STATE + ".killed"


def kill_current():
    """Kill the running app's whole process tree plus any process using its browser profile."""
    try:
        with open(STATE) as f:
            st = json.load(f)
    except Exception:
        return False
    open(KILLED, "w").close()  # tells the Node.js launcher this was a deliberate stop, not a crash
    for force in (False, True):
        for pg in st.get("pgids") or [st["pgid"]]:
            kill_tree(pg, force)
        if force or not IS_WIN:
            kill_match(st.get("match"), force)
        if not force:
            time.sleep(1.5)
    for cmd in st.get("stop_cmds") or []:
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25, **NOWIN)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        os.remove(STATE)
    except OSError:
        pass
    return True


BROWSERS = [  # (name, executables / Windows install paths, family)
    ("Firefox", ["firefox", r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
                 r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"], "firefox"),
    ("Google Chrome", ["google-chrome-stable", "google-chrome", r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                       r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                       r"%LocalAppData%\Google\Chrome\Application\chrome.exe"], "chromium"),
    ("Chromium", ["chromium", "chromium-browser", r"%LocalAppData%\Chromium\Application\chrome.exe"], "chromium"),
    ("Brave", ["brave-browser", "brave", r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
               r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"], "chromium"),
    ("Vivaldi", ["vivaldi-stable", "vivaldi", r"%LocalAppData%\Vivaldi\Application\vivaldi.exe",
                 r"%ProgramFiles%\Vivaldi\Application\vivaldi.exe"], "chromium"),
    ("Microsoft Edge", ["microsoft-edge-stable", "microsoft-edge",
                        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
                        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"], "chromium"),
    ("Opera", ["opera", r"%LocalAppData%\Programs\Opera\opera.exe", r"%ProgramFiles%\Opera\opera.exe"], "chromium"),
    ("LibreWolf", ["librewolf", r"%ProgramFiles%\LibreWolf\librewolf.exe"], "firefox"),
]


def installed_browsers():
    out = []
    for name, bins, fam in BROWSERS:
        b = next((r for r in (exe_path(x) for x in bins) if r), None)
        if b:
            out.append((name, b, fam))
    return out


VIDEO = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".webm", ".ts", ".mpg", ".mpeg", ".flv"}
AUDIO = {".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aac", ".wma"}
IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
GLYPH = {"dir": "\u25b8", "video": "\u25b6", "audio": "\u266a", "image": "\u25a3"}
_css_done = False


def kind_of(name):
    e = os.path.splitext(name)[1].lower()
    return "video" if e in VIDEO else "audio" if e in AUDIO else "image" if e in IMAGE else None


def player_cmd(files, screen):
    mpv = exe_path("mpv") or exe_path(r"%ProgramFiles%\mpv\mpv.exe")
    if mpv:
        return [mpv, "--fullscreen", f"--fs-screen={screen}", f"--screen={screen}", "--force-window=yes",
                "--no-terminal", "--image-display-duration=inf", *files]
    vlc = exe_path("vlc") or next((r for r in (exe_path(x) for x in WIN_ALIASES["vlc"]) if r), None)
    if vlc:
        return [vlc, "--fullscreen", f"--qt-fullscreen-screennumber={screen}", "--play-and-exit", *files]
    return None


class Browser(Gtk.Window):
    """Fullscreen file browser for local folders / USB drives. Plays with mpv (or VLC)."""

    def __init__(self, hub, roots):
        global _css_done
        super().__init__(title="Media")
        self.hub, self.roots = hub, roots
        self.path = roots[0] if len(roots) == 1 else None
        hub.browser = self
        self.set_decorated(False); self.set_transient_for(hub)
        self.connect("key-press-event", self.on_key)
        if not _css_done:
            c = Gtk.CssProvider()
            c.load_from_data(b"#bhead{color:white;font-size:34px;font-weight:bold;}"
                             b"#bhint{color:#7d8590;font-size:20px;}"
                             b"#blist{background:#0b0d12;color:white;font-size:30px;}"
                             b"#blist:selected{background:#2a6df4;color:white;}")
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), c, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            _css_done = True
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16); box.set_border_width(60)
        self.head = Gtk.Label(xalign=0); self.head.set_name("bhead")
        hint = Gtk.Label(label="Enter: open / play   Backspace or Esc: back   P: play whole folder",
                         xalign=0); hint.set_name("bhint")
        self.store = Gtk.ListStore(str, str, str)
        self.tree = Gtk.TreeView(model=self.store); self.tree.set_name("blist")
        self.tree.set_headers_visible(False); self.tree.set_enable_search(False)
        self.tree.append_column(Gtk.TreeViewColumn("", Gtk.CellRendererText(ypad=10), text=0))
        self.tree.connect("row-activated", lambda *a: self.activate_row())
        sc = Gtk.ScrolledWindow(); sc.add(self.tree); sc.set_vexpand(True)
        for w in (self.head, hint):
            box.pack_start(w, False, False, 0)
        box.pack_start(sc, True, True, 0)
        self.add(box)
        self.refresh(); self.show_all()
        self.fullscreen_on_monitor(Gdk.Screen.get_default(), hub.mon_idx)
        self.tree.grab_focus()

    def refresh(self, select=None):
        self.store.clear()
        if self.path is None:
            self.head.set_text("Local media")
            rows = [(f"{GLYPH['dir']} {os.path.basename(r.rstrip('/')) or r}", r, "dir") for r in self.roots]
        else:
            self.head.set_text(self.path)
            try:
                names = sorted((n for n in os.listdir(self.path) if not n.startswith(".")), key=str.lower)
            except OSError:
                names = []
            full = lambda n: os.path.join(self.path, n)
            rows = [(f"{GLYPH['dir']} {n}", full(n), "dir") for n in names if os.path.isdir(full(n))]
            rows += [(f"{GLYPH[kind_of(n)]} {n}", full(n), kind_of(n))
                     for n in names if kind_of(n) and os.path.isfile(full(n))]
        for r in rows:
            self.store.append(list(r))
        if not rows:
            self.store.append(["(no media here)", "", "none"])
        idx = next((i for i, r in enumerate(rows) if r[1] == select), 0)
        self.tree.set_cursor(Gtk.TreePath(idx))

    def current(self):
        m, it = self.tree.get_selection().get_selected()
        return tuple(m[it]) if it else None

    def on_key(self, _w, e):
        k = Gdk.keyval_name(e.keyval)
        act = remote_action(self.hub.cfg, k)
        if act == "back":
            self.up(); return True
        if act in ("select", "playpause"):
            self.activate_row(); return True
        if act == "menu":
            self.play(None); return True  # Menu = play the whole folder
        if k in ("Escape", "BackSpace", "Left"):
            self.up()
        elif k in ("Return", "KP_Enter", "Right"):
            self.activate_row()
        elif k in ("p", "P"):
            self.play(None)
        elif k in ("q", "Q"):
            self.close_win()
        else:
            return False
        return True

    def up(self):
        old = self.path
        if old is None or (old in self.roots and len(self.roots) == 1):
            return self.close_win()
        self.path = None if old in self.roots else os.path.dirname(old)
        self.refresh(select=old)

    def close_win(self):
        self.hub.browser = None
        self.destroy()
        self.hub.present()

    def activate_row(self):
        row = self.current()
        if not row:
            return
        if row[2] == "dir":
            self.path = row[1]; self.refresh()
        elif row[2] in ("video", "audio", "image"):
            self.play(row[1])

    def play(self, start):
        files = [r[1] for r in self.store if r[2] in ("video", "audio", "image")]
        if not files:
            return
        i = files.index(start) if start in files else 0
        cmd = player_cmd(files[i:] + files[:i], self.hub.mon_idx)
        if not cmd:
            m = Gtk.MessageDialog(transient_for=self, message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.OK,
                                  text="No media player found. Install VLC or mpv (Linux: sudo apt install mpv)")
            m.run(); m.destroy(); return
        self.hub.run_cmd(cmd, None, self)


GAMEPAD_DEFAULTS = {  # action -> inputs. "b0" = button 0, "a6-" = axis 6 negative. Layout of the Linux xpad driver.
    "up": ["a7-", "a1-"], "down": ["a7+", "a1+"], "left": ["a6-", "a0-"], "right": ["a6+", "a0+"],
    "select": ["b0"], "back": ["b1"], "playpause": ["b2"], "menu": ["b7"], "home": ["b8"],
}
GAMEPAD_LABELS = {"up": "Up (D-pad / left stick)", "down": "Down", "left": "Left", "right": "Right",
                  "select": "Select (usually A)", "back": "Back (usually B)",
                  "playpause": "Play / Pause (usually X)", "menu": "Menu (usually Start)",
                  "home": "Close app (usually Xbox button)"}
DIR_KEYS = {"up": "Up", "down": "Down", "left": "Left", "right": "Right"}


def gp_map(cfg):
    m = cfg.get("gamepad", {})
    return {a: m.get(a, d) for a, d in GAMEPAD_DEFAULTS.items()}


class Gamepad(threading.Thread):
    """Reads Xbox (and other) controllers from /dev/input/js* with no extra packages; hot-plug aware.
    Actions are turned into key presses for the TV Hub window in front, so every screen works unchanged."""
    ON, OFF = 18000, 12000

    def __init__(self, hub):
        super().__init__(daemon=True)
        self.hub = hub
        self.fds, self.active, self.repeat = {}, set(), {}
        self.learn_cb = self.watch = self.error = None

    def status(self):
        if self.fds:
            return "Controller connected: " + ", ".join(n or p for p, n in self.fds.values())
        return self.error or "No controller found. Plug it in by USB or pair it in Bluetooth settings."

    def drop(self, fd):
        try:
            os.close(fd)
        except OSError:
            pass
        self.fds.pop(fd, None)
        self.active.clear(); self.repeat.clear()

    def scan(self):
        paths = set(glob.glob("/dev/input/js*"))
        for fd, (p, _n) in list(self.fds.items()):
            if p not in paths:
                self.drop(fd)
        have = {p for p, _n in self.fds.values()}
        for p in paths - have:
            try:
                fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
            except PermissionError:
                self.error = "No permission to read controllers. Run: sudo usermod -aG input $USER  (then log out and in)"
                continue
            except OSError:
                continue
            name = ""
            try:
                buf = bytearray(128)
                fcntl.ioctl(fd, 0x80806A13, buf)  # JSIOCGNAME(128)
                name = bytes(buf).split(b"\0")[0].decode(errors="replace")
            except OSError:
                pass
            self.fds[fd] = (p, name); self.error = None

    def run(self):
        last_scan = 0.0
        while True:
            now = time.monotonic()
            if now - last_scan > 2:
                self.scan(); last_scan = now
            if self.fds:
                try:
                    ready, _, _ = select.select(list(self.fds), [], [], 0.05)
                except (OSError, ValueError):
                    ready = []
                for fd in ready:
                    self.read(fd)
                for spec, t in list(self.repeat.items()):  # hold a direction to keep moving
                    if time.monotonic() >= t:
                        self.repeat[spec] = time.monotonic() + 0.12
                        self.fire(spec)
            else:
                time.sleep(0.5)

    def read(self, fd):
        try:
            data = os.read(fd, 8 * 64)
        except BlockingIOError:
            return
        except OSError:
            return self.drop(fd)
        if not data:
            return self.drop(fd)
        for _ts, value, typ, num in struct.iter_unpack("<IhBB", data[: len(data) // 8 * 8]):
            if typ & 0x80:  # synthetic initial-state events
                continue
            self.handle(typ, num, value)

    def handle(self, typ, num, value):
        if typ == 1:
            self.press(f"b{num}") if value else self.release(f"b{num}")
        elif typ == 2:
            for sign, ch in ((1, "+"), (-1, "-")):
                if num in (2, 5) and ch == "-":  # triggers rest at their negative extreme
                    continue
                spec, v = f"a{num}{ch}", value * sign
                if v > self.ON:
                    self.press(spec)
                elif v < self.OFF:
                    self.release(spec)

    def press(self, spec):
        if spec in self.active:
            return
        self.active.add(spec)
        self.fire(spec)
        if any(spec in gp_map(self.hub.cfg)[a] for a in DIR_KEYS):
            self.repeat[spec] = time.monotonic() + 0.45

    def release(self, spec):
        self.active.discard(spec); self.repeat.pop(spec, None)

    def fire(self, spec):
        if self.watch:
            GLib.idle_add(self.watch, spec)
        if self.learn_cb:
            GLib.idle_add(self.learn_cb, spec)
            return
        for act, specs in gp_map(self.hub.cfg).items():
            if spec in specs:
                if act == "home":  # works even while another app is running
                    threading.Thread(target=kill_current, daemon=True).start()
                else:
                    GLib.idle_add(self.hub.gamepad_action, act)


if IS_WIN:
    class _XPad(ctypes.Structure):
        _fields_ = [("buttons", ctypes.c_ushort), ("lt", ctypes.c_ubyte), ("rt", ctypes.c_ubyte),
                    ("lx", ctypes.c_short), ("ly", ctypes.c_short), ("rx", ctypes.c_short), ("ry", ctypes.c_short)]

    class _XState(ctypes.Structure):
        _fields_ = [("packet", ctypes.c_ulong), ("pad", _XPad)]


class XInputPad(Gamepad):
    """Xbox controllers on Windows via XInput (built in; no drivers). Emits the same inputs as the Linux xpad layout
    so the mapping, Learn screen and repeat logic are shared."""
    BITS = {0x1000: "b0", 0x2000: "b1", 0x4000: "b2", 0x8000: "b3", 0x0100: "b4", 0x0200: "b5", 0x0020: "b6",
            0x0010: "b7", 0x0400: "b8", 0x0040: "b9", 0x0080: "b10",
            0x0001: "a7-", 0x0002: "a7+", 0x0004: "a6-", 0x0008: "a6+"}

    def __init__(self, hub):
        super().__init__(hub)
        self.slot, self.get = None, None
        for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                dll = ctypes.WinDLL(name)
            except OSError:
                continue
            try:
                self.get = dll[100]  # XInputGetStateEx: also reports the Xbox/Guide button
            except (AttributeError, OSError):
                self.get = dll.XInputGetState
            self.get.argtypes = [ctypes.c_ulong, ctypes.POINTER(_XState)]
            self.get.restype = ctypes.c_ulong
            break

    def status(self):
        if not self.get:
            return "XInput isn't available on this version of Windows."
        if self.slot is None:
            return "No Xbox controller found. Plug it in by USB, or pair it in Windows Bluetooth settings."
        return f"Xbox controller connected (player {self.slot + 1})"

    def run(self):
        if not self.get:
            return
        st, last_scan = _XState(), 0.0
        while True:
            now = time.monotonic()
            if self.slot is None:
                if now - last_scan > 2:  # polling empty slots is slow, so only now and then
                    last_scan = now
                    for i in range(4):
                        if self.get(i, ctypes.byref(st)) == 0:
                            self.slot = i
                            break
                time.sleep(0.25)
                continue
            if self.get(self.slot, ctypes.byref(st)) != 0:  # unplugged
                self.slot = None
                self.active.clear(); self.repeat.clear()
                continue
            pad = st.pad
            cur = {spec for bit, spec in self.BITS.items() if pad.buttons & bit}
            for spec, v in (("a0+", pad.lx), ("a0-", -pad.lx), ("a1-", pad.ly), ("a1+", -pad.ly)):
                if v > (self.OFF if spec in self.active else self.ON):
                    cur.add(spec)
            for spec in cur - self.active:
                self.press(spec)
            for spec in self.active - cur:
                self.release(spec)
            for spec, t in list(self.repeat.items()):
                if time.monotonic() >= t:
                    self.repeat[spec] = time.monotonic() + 0.12
                    self.fire(spec)
            time.sleep(0.016)


PAGE = r"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>TV Hub Remote</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}[hidden]{display:none!important}
html,body{height:100%;margin:0;overflow:hidden;overscroll-behavior:none}
body{background:#0b0d12;color:#fff;font:16px system-ui,sans-serif}
#main{height:100vh;height:100dvh;display:flex;flex-direction:column;padding:10px 12px 0;padding-top:calc(10px + env(safe-area-inset-top))}
#top{display:flex;align-items:baseline;gap:10px;flex:none;margin-bottom:8px}h1{font-size:18px;margin:0}#st{color:#7d8590;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.panel{flex:1;min-height:0;display:none;flex-direction:column;gap:8px;padding-bottom:8px}.panel.on{display:flex}
button{background:#222733;color:#fff;border:0;border-radius:14px;font-size:17px;padding:6px 4px;touch-action:manipulation;user-select:none;min-height:0}
button:active{background:#2a6df4}.grid{display:grid;gap:8px}.g3{grid-template-columns:repeat(3,1fr)}.g4{grid-template-columns:repeat(4,1fr)}
.rows{flex:none;height:clamp(44px,7.5dvh,64px)}.fill{flex:1;min-height:0;grid-template-rows:repeat(3,minmax(0,1fr))}
.big{font-size:24px}.ok{background:#2a6df4}.danger{background:#7a1f2b}
input{width:100%;padding:14px;border-radius:12px;border:1px solid #333a4a;background:#151922;color:#fff;font-size:18px}
#tabs{flex:none;display:grid;grid-template-columns:repeat(4,1fr);gap:6px;padding:8px 0;padding-bottom:calc(8px + env(safe-area-inset-bottom));border-top:1px solid #222733}
#tabs button{background:#151922;color:#9aa4b2;font-size:14px;font-weight:600;padding:10px 2px;border-radius:12px}#tabs button.on{background:#2a6df4;color:#fff}
#apps{flex:1;min-height:0}#apps button{color:#fff;font-weight:600;padding:4px;overflow:hidden;overflow-wrap:anywhere}
#login{max-width:340px;margin:12vh auto 0;padding:0 16px}#login .ok{width:100%;padding:18px;font-size:22px}
#pad{flex:1;min-height:0;border-radius:16px;background:#151922;border:1px solid #333a4a;display:flex;align-items:center;justify-content:center;text-align:center;color:#7d8590;touch-action:none;user-select:none;-webkit-user-select:none;padding:10px;line-height:1.5}#hold.on{background:#2a6df4}
</style></head><body>
<div id="login" hidden><h1>TV Hub Remote</h1><p style="color:#7d8590">Enter the PIN shown on your TV (Settings &gt; Phone remote).</p>
<input id="pin" inputmode="numeric" autocomplete="off" placeholder="PIN" style="margin-bottom:10px"><button class="ok" id="go">Connect</button><p id="err" style="color:#ff7b8a"></p></div>
<div id="main" hidden><div id="top"><h1>TV Hub Remote</h1><div id="st"></div></div>
<div class="panel on" id="p-dpad">
<div class="grid g3 fill"><span></span><button class="big" data-k="up">&#9650;</button><span></span>
<button class="big" data-k="left">&#9664;</button><button class="big ok" data-k="select">OK</button><button class="big" data-k="right">&#9654;</button>
<span></span><button class="big" data-k="down">&#9660;</button><span></span></div>
<div class="grid g4 rows"><button data-k="back">Back</button><button data-k="escape">Esc</button><button data-k="playpause">&#9199; Play</button><button data-k="menu">Menu</button></div>
<div class="grid g3 rows"><button data-v="down">Vol &minus;</button><button data-v="mute">Mute</button><button data-v="up">Vol +</button></div>
<button class="danger rows" data-k="home">Close app / Home</button></div>
<div class="panel" id="p-pad">
<div id="pad">Drag to move the cursor &middot; tap = click<br>Two fingers: tap = right click, drag = scroll<br>Press and hold, then drag = drag and drop</div>
<div class="grid g3 rows"><button data-m="left">Left click</button><button data-m="double">Double click</button><button data-m="right">Right click</button></div>
<div class="grid g3 rows"><button data-s="-1">Scroll &uarr;</button><button id="hold">Hold</button><button data-s="1">Scroll &darr;</button></div></div>
<div class="panel" id="p-type"><input id="txt" placeholder="Text to type into the TV&hellip;" autocomplete="off">
<div class="grid g3 rows"><button id="send">Send</button><button data-k="backspace">&#9003;</button><button data-k="enter">Enter</button></div></div>
<div class="panel" id="p-apps"><div id="apps" class="grid"></div></div>
<div id="tabs"><button data-t="dpad">D-pad</button><button data-t="pad">Touchpad</button><button data-t="type">Type</button><button data-t="apps">Apps</button></div></div>
<script>
const $=s=>document.querySelector(s);let pin=localStorage.getItem("tvpin")||"";
async function api(path,body){const r=await fetch(path,{method:body?"POST":"GET",headers:{"X-Pin":pin,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
 if(r.status===401||r.status===429){showLogin((await r.json()).error);throw 0}return r.json()}
function showLogin(m){$("#main").hidden=true;$("#login").hidden=false;$("#err").textContent=m||""}
async function load(){try{const s=await api("/api/state");$("#login").hidden=true;$("#main").hidden=false;
 $("#st").textContent=s.running?"An app is running":"Home screen";const a=$("#apps");a.replaceChildren();const n=s.apps.length,c=n<=4?2:n<=12?3:4;a.style.gridTemplateColumns="repeat("+c+",1fr)";a.style.gridTemplateRows="repeat("+Math.max(1,Math.ceil(n/c))+",minmax(0,1fr))";a.style.overflowY=n>20?"auto":"hidden";a.style.fontSize=n>12?"14px":"17px";
 s.apps.forEach(x=>{const b=document.createElement("button");b.textContent=x.name;b.style.background=x.color;b.onclick=()=>{buzz();api("/api/launch",{i:x.i}).then(()=>setTimeout(load,800))};a.append(b)})}catch(e){}}
const buzz=()=>navigator.vibrate&&navigator.vibrate(12);
function tab(t){document.querySelectorAll(".panel").forEach(p=>p.classList.toggle("on",p.id==="p-"+t));
 document.querySelectorAll("[data-t]").forEach(b=>b.classList.toggle("on",b.dataset.t===t));try{localStorage.setItem("tvtab",t)}catch(e){}}
document.querySelectorAll("[data-t]").forEach(b=>b.onclick=()=>{buzz();tab(b.dataset.t)});
tab(["dpad","pad","type","apps"].includes(localStorage.getItem("tvtab"))?localStorage.getItem("tvtab"):"dpad");
function press(k){buzz();api("/api/key",{key:k}).catch(()=>{})}
document.querySelectorAll("[data-k]").forEach(b=>{let t,i;const k=b.dataset.k,dir=["up","down","left","right"].includes(k);
 b.onpointerdown=e=>{e.preventDefault();press(k);if(dir){t=setTimeout(()=>{i=setInterval(()=>press(k),130)},420)}};
 const stop=()=>{clearTimeout(t);clearInterval(i)};b.onpointerup=b.onpointerleave=b.onpointercancel=stop});
document.querySelectorAll("[data-v]").forEach(b=>b.onclick=()=>{buzz();api("/api/volume",{op:b.dataset.v}).catch(()=>{})});
(()=>{const pad=$("#pad"),post=(p,b)=>api(p,b).catch(()=>{});
 let acc={x:0,y:0,s:0},last=null,t0=0,moved=0,maxF=0,dragging=false,lp=null,timer=null;
 const avg=ts=>{let x=0,y=0;for(const t of ts){x+=t.clientX;y+=t.clientY}return{x:x/ts.length,y:y/ts.length}};
 const flush=()=>{timer=null;const dx=Math.round(acc.x),dy=Math.round(acc.y);
  if(dx||dy){acc.x-=dx;acc.y-=dy;post("/api/mouse",{dx,dy})}
  const sc=Math.trunc(acc.s);if(sc){acc.s-=sc;post("/api/mouse",{scroll:sc})}};
 const kick=()=>{if(!timer)timer=setTimeout(flush,30)};
 const endDrag=()=>{if(dragging){post("/api/mouse",{btn:"left",act:"up"});dragging=false}};
 pad.addEventListener("touchstart",e=>{e.preventDefault();maxF=Math.max(maxF,e.touches.length);
  if(e.touches.length===1){t0=Date.now();moved=0;dragging=false;clearTimeout(lp);
   lp=setTimeout(()=>{if(moved<8){dragging=true;buzz();post("/api/mouse",{btn:"left",act:"down"})}},450)}
  last=avg(e.touches)},{passive:false});
 pad.addEventListener("touchmove",e=>{e.preventDefault();const p=avg(e.touches);if(!last){last=p;return}
  const dx=p.x-last.x,dy=p.y-last.y;last=p;moved+=Math.abs(dx)+Math.abs(dy);
  if(e.touches.length>=2){acc.s+=-dy/18}else{acc.x+=dx*1.6;acc.y+=dy*1.6}kick()},{passive:false});
 pad.addEventListener("touchend",e=>{e.preventDefault();clearTimeout(lp);
  if(e.touches.length===0){const dt=Date.now()-t0;
   if(dragging)endDrag();else if(moved<10&&dt<250){buzz();post("/api/mouse",{btn:maxF>=2?"right":"left",act:"click"})}
   maxF=0;last=null;flush()}else{last=avg(e.touches)}},{passive:false});
 pad.addEventListener("touchcancel",()=>{clearTimeout(lp);endDrag();maxF=0;last=null});
 document.querySelectorAll("[data-m]").forEach(b=>b.onclick=()=>{buzz();const m=b.dataset.m;
  post("/api/mouse",m==="double"?{btn:"left",act:"double"}:{btn:m,act:"click"})});
 document.querySelectorAll("[data-s]").forEach(b=>b.onclick=()=>{buzz();post("/api/mouse",{scroll:+b.dataset.s*3})});
 let held=false;$("#hold").onclick=()=>{buzz();held=!held;$("#hold").classList.toggle("on",held);
  $("#hold").textContent=held?"Release":"Hold";post("/api/mouse",{btn:"left",act:held?"down":"up"})};
})();
$("#send").onclick=async()=>{const t=$("#txt").value;if(!t)return;try{const r=await api("/api/type",{text:t});$("#txt").value=""}catch(e){}};
$("#go").onclick=()=>{pin=$("#pin").value.trim();localStorage.setItem("tvpin",pin);load()};
if(pin)load();else showLogin();setInterval(()=>{if(!$("#main").hidden)load()},5000);
</script></body></html>"""

KEYS_OK = {"up", "down", "left", "right", "select", "back", "menu", "playpause", "home", "backspace", "enter", "escape"}
EXT_KEYS = {"up": "Up", "down": "Down", "left": "Left", "right": "Right", "select": "Return", "enter": "Return",
            "back": "XF86Back", "playpause": "XF86AudioPlay", "backspace": "BackSpace", "escape": "Escape"}


def local_ips():
    ips = set()
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:  # no packet is sent; just picks the LAN interface
            sk.connect(("8.8.8.8", 80))
            ips.add(sk.getsockname()[0])
    except OSError:
        pass
    return sorted(i for i in ips if i.count(".") == 3 and not i.startswith("127."))


def qr_matrix(text):
    """Tiny QR encoder (byte mode, error correction L, versions 1-5) so the phone-remote code needs no extra package.
    Returns a list of rows of booleans (True = dark), or None if the text is too long."""
    data = text.encode()
    caps = {1: (19, 7), 2: (34, 10), 3: (55, 15), 4: (80, 20), 5: (108, 26)}  # version: (data bytes, EC bytes), 1 block
    ver = next((v for v, (d, _e) in caps.items() if len(data) + 2 <= d), None)
    if ver is None:
        return None
    nd, ne = caps[ver]
    bits = "0100" + format(len(data), "08b") + "".join(format(b, "08b") for b in data)
    bits += "0" * min(4, nd * 8 - len(bits))
    bits += "0" * (-len(bits) % 8)
    cw = [int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)]
    for pad in range(nd - len(cw)):
        cw.append(0xEC if pad % 2 == 0 else 0x11)
    exp, log, x = [0] * 512, [0] * 256, 1  # GF(256), polynomial 0x11d
    for i in range(255):
        exp[i], log[x] = x, i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        exp[i] = exp[i - 255]
    mul = lambda a, b: 0 if a == 0 or b == 0 else exp[log[a] + log[b]]
    gen = [1]
    for i in range(ne):
        nxt = [0] * (len(gen) + 1)
        for j, c in enumerate(gen):
            nxt[j] ^= c
            nxt[j + 1] ^= mul(c, exp[i])
        gen = nxt
    rem = [0] * ne
    for b in cw:
        f = b ^ rem[0]
        rem = rem[1:] + [0]
        for j in range(ne):
            rem[j] ^= mul(gen[j + 1], f)
    allbits = [int(c) for c in "".join(format(b, "08b") for b in cw + rem)]
    n = 17 + 4 * ver
    m = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def put(xx, yy, v):
        m[yy][xx] = v; fn[yy][xx] = True

    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # finder patterns with separators
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                xx, yy = cx + dx, cy + dy
                if 0 <= xx < n and 0 <= yy < n:
                    d = max(abs(dx), abs(dy))
                    put(xx, yy, d not in (2, 4))
    for i in range(n):  # timing
        if not fn[6][i]: put(i, 6, i % 2 == 0)
        if not fn[i][6]: put(6, i, i % 2 == 0)
    if ver >= 2:  # one alignment pattern
        c = 4 * ver + 10
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                put(c + dx, c + dy, max(abs(dx), abs(dy)) != 1)
    for i in range(9):  # reserve format areas
        fn[8][i] = fn[i][8] = True
    for i in range(8):
        fn[8][n - 1 - i] = fn[n - 1 - i][8] = True
    fn[n - 8][8] = True

    def place():
        k = 0
        for right in range(n - 1, 0, -2):
            if right <= 6:
                right -= 1
            for vert in range(n):
                for j in range(2):
                    xx = right - j
                    yy = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                    if not fn[yy][xx] and k < len(allbits):
                        m[yy][xx] = bool(allbits[k]); k += 1

    place()
    masks = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]

    def build(mk):
        g = [row[:] for row in m]
        for yy in range(n):
            for xx in range(n):
                if not fn[yy][xx] and masks[mk](xx, yy):
                    g[yy][xx] = not g[yy][xx]
        d = (1 << 3) | mk  # error correction L = 01
        r = d
        for _ in range(10):
            r = (r << 1) ^ ((r >> 9) * 0x537)
        fb = ((d << 10) | r) ^ 0x5412
        bit = lambda i: bool((fb >> i) & 1)
        for i in range(6): g[i][8] = bit(i)
        g[7][8], g[8][8], g[8][7] = bit(6), bit(7), bit(8)
        for i in range(9, 15): g[8][14 - i] = bit(i)
        for i in range(8): g[8][n - 1 - i] = bit(i)
        for i in range(8, 15): g[n - 15 + i][8] = bit(i)
        g[n - 8][8] = True
        return g

    def penalty(g):
        p = 0
        for lines in (g, [list(c) for c in zip(*g)]):
            for row in lines:
                run = 1
                for i in range(1, n):
                    if row[i] == row[i - 1]:
                        run += 1
                        if run == 5: p += 3
                        elif run > 5: p += 1
                    else:
                        run = 1
                s = "".join("1" if v else "0" for v in row)
                p += 40 * (s.count("10111010000") + s.count("00001011101"))
        for yy in range(n - 1):
            for xx in range(n - 1):
                if g[yy][xx] == g[yy][xx + 1] == g[yy + 1][xx] == g[yy + 1][xx + 1]:
                    p += 3
        dark = sum(sum(r) for r in g)
        return p + 10 * (abs(dark * 20 - n * n * 10) // (n * n))

    return min((build(k) for k in range(8)), key=penalty)


class WebRemote:
    """Small PIN-protected web page + API so a phone on the same Wi-Fi can drive TV Hub (opt-in)."""

    def __init__(self, hub):
        self.hub, self.httpd, self.port, self.error, self.fail = hub, None, None, None, {}

    def apply(self):  # call from the GTK thread after settings change
        cfg = self.hub.cfg
        want, port = cfg.get("web_remote", False), int(cfg.get("web_port", 8765))
        if self.httpd and (not want or port != self.port):
            self.stop()
        if want and not self.httpd:
            if not cfg.get("web_pin"):
                cfg["web_pin"] = f"{secrets.randbelow(10 ** 6):06d}"; save(cfg)
            self.start(port)

    def stop(self):
        self.httpd.shutdown(); self.httpd.server_close(); self.httpd = None

    def start(self, port):
        remote = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"  # keep-alive: the touchpad sends many small requests
            timeout = 30

            def log_message(self, *a):
                pass

            def send(self, code, payload, ctype="application/json"):
                data = payload if isinstance(payload, bytes) else (payload if isinstance(payload, str)
                                                                    else json.dumps(payload)).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store"); self.end_headers()
                self.wfile.write(data)

            def authed(self):
                ip = self.client_address[0]
                n, until = remote.fail.get(ip, (0, 0))
                if time.time() < until:
                    self.send(429, {"error": "Too many wrong PINs. Wait a minute."}); return False
                pin = str(remote.hub.cfg.get("web_pin", "")).encode()
                if hmac.compare_digest(self.headers.get("X-Pin", "").encode(errors="replace"), pin):
                    remote.fail.pop(ip, None); return True
                n += 1
                remote.fail[ip] = (0, time.time() + 60) if n >= 5 else (n, 0)
                self.send(401, {"error": "Wrong PIN"}); return False

            def do_GET(self):
                if self.path == "/":
                    return self.send(200, PAGE, "text/html; charset=utf-8")
                if self.path != "/api/state":
                    return self.send(404, {"error": "not found"})
                if not self.authed():
                    return
                apps = []
                names = list(getattr(remote.hub, "item_labels", []))
                for i, a in enumerate(list(getattr(remote.hub, "items", []))):
                    sp = a.get("special")
                    if sp in (None, "browser", "local", "drive"):
                        apps.append({"i": i, "color": a.get("color") or "#3b4a63",
                                     "name": (names[i] if i < len(names) else None) or a.get("name")
                                     or {"browser": "Web Browser", "local": "Local Media"}.get(sp, "?")})
                self.send(200, {"running": os.path.exists(STATE), "apps": apps})

            def do_POST(self):
                try:  # read the body first so a keep-alive connection stays in sync even if auth fails
                    n = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(n) if 0 <= n <= 4096 else b""
                    if n > 4096:
                        self.close_connection = True
                except Exception:
                    return self.send(400, {"error": "bad request"})
                if not self.authed():
                    return
                try:
                    body = json.loads(raw or b"{}")
                except Exception:
                    return self.send(400, {"error": "bad request"})
                hub = remote.hub
                if self.path == "/api/key" and body.get("key") in KEYS_OK:
                    GLib.idle_add(hub.remote_key, body["key"])
                    return self.send(200, {"ok": True})
                if self.path == "/api/launch":
                    try:
                        GLib.idle_add(hub.remote_launch, int(body.get("i")))
                        return self.send(200, {"ok": True})
                    except (TypeError, ValueError):
                        pass
                if self.path == "/api/volume":
                    if os_volume(body.get("op")):
                        return self.send(200, {"ok": True})
                    return self.send(501, {"error": "volume control isn't available (Linux needs pactl)"})
                if self.path == "/api/mouse":
                    try:
                        if "scroll" in body:
                            ok = os_scroll(float(body["scroll"]))
                        elif "btn" in body:
                            ok = os_mouse_button(str(body["btn"]), str(body.get("act", "click")))
                        else:
                            ok = os_mouse_move(max(-400, min(400, int(body.get("dx", 0)))),
                                               max(-400, min(400, int(body.get("dy", 0)))))
                    except (TypeError, ValueError, OverflowError):
                        return self.send(400, {"error": "bad request"})
                    if ok:
                        return self.send(200, {"ok": True})
                    return self.send(501, {"error": "mouse control isn't available (Linux needs libXtst or xdotool)"})
                if self.path == "/api/type":
                    text = str(body.get("text", ""))[:200]
                    if not os_input_available():
                        return self.send(501, {"error": "typing needs xdotool: sudo apt install xdotool"})
                    if text:
                        os_type(text)
                    return self.send(200, {"ok": True})
                self.send(400, {"error": "bad request"})

        try:
            self.httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
            self.error = None
        except OSError as ex:
            self.error = f"Couldn't listen on port {port}: {ex}"
            return
        self.port = port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


# ---------------------------------------------------------------------------------------------
# Pop-ups (anTV Pop-up Protocol v1). Apps either serve a feed anTV listens to (pull) or POST to
# anTV's push address. See anTV_Popup_Protocol_Spec.md.
# ---------------------------------------------------------------------------------------------
POPUP_POSITIONS = ("top-right", "top-left", "bottom-right", "bottom-left")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def origin_of(url):
    """'http://host:3000/some/path' -> 'http://host:3000' (adds http:// when missing)."""
    url = (url or "").strip()
    if url and "://" not in url:
        url = "http://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}" if p.scheme in ("http", "https") and p.netloc else ""


def _clip(v, n):
    return " ".join(str(v if v is not None else "").split())[:n]


def popup_clean(raw, source, base=None, color=None):
    """Validate one pop-up from any app and return the normalized dict, or None.
    base = the feed's origin: action URLs must stay on it. Pushed pop-ups (base None) need absolute URLs."""
    if not isinstance(raw, dict):
        return None
    title, body = _clip(raw.get("title"), 120), _clip(raw.get("body"), 400)
    if not title and not body:
        return None
    col = raw.get("color") if _COLOR_RE.match(str(raw.get("color") or "")) else (
        color if _COLOR_RE.match(str(color or "")) else "#ffb84d")
    try:
        timeout = None if raw.get("timeout") is None else max(0.0, min(600.0, float(raw["timeout"])))
    except (TypeError, ValueError):
        timeout = None
    acts = []
    for a in (raw.get("actions") or [])[:3]:
        if not isinstance(a, dict) or not _clip(a.get("label"), 24):
            continue
        kind = a.get("kind") if a.get("kind") in ("http", "open", "dismiss") else "http"
        out = {"label": _clip(a.get("label"), 24), "kind": kind, "close": a.get("close", True) is not False}
        if kind == "http":
            method = str(a.get("method") or "POST").upper()
            if method not in ("GET", "POST", "PATCH", "PUT", "DELETE") or not a.get("url"):
                continue
            url = str(a["url"]).strip()
            if base:
                url = urljoin(base + "/", url)
                if origin_of(url) != base:
                    continue  # a feed may only call back to its own app
            elif not url.startswith(("http://", "https://")):
                continue
            out.update(method=method, url=url, body=a.get("body"))
        acts.append(out)
    return {"id": _clip(raw.get("id"), 80) or None, "source": _clip(source, 40) or "App", "source_url": base,
            "title": title, "body": body, "tag": _clip(raw.get("tag"), 60), "color": col,
            "priority": raw.get("priority") if raw.get("priority") in ("low", "normal", "high") else "normal",
            "timeout": timeout, "sound": raw.get("sound", True) is not False, "test": bool(raw.get("test")),
            "actions": acts}


def legacy_due(obj, base):
    """Tasks builds before the protocol only send a 'due' event; turn it into a popup."""
    t = (obj or {}).get("task") or {}
    if not t.get("text"):
        return None
    when = time.strftime("%a %I:%M %p", time.localtime((t.get("due") or 0) / 1000)).replace(" 0", " ")
    test = bool(obj.get("test"))
    u = f"/api/lists/{t.get('listId')}/tasks/{t.get('id')}"
    return {"id": f"due:{t.get('id')}:{t.get('due')}:{t.get('snoozeUntil') or 0}", "title": t["text"],
            "tag": f"{t.get('listName', 'Tasks')} \u00b7 " + ("Overdue" if obj.get("overdue") else "Due " + when),
            "color": t.get("color"), "priority": "high" if obj.get("overdue") else "normal", "test": test,
            "actions": [] if test else [
                {"label": "\u2713 Done", "method": "PATCH", "url": u, "body": {"done": True}},
                {"label": "\u23f0 10 min", "method": "POST", "url": u + "/snooze", "body": {"minutes": 10}},
                {"label": "Open", "kind": "open"}]}


def popup_from_event(src, has_manifest, event, data):
    base = src["url"]
    if event == "popup":
        return popup_clean(data, src.get("name"), base, src.get("color"))
    if event == "due" and not has_manifest:
        return popup_clean(legacy_due(data, base), src.get("name") or "Tasks", base, src.get("color"))
    return None


def chime():
    try:
        if IS_WIN:
            import winsound
            winsound.MessageBeep()
        elif shutil.which("canberra-gtk-play"):
            subprocess.Popen(["canberra-gtk-play", "-i", "message"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("paplay") and os.path.exists("/usr/share/sounds/freedesktop/stereo/message.oga"):
            subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/message.oga"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            Gdk.beep()
    except Exception:
        pass


class PopupFeed(threading.Thread):
    """Listens to one app's Server-Sent-Events feed and reconnects forever (apps may start later)."""

    def __init__(self, center, src):
        super().__init__(daemon=True)
        self.center, self.src, self.stop_ev = center, src, threading.Event()
        self.state, self.manifest, self.resp = "connecting", None, None

    def stop(self):
        self.stop_ev.set()
        try:
            if self.resp:
                self.resp.close()
        except Exception:
            pass

    def run(self):
        wait = 3
        while not self.stop_ev.is_set():
            try:
                if self.stream():
                    wait = 3
            except Exception:
                pass
            if not self.stop_ev.is_set():
                self.state = "offline"
                self.stop_ev.wait(wait)
                wait = min(30, wait * 2)

    def stream(self):
        base = self.src["url"]
        try:
            with urllib.request.urlopen(base + "/antv.json", timeout=5) as r:
                m = json.loads(r.read(65536))
            self.manifest = m if isinstance(m, dict) and m.get("protocol") else None
        except urllib.error.HTTPError as ex:
            if ex.code != 404:
                raise
            self.manifest = None  # older app without a manifest: use its plain /api/events feed
        if self.manifest and not self.src.get("name"):
            self.src["name"] = _clip(self.manifest.get("name"), 40)
        if self.manifest and not self.src.get("color") and _COLOR_RE.match(str(self.manifest.get("color") or "")):
            self.src["color"] = self.manifest["color"]
        path = (self.manifest or {}).get("events") or "/api/events"
        req = urllib.request.Request(urljoin(base + "/", path), headers={"Accept": "text/event-stream"})
        self.resp = urllib.request.urlopen(req, timeout=70)  # apps ping every ~25 s, so silence means dead
        self.state = "connected"
        ev, data = "message", []
        for raw in self.resp:
            if self.stop_ev.is_set():
                break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line == "":
                if data:
                    try:
                        p = popup_from_event(self.src, bool(self.manifest), ev, json.loads("\n".join(data)))
                    except ValueError:
                        p = None
                    if p:
                        self.center.submit(p)
                ev, data = "message", []
            elif line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
        return True


class PopupWindow(Gtk.Window):
    """One pop-up card. It never takes keyboard focus (so a movie keeps its keys); it is answered through
    PopupCenter.handle() (controller, phone remote) or by clicking a button."""

    def __init__(self, center, p, more):
        # POPUP = override-redirect on X11: the window manager does not manage it, so a fullscreen kiosk browser
        # or Waydroid cannot stack above it (a normal "keep above" window would end up underneath).
        super().__init__(type=Gtk.WindowType.POPUP)
        self._antv_popup = True
        self.center, self.p, self.sel = center, p, 0
        self.set_title("anTV pop-up"); self.set_name("antv-popup")
        self.set_decorated(False); self.set_resizable(False); self.set_keep_above(True)
        self.set_skip_taskbar_hint(True); self.set_skip_pager_hint(True)
        self.set_accept_focus(False); self.set_focus_on_map(False)
        scr = self.get_screen(); vis = scr.get_rgba_visual()
        rad = "0"
        if vis is not None and scr.is_composited():  # rounded corners only where the background can be transparent
            self.set_visual(vis); self.set_app_paintable(True); rad = "20px"
        acc = p["color"]
        css = (f"#antv-popup{{background-color:#1c1f27;border-radius:{rad};border-left:12px solid {acc};}}"
               f"#antv-popup label.ptag{{color:{acc};font-weight:bold;font-size:15pt;}}"
               "#antv-popup label.ptitle{color:#f4f5f8;font-weight:bold;font-size:30pt;}"
               "#antv-popup label.pbody{color:#c9ccd6;font-size:18pt;}"
               "#antv-popup label.phint{color:#8d93a3;font-size:13pt;}"
               "#antv-popup button{background-image:none;background-color:#2d3240;color:#f1f2f5;font-size:18pt;"
               "font-weight:bold;border-radius:12px;padding:10px 22px;border:none;box-shadow:none;}"
               f"#antv-popup button.sel{{background-color:{acc};color:#15171c;}}")
        self.prov = Gtk.CssProvider(); self.prov.load_from_data(css.encode())
        self.actions = list(p["actions"])
        if not any(a["kind"] == "dismiss" for a in self.actions):
            self.actions.append({"label": "Dismiss", "kind": "dismiss", "close": True})
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10); box.set_border_width(26)
        tag = f"{p['source']} \u00b7 {p['tag']}" if p["tag"] else p["source"]
        for text, cls in ((tag, "ptag"), (p["title"] or p["body"], "ptitle"), (p["body"] if p["title"] else "", "pbody")):
            if text:
                lab = Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=34); lab.get_style_context().add_class(cls)
                box.pack_start(lab, False, False, 0)
        row = Gtk.Box(spacing=12); self.buttons = []
        for i, a in enumerate(self.actions):
            b = Gtk.Button(label=a["label"]); b.set_can_focus(False)
            b.connect("clicked", lambda _b, i=i: center.activate(i))
            row.pack_start(b, False, False, 0); self.buttons.append(b)
        box.pack_start(row, False, False, 8)
        self.hint = Gtk.Label(xalign=0); self.hint.get_style_context().add_class("phint")
        box.pack_start(self.hint, False, False, 0)
        self.add(box)
        self.restyle(self)  # a provider on a window does not reach its children, so hand it to each widget
        self.set_more(more); self.set_sel(0)

    def restyle(self, w):
        w.get_style_context().add_provider(self.prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        if isinstance(w, Gtk.Container):
            w.forall(self.restyle)

    def set_more(self, more):
        keys = "\u25c0 \u25b6 choose   OK run   Back dismiss" if len(self.actions) > 1 else "OK / Back dismiss"
        self.hint.set_text(keys + (f"      +{more} more" if more else ""))

    def set_sel(self, i):
        self.sel = i % len(self.buttons)
        for j, b in enumerate(self.buttons):
            (b.get_style_context().add_class if j == self.sel else b.get_style_context().remove_class)("sel")

    def put(self, mon):
        g = mon.get_geometry(); w, h = 700, self.get_preferred_height()[1]
        self.set_size_request(w, -1)
        pos = self.center.hub.cfg.get("popup_pos", "top-right")
        top, right = (pos if pos in POPUP_POSITIONS else "top-right").split("-")
        x = g.x + (g.width - w - 48 if right == "right" else 48)
        y = g.y + (48 if top == "top" else g.height - h - 48)
        self.move(x, y)


class PopupCenter:
    """Owns the feeds, the push server, the queue and the one visible pop-up. GTK-thread only, except submit()."""

    def __init__(self, hub):
        self.hub, self.feeds, self.queue, self.win, self.cur = hub, {}, [], None, None
        self.seen, self.timer, self.push, self.push_error = {}, None, None, None

    @property
    def active(self):
        return self.win is not None

    # ---- sources
    def sources(self):
        out, used = [], set()
        cfg = self.hub.cfg
        for s in list(cfg.get("popup_sources", [])):
            o = origin_of(s.get("url"))
            if o and s.get("enabled", True) and o not in used:
                used.add(o); out.append({"name": s.get("name") or "", "url": o, "color": s.get("color")})
        for _l, a in flatten_apps(cfg.get("apps", [])):
            o = origin_of(a.get("url")) if a.get("popups") else ""
            if o and o not in used:
                used.add(o); out.append({"name": a["name"], "url": o, "color": a.get("color")})
        return out

    def sync(self):
        """Start/stop feed listeners to match Settings and the apps flagged 'popups'. Safe to call any time."""
        want = {s["url"]: s for s in self.sources()}
        for url in [u for u in self.feeds if u not in want]:
            self.feeds.pop(url).stop()
        for url, src in want.items():
            if url in self.feeds:
                self.feeds[url].src.update(src)
            else:
                self.feeds[url] = PopupFeed(self, src); self.feeds[url].start()

    def status(self):
        if not self.hub.cfg.get("popups", True):
            return "Off"
        n = len(self.feeds); ok = sum(1 for f in self.feeds.values() if f.state == "connected")
        return "none yet" if not n else f"{ok} of {n} connected"

    def apply(self):
        """Settings changed (or startup)."""
        self.sync()
        cfg = self.hub.cfg
        want = bool(cfg.get("popup_push"))
        port, lan = int(cfg.get("popup_port", 8767)), bool(cfg.get("popup_lan"))
        if self.push and (not want or self.push["port"] != port or self.push["lan"] != lan):
            self.push["httpd"].shutdown(); self.push["httpd"].server_close(); self.push = None
        if want and not self.push:
            if not cfg.get("popup_token"):
                cfg["popup_token"] = secrets.token_urlsafe(16); save(cfg)
            self.start_push(port, lan)

    def start_push(self, port, lan):
        center = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = 15

            def log_message(self, *a):
                pass

            def send(self, code, payload):
                data = json.dumps(payload).encode()
                self.send_response(code); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)

            def do_POST(self):
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    raw = self.rfile.read(n) if 0 <= n <= 8192 else b""
                    if n > 8192:
                        self.close_connection = True
                except Exception:
                    return self.send(400, {"error": "bad request"})
                tok = str(center.hub.cfg.get("popup_token", "")).encode()
                if not hmac.compare_digest(self.headers.get("X-Antv-Token", "").encode(errors="replace"), tok):
                    return self.send(401, {"error": "wrong or missing X-Antv-Token"})
                if self.path != "/notify":
                    return self.send(404, {"error": "not found"})
                try:
                    obj = json.loads(raw or b"{}")
                except ValueError:
                    return self.send(400, {"error": "bad json"})
                p = popup_clean(obj, (obj or {}).get("app") if isinstance(obj, dict) else None)
                if not p:
                    return self.send(400, {"error": "need a title or body"})
                center.submit(p)
                self.send(200, {"ok": True})

            def do_GET(self):
                self.send(200, {"antv": VERSION, "protocol": 1})

        try:
            httpd = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), H)
            self.push_error = None
        except OSError as ex:
            self.push_error = f"Couldn't listen on port {port}: {ex}"
            return
        self.push = {"httpd": httpd, "port": port, "lan": lan}
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

    # ---- queue and display
    def submit(self, p):
        """Any thread."""
        GLib.idle_add(self._submit, p)

    def _submit(self, p):
        cfg = self.hub.cfg
        if not cfg.get("popups", True):
            return False
        now = time.monotonic()
        if p.get("id") and not p["test"]:
            for k in [k for k, t in self.seen.items() if now - t > 300]:
                del self.seen[k]
            key = (p["source"], p["id"])
            if key in self.seen:
                return False
            self.seen[key] = now
        if self.win is None:
            self.show(p)
        elif p["priority"] == "high" and self.cur["priority"] != "high":
            self.queue.insert(0, self.cur); self.close(advance=False); self.show(p)
        elif len(self.queue) < 20:
            self.queue.append(p); self.win.set_more(len(self.queue))
        return False

    def show(self, p):
        self.cur = p
        self.win = PopupWindow(self, p, len(self.queue))
        self.win.show_all(); self.win.put(self.hub.mon); self.win.show()
        secs = p["timeout"] if p["timeout"] is not None else float(self.hub.cfg.get("popup_secs", 20))
        if secs > 0:
            self.timer = GLib.timeout_add(int(secs * 1000), self._expire, self.win)
        if p["sound"] and self.hub.cfg.get("popup_sound", True) and p["priority"] != "low":
            chime()

    def _expire(self, win):
        self.timer = None
        if win is self.win:
            self.close()
        return False

    def close(self, advance=True):
        if self.timer:
            GLib.source_remove(self.timer); self.timer = None
        if self.win is not None:
            self.win.destroy()
        self.win, self.cur = None, None
        if advance and self.queue:
            GLib.timeout_add(400, self._next)

    def _next(self):
        if self.win is None and self.queue:
            self.show(self.queue.pop(0))
        return False

    # ---- answering
    def handle(self, act):
        """Controller / phone-remote button (GTK thread). True = consumed. Up/down/menu/home are never taken."""
        if self.win is None:
            return False
        if act in ("left", "right"):
            if len(self.win.buttons) > 1:
                self.win.set_sel(self.win.sel + (-1 if act == "left" else 1)); return True
            return False
        if act == "select":
            self.activate(self.win.sel); return True
        if act in ("back", "escape"):
            self.close(); return True
        return False

    def activate(self, i):
        if self.win is None or not (0 <= i < len(self.win.actions)):
            return
        a, p = self.win.actions[i], self.cur
        if a["kind"] == "open":
            self.hub.open_source_app(p["source"], p.get("source_url"))
        elif a["kind"] == "http":
            def work():
                try:
                    data = None if a["method"] == "GET" else json.dumps(a["body"] if a.get("body") is not None else {}).encode()
                    req = urllib.request.Request(a["url"], data=data, method=a["method"],
                                                 headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=8).close()
                except Exception as ex:
                    GLib.idle_add(self.hub.toast, "Pop-up action failed: %s" % ex)
            threading.Thread(target=work, daemon=True).start()
        if a.get("close", True):
            self.close()

    def test(self):
        self.submit(popup_clean({"title": "This is what an anTV pop-up looks like", "tag": "Test",
                                 "body": "Choose with left/right on the controller, OK to run, Back to dismiss.",
                                 "test": True, "actions": [{"label": "Nice", "kind": "dismiss"}]}, "anTV"))


class Splash(Gtk.Window):
    """Fullscreen status screen shown while a Node.js app installs/starts. Esc cancels."""

    def __init__(self, hub, cancel):
        super().__init__(title="TV Hub")
        self.set_decorated(False)
        self.lab = Gtk.Label(justify=Gtk.Justification.CENTER)
        self.add(self.lab)
        self.connect("key-press-event", lambda w, e: cancel.set() if (Gdk.keyval_name(e.keyval) == "Escape"
                      or remote_action(hub.cfg, Gdk.keyval_name(e.keyval)) == "back") else None)
        self.set_text("Starting\u2026")
        self.show_all()
        self.fullscreen_on_monitor(Gdk.Screen.get_default(), hub.mon_idx)

    def set_text(self, text):
        t = GLib.markup_escape_text(text)
        self.lab.set_markup(f'<span size="36000" foreground="white" weight="bold">{t}</span>\n\n'
                            f'<span size="20000" foreground="#7d8590">Esc to cancel</span>')


def choose_dialog(parent, cfg, title, options, text=None):
    """Big-button menu. Returns the chosen index or None."""
    dlg = Gtk.Dialog(title=title, transient_for=parent, modal=True)
    hook_back(dlg, cfg)
    box = dlg.get_content_area(); box.set_spacing(12); box.set_border_width(32)
    lab = Gtk.Label(label=title, xalign=0); lab.set_name("tvs-dlg-title")
    box.pack_start(lab, False, False, 8)
    if text:
        box.pack_start(Gtk.Label(label=text, xalign=0, wrap=True, max_width_chars=64), False, False, 4)
    first = None
    holder = box
    if len(options) > 8:  # a long list scrolls instead of running off the screen
        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sc = Gtk.ScrolledWindow(); sc.set_min_content_height(660); sc.set_min_content_width(720); sc.add(holder)
        box.pack_start(sc, True, True, 0)
    for i, o in enumerate(options):
        b = Gtk.Button(label=o); b.set_size_request(680, 84)
        b.connect("clicked", lambda _b, i=i: dlg.response(i))
        holder.pack_start(b, False, False, 0); first = first or b
    dlg.show_all()
    if first:
        first.grab_focus()
    r = dlg.run(); dlg.destroy()
    return r if 0 <= r < len(options) else None


def ask_text(parent, cfg, title, prompt, default=""):
    """Small text-entry dialog. Returns the text or None. (The phone remote's 'Type on TV' can fill it in.)"""
    dlg = Gtk.Dialog(title=title, transient_for=parent, modal=True)
    hook_back(dlg, cfg)
    dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "OK", Gtk.ResponseType.OK)
    dlg.set_default_response(Gtk.ResponseType.OK)
    box = dlg.get_content_area(); box.set_spacing(14); box.set_border_width(28)
    box.pack_start(Gtk.Label(label=prompt, xalign=0, wrap=True, max_width_chars=60), False, False, 0)
    entry = Gtk.Entry(text=default); entry.set_activates_default(True); entry.set_size_request(560, -1)
    box.pack_start(entry, False, False, 0)
    dlg.show_all(); entry.grab_focus()
    r = dlg.run(); val = entry.get_text().strip() if r == Gtk.ResponseType.OK else None
    dlg.destroy()
    return val or None


def run_busy(parent, cfg, text, fn):
    """Show a spinner while fn() runs in a thread. Returns {'v': result} or {'e': error text}."""
    win = Gtk.Window(title="anTV", transient_for=parent, modal=True)
    win.set_decorated(False); win.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
    tenft(win, cfg)
    box = Gtk.Box(spacing=24, margin=40)
    sp = Gtk.Spinner(); sp.set_size_request(48, 48); sp.start()
    lab = Gtk.Label(label=text, xalign=0); lab.set_name("tvs-dlg-title")
    box.pack_start(sp, False, False, 0); box.pack_start(lab, False, False, 0)
    win.add(box)
    result = {}

    def work():
        try:
            result["v"] = fn()
        except Exception as ex:
            result["e"] = str(ex)
    th = threading.Thread(target=work, daemon=True); th.start()
    win.show_all()
    while th.is_alive():
        while Gtk.events_pending():
            Gtk.main_iteration()
        time.sleep(0.03)
    win.destroy()
    return result


SHORTCUTS = [
    ("Arrow keys / D-pad", "Move between cards"),
    ("Enter / OK", "Open the highlighted card"),
    ("S, or the cog next to anTV", "Settings"),
    ("A", "Add an app"),
    ("N", "Add a Node.js app"),
    ("B", "Pick the web browser"),
    ("E", "Eject the highlighted USB drive"),
    ("Delete", "Remove the highlighted app"),
    ("F1", "Move anTV to the next screen"),
    ("H", "Hide anTV to the taskbar (click it there to bring it back)"),
    ("Esc or Q", "Quit anTV"),
    ("I", "Install an APK (Android app) on a connected device"),
    ("U", "Install the update (or restart to finish it) when the green update button shows next to the clock"),
    ("Ctrl+Alt+K", "Close the running app and come back"),
]


def show_text(parent, cfg, title, heading, markup):
    dlg = Gtk.Dialog(title=title, transient_for=parent, modal=True)
    hook_back(dlg, cfg)
    dlg.add_button("Close", Gtk.ResponseType.CLOSE)
    head = Gtk.Label(xalign=0)
    head.set_markup('<span size="x-large" weight="bold">%s</span>' % GLib.markup_escape_text(heading))
    lab = Gtk.Label(xalign=0, wrap=True, max_width_chars=70)
    lab.set_markup(markup); lab.set_valign(Gtk.Align.START)
    sw = Gtk.ScrolledWindow(); sw.set_min_content_height(440); sw.set_min_content_width(780); sw.add(lab)
    box = dlg.get_content_area(); box.set_border_width(24); box.set_spacing(14)
    box.pack_start(head, False, False, 0); box.pack_start(sw, True, True, 0)
    dlg.show_all(); dlg.run(); dlg.destroy()


def show_history(parent, cfg):
    show_text(parent, cfg, "Version history", "anTV " + VERSION,
              "\n".join("<b>%s</b>   %s" % (v, GLib.markup_escape_text(d)) for v, d in reversed(CHANGELOG)))


def show_shortcuts(parent, cfg):
    show_text(parent, cfg, "Keyboard shortcuts", "Keyboard shortcuts",
              "\n".join("<b>%s</b>   %s" % (GLib.markup_escape_text(k), GLib.markup_escape_text(d)) for k, d in SHORTCUTS))


class TVSettings(Gtk.Window):
    """10-foot settings: huge text, one list at a time, no small controls. Works with D-pad / remote / gamepad /
    phone touchpad. Left list = sections, right list = options. Left/Right change a value, Enter picks, Back goes up.
    Changes are saved as you go and applied to the main screen when you leave."""

    def __init__(self, hub):
        super().__init__(title="anTV settings")
        ensure_tenft_css()
        self.set_name("tvs-win")
        self.hub, self.cfg = hub, hub.cfg
        self.dirty, self.rows, self.pane, self.cat_index, self.sel_hint = False, [], "cats", 0, None
        self.snapshot, self.pending, self.tv_stack = copy.deepcopy(hub.cfg), False, []  # pending = changes not saved yet
        self.set_decorated(False); self.set_modal(True); self.set_transient_for(hub)
        self.connect("key-press-event", self.on_key)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20); root.set_border_width(50)
        title = Gtk.Label(label="Settings", xalign=0); title.set_name("tvs-title")
        self.hint = Gtk.Label(xalign=0); self.hint.set_name("tvs-hint")
        self.cats, self.opts = Gtk.ListBox(), Gtk.ListBox()
        self.cats.set_name("tvs-cats"); self.opts.set_name("tvs-opts")
        for lb in (self.cats, self.opts):
            lb.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.cat_defs = [("Apps & favorites", self.rows_apps), ("Layout", self.rows_layout), ("Look", self.rows_look),
                         ("Screen & browser", self.rows_system), ("Remote & devices", self.rows_devices),
                         ("Pop-ups", self.rows_popups), ("Updates", self.rows_updates), ("Your data", self.rows_data),
                         ("About", self.rows_about)]
        for name, _fn in self.cat_defs:
            rw = Gtk.ListBoxRow(); lab = Gtk.Label(label=name, xalign=0); lab.set_ellipsize(Pango.EllipsizeMode.END)
            rw.add(lab); self.cats.add(rw)
        n = len(self.cat_defs)
        self.cat_actions = {n: self.save_and_close, n + 1: self.discard_and_close, n + 2: self.hide_app, n + 3: self.quit_app}
        for label, cls in (("\u2714  Save and close", "tvs-save"), ("\u2716  Discard changes", "tvs-discard"),
                           ("\u25bc  Hide anTV (minimize)", "tvs-discard"), ("\u23fb  Quit anTV", "tvs-discard")):
            rw = Gtk.ListBoxRow(); lab = Gtk.Label(label=label, xalign=0)
            rw.add(lab); rw.get_style_context().add_class(cls); self.cats.add(rw)
        body = Gtk.Box(spacing=36)
        sc1 = Gtk.ScrolledWindow(); sc1.set_size_request(470, -1); sc1.add(self.cats)
        sc2 = Gtk.ScrolledWindow(); sc2.set_hexpand(True); sc2.add(self.opts)
        body.pack_start(sc1, False, False, 0); body.pack_start(sc2, True, True, 0)
        root.pack_start(title, False, False, 0); root.pack_start(body, True, True, 0)
        foot = Gtk.Box(spacing=16)
        foot.pack_start(self.hint, True, True, 0)
        for label, nm, fn in (("Quit", "tvs-discard", self.quit_app), ("Hide", "tvs-discard", self.hide_app),
                              ("Discard", "tvs-discard", self.discard_and_close), ("Save", "tvs-save", self.save_and_close)):
            b = Gtk.Button(label=label); b.set_name(nm)
            b.connect("clicked", lambda _b, fn=fn: fn())
            foot.pack_start(b, False, False, 0)
        root.pack_start(foot, False, False, 0)
        self.add(root)
        self.cats.connect("row-selected", self.on_cat)
        self.opts.connect("row-activated", lambda _lb, row: self.activate(row))
        self.show_all()
        self.fullscreen_on_monitor(Gdk.Screen.get_default(), hub.mon_idx)
        first = self.cats.get_row_at_index(0)
        self.cats.select_row(first); first.grab_focus()
        self.set_hint()

    # ---- plumbing
    def set_hint(self):
        self.hint.set_text("\u25b2\u25bc choose     \u25c0 \u25b6 change     Enter: select     Back: sections     Menu: save and close"
                           if self.pane == "opts"
                           else "\u25b2\u25bc choose a section     Enter or \u25b6: open     Menu: save and close     Back: close")

    def touched(self):
        self.dirty = True
        self.pending = self.cfg != self.snapshot  # only true if something really differs from what is saved

    def on_cat(self, _lb, row):
        if row is not None:
            self.cat_index = row.get_index()
            if self.cat_index != 0:
                self.tv_stack = []
            self.fill(0)

    def fill(self, sel=None):
        cur = self.opts.get_selected_row()
        if sel is None:
            sel = self.sel_hint if self.sel_hint is not None else (cur.get_index() if cur else 0)
        self.sel_hint = None
        for c in self.opts.get_children():
            self.opts.remove(c)
        self.rows = [] if self.cat_index in self.cat_actions else self.cat_defs[self.cat_index][1]()
        for d in self.rows:
            rw = Gtk.ListBoxRow(); box = Gtk.Box(spacing=24)
            lab = Gtk.Label(label=d["label"], xalign=0); lab.set_ellipsize(Pango.EllipsizeMode.END)
            val = Gtk.Label(xalign=1); val.get_style_context().add_class("val")
            box.pack_start(lab, True, True, 0); box.pack_start(val, False, False, 0)
            rw.add(box); rw.defn, rw.vl = d, val
            val.set_text(self.value_text(d))
            self.opts.add(rw)
        self.opts.show_all()
        if self.rows:
            row = self.opts.get_row_at_index(max(0, min(sel, len(self.rows) - 1)))
            self.opts.select_row(row)
            if self.pane == "opts":
                row.grab_focus()

    def to_opts(self):
        if self.cat_index in self.cat_actions:  # the Save / Discard entries act instead of opening a list
            return self.cat_actions[self.cat_index]()
        if not self.rows:
            return
        self.pane = "opts"; self.set_hint()
        row = self.opts.get_selected_row() or self.opts.get_row_at_index(0)
        self.opts.select_row(row); row.grab_focus()

    def to_cats(self):
        self.pane = "cats"; self.set_hint()
        row = self.cats.get_row_at_index(self.cat_index)
        self.cats.select_row(row); row.grab_focus()

    def focus_current(self):
        row = (self.opts if self.pane == "opts" else self.cats).get_selected_row()
        if row:
            row.grab_focus()

    def hidden(self, fn):
        """Run a normal dialog on top of the main screen while this one steps aside.
        Those screens save by themselves, so anything changed here so far is saved first."""
        if self.pending:
            self.commit()
        self.hub.add_target = self.cur_apps  # "Popular apps" / "Install APK" add into the folder being edited
        self.hide()
        try:
            return fn()
        finally:
            self.hub.add_target = None
            self.snapshot, self.dirty = copy.deepcopy(self.cfg), True
            self.show_all()
            self.fullscreen_on_monitor(Gdk.Screen.get_default(), self.hub.mon_idx)
            self.present(); self.focus_current()

    def commit(self):
        save(self.cfg)
        self.snapshot, self.pending = copy.deepcopy(self.cfg), False

    def apply_to_hub(self):
        self.hub.path = []
        self.hub.apply_bg(); self.hub.rebuild(); self.hub.place(); self.hub.web.apply(); self.hub.popups.apply()

    def finish(self):
        self.hub.tvs = None
        self.destroy()
        self.hub.present()

    def revert(self):
        self.cfg.clear(); self.cfg.update(copy.deepcopy(self.snapshot))
        self.pending = False

    def save_and_close(self):
        if self.pending:
            self.commit()
        self.apply_to_hub()
        self.finish()
        self.hub.toast("Settings saved")

    def discard_and_close(self):
        if self.pending:
            if self.choose("Discard your changes?", ["Yes, discard them", "No, keep editing"]) != 0:
                return
            self.revert()
        self.apply_to_hub()
        self.finish()

    def hide_app(self):
        """Save any changes, close settings and minimize anTV to the taskbar."""
        if self.pending:
            self.commit()
        self.apply_to_hub()
        self.finish()
        GLib.timeout_add(200, self.hub.hide_to_taskbar)

    def quit_app(self):
        if self.choose("Quit anTV?", ["Yes, quit anTV", "No, go back"]) != 0:
            return
        if self.pending:
            self.commit()
        self.hub.tvs = None
        self.hub.quit_app()

    def close_win(self):
        """Back from the section list. Unsaved changes ask what to do."""
        if self.pending:
            c = self.choose("Save your changes?", ["Save", "Discard", "Keep editing"])
            if c == 0:
                return self.save_and_close()
            if c == 1:
                self.revert(); self.apply_to_hub(); return self.finish()
            return
        if self.dirty:
            self.apply_to_hub()
        self.finish()

    # ---- keys
    def on_key(self, _w, e):
        k = Gdk.keyval_name(e.keyval)
        act = remote_action(self.cfg, k)
        row = self.opts.get_selected_row()
        if act == "back" or k in ("Escape", "BackSpace"):
            self.to_cats() if self.pane == "opts" else self.close_win()
        elif act == "menu":
            self.save_and_close()
        elif act in ("select", "playpause") or k in ("Return", "KP_Enter"):
            if self.pane == "cats":
                self.to_opts()
            elif row:
                self.activate(row)
        elif k == "Right":
            if self.pane == "cats":
                self.to_opts()
            elif row:
                self.adjust(row, 1)
        elif k == "Left":
            if self.pane == "opts" and not (row and self.adjust(row, -1)):
                self.to_cats()
        else:
            return False  # Up/Down: the list handles them
        return True

    # ---- values
    def toggle_get(self, d):
        return d["get"]() if "get" in d else self.cfg.get(d["key"], d.get("default", False))

    def toggle_set(self, d, v):
        if "set" in d:
            d["set"](v)
        else:
            self.cfg[d["key"]] = v

    def value_text(self, d):
        k = d["kind"]
        if k == "toggle":
            return "\u25c0  %s  \u25b6" % ("On" if self.toggle_get(d) else "Off")
        if k == "number":
            return "\u25c0  %s%s  \u25b6" % (self.cfg.get(d["key"], d["default"]), d.get("unit", ""))
        if k == "choice":
            return "\u25c0  %s  \u25b6" % d["opts"][d["get"]()] if d["opts"] else "none found"
        return d["value"]() if "value" in d else "\u203a"

    def adjust(self, row, dr, wrap=False):
        d, k = row.defn, row.defn["kind"]
        if k == "toggle":
            self.toggle_set(d, not self.toggle_get(d))
        elif k == "number":
            v = self.cfg.get(d["key"], d["default"]) + dr * d["step"]
            if v > d["max"]:
                v = d["min"] if wrap else d["max"]
            self.cfg[d["key"]] = max(d["min"], v)
        elif k == "choice":
            if not d["opts"]:
                return False
            d["set"]((d["get"]() + dr) % len(d["opts"]))
        else:
            return False
        self.touched(); row.vl.set_text(self.value_text(d))
        return True

    def activate(self, row):
        d, k = row.defn, row.defn["kind"]
        if k == "toggle":
            self.adjust(row, 1)
        elif k == "number":
            self.adjust(row, 1, wrap=True)
        elif k == "choice":
            i = self.choose(d["label"], d["opts"]) if d["opts"] else None
            if i is not None:
                d["set"](i); self.touched(); row.vl.set_text(self.value_text(d))
        else:
            d["run"](); self.touched(); self.fill()

    # ---- big pickers
    def choose(self, title, options):
        """Big-button menu. Returns the chosen index or None."""
        return choose_dialog(self, self.cfg, title, options)

    def pick_font(self):
        dlg = Gtk.FontChooserDialog(title="Choose the card font", transient_for=self)
        hook_back(dlg, self.cfg)
        dlg.set_font(self.cfg.get("tile_font") or "Sans Bold 26")
        r = dlg.run(); font = dlg.get_font() if r == Gtk.ResponseType.OK else None
        dlg.destroy()
        return font

    def pick_path(self, title, folder=False, images=False):
        dlg = Gtk.FileChooserDialog(title=title, transient_for=self,
                                    action=Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Choose", Gtk.ResponseType.OK)
        hook_back(dlg, self.cfg)
        if images:
            flt = Gtk.FileFilter(); flt.set_name("Images"); flt.add_pixbuf_formats(); dlg.add_filter(flt)
        dlg.set_default_size(1200, 800)
        r = dlg.run(); path = dlg.get_filename() if r == Gtk.ResponseType.OK else None
        dlg.destroy()
        return path

    # ---- sections
    def cur_apps(self):
        return self.tv_stack[-1].setdefault("apps", []) if self.tv_stack else self.cfg["apps"]

    def off(self):
        return 1 if self.tv_stack else 0  # rows above the first app (the "Up" row)

    def rows_apps(self):
        lst = self.cur_apps()
        kinds = {"web": "Website", "cmd": "Program", "node": "Node.js", "android": "Android"}
        rows = []
        if self.tv_stack:
            rows.append({"kind": "action", "label": "\u25c2  Up one folder", "run": self.tv_up,
                         "value": lambda: "in " + self.tv_stack[-1]["name"]})
        for i, a in enumerate(lst):
            rows.append({"kind": "action",
                         "label": ("\u2605  " if a.get("favorite") else "") + ("\u25a4  " if is_folder(a) else "") + a["name"],
                         "value": (lambda a=a: describe_app(a) if is_folder(a) else kinds.get(a.get("type"), "")),
                         "run": (lambda i=i: self.app_menu(i))})
        rows += [{"kind": "action", "label": "+  Add a website or program", "run": lambda: self.add_app("web")},
                 {"kind": "action", "label": "+  New folder", "run": lambda: self.add_app("folder")},
                 {"kind": "action", "label": "+  Add a Node.js app", "run": lambda: self.add_app("node")},
                 {"kind": "action", "label": "+  Popular apps (YouTube, SmartTube\u2026)", "run": lambda: self.hidden(self.hub.quick_add)},
                 {"kind": "action", "label": "+  Install an APK (Android app)", "run": lambda: self.hidden(self.hub.install_apk)},
                 {"kind": "action", "label": "Reset apps to the defaults", "run": self.reset_apps}]
        return rows

    def tv_up(self):
        child = self.tv_stack.pop()
        self.sel_hint = next((j for j, x in enumerate(self.cur_apps()) if x is child), 0) + self.off()

    def app_menu(self, i):
        lst = self.cur_apps(); a = lst[i]
        folder = is_folder(a)
        keys = (["open"] if folder else []) + ["fav", "edit", "moveto", "up", "down", "remove", "cancel"]
        names = (["Open folder"] if folder else []) + ["Toggle favorite \u2605", "Edit\u2026", "Move to folder\u2026",
                                                        "Move up", "Move down", "Remove", "Cancel"]
        c = self.choose(a["name"], names)
        key = keys[c] if c is not None else "cancel"
        self.sel_hint = i + self.off()
        if key == "open":
            self.tv_stack.append(a); self.sel_hint = 0
        elif key == "fav":
            a["favorite"] = not a.get("favorite", False)
        elif key == "edit":
            new = self.hidden(lambda: self.hub.app_form(a))
            if new:
                lst[i] = new
        elif key == "moveto":
            dests = [d for d in folder_choices(self.cfg["apps"], exclude=a) if d[1] is not lst]
            k = self.choose("Move %s to\u2026" % a["name"], [d[0] for d in dests] + ["Cancel"])
            if k is not None and k < len(dests):
                move_item(self.cfg["apps"], a, dests[k][1]); self.sel_hint = max(0, i - 1) + self.off()
        elif key in ("up", "down"):
            j = i + (-1 if key == "up" else 1)
            if 0 <= j < len(lst):
                lst[i], lst[j] = lst[j], lst[i]; self.sel_hint = j + self.off()
        elif key == "remove":
            text = ("Remove %s and everything in it?" if folder and a.get("apps") else "Remove %s?") % a["name"]
            if self.choose(text, ["Yes, remove it", "No, keep it"]) == 0:
                lst.pop(i); self.sel_hint = max(0, i - 1) + self.off()

    def add_app(self, kind):
        new = self.hidden(lambda: self.hub.app_form({"type": kind}))
        if new:
            lst = self.cur_apps(); lst.append(new)
            self.sel_hint = len(lst) - 1 + self.off()

    def reset_apps(self):
        if self.choose("Reset apps to the defaults?", ["Yes, reset", "No, keep my apps"]) == 0:
            self.cfg["apps"] = [dict(a) for a in DEFAULT["apps"]]; self.tv_stack = []; self.sel_hint = 0

    def rows_layout(self):
        c = self.cfg

        def pick(key, values, default):
            def get():
                v = c.get(key, default)
                return values.index(v if v in values else default)
            return get, (lambda i: c.__setitem__(key, values[i]))

        def fav_get(k):
            return k in c.get("favorite_builtins", [])

        def fav_set(k, v):
            st = set(c.get("favorite_builtins", []))
            (st.add if v else st.discard)(k)
            c["favorite_builtins"] = sorted(st)
        return [{"kind": "toggle", "label": "Show other apps below the favorites", "key": "show_others", "default": True},
                {"kind": "toggle", "label": "Favorites row: Web Browser", "get": lambda: fav_get("browser"),
                 "set": lambda v: fav_set("browser", v)},
                {"kind": "toggle", "label": "Favorites row: Local Media", "get": lambda: fav_get("local"),
                 "set": lambda v: fav_set("local", v)},
                {"kind": "choice", "label": "Favorites row", "opts": ["Scroll sideways", "Grid: show all"],
                 "get": lambda: 1 if c.get("fav_layout") == "grid" else 0,
                 "set": lambda i: c.__setitem__("fav_layout", "grid" if i == 1 else "scroll")},
                {"kind": "choice", "label": "Card size", "opts": ["Small", "Medium", "Large", "Extra large"],
                 "get": pick("tile_size", ("small", "medium", "large", "xlarge"), "medium")[0],
                 "set": pick("tile_size", ("small", "medium", "large", "xlarge"), "medium")[1]},
                {"kind": "choice", "label": "Card shape", "opts": ["Wide (16:9)", "Classic (4:3)", "Square", "Poster (2:3)"],
                 "get": pick("tile_shape", ("wide", "classic", "square", "poster"), "wide")[0],
                 "set": pick("tile_shape", ("wide", "classic", "square", "poster"), "wide")[1]},
                {"kind": "choice", "label": "Pictures on cards", "opts": ["Fill the card (crop)", "Fit the whole picture"],
                 "get": pick("picture_fit", ("fill", "fit"), "fill")[0],
                 "set": pick("picture_fit", ("fill", "fit"), "fill")[1]}]

    def rows_look(self):
        c = self.cfg
        name_of = lambda key: os.path.basename(str(c.get(key, "")).rstrip("/\\")) or "None"
        return [
            {"kind": "action", "label": "Card font", "value": lambda: c.get("tile_font") or "Sans Bold 26", "run": self.set_font},
            {"kind": "choice", "label": "Clock next to anTV", "opts": ["12-hour", "24-hour", "Off"],
             "get": lambda: {"12h": 0, "24h": 1, "off": 2}.get(c.get("clock", "12h"), 0),
             "set": lambda i: c.__setitem__("clock", ("12h", "24h", "off")[i])},
            {"kind": "toggle", "label": "Use the default backgrounds", "key": "background_default", "default": True},
            {"kind": "action", "label": "Add pictures to the default backgrounds",
             "value": lambda: "%d in folder" % len(list_images(BG_DIR)), "run": self.add_bg_pictures},
            {"kind": "action", "label": "Open the default backgrounds folder", "run": lambda: open_path(BG_DIR)},
            {"kind": "action", "label": "Background picture", "value": lambda: name_of("background"), "run": self.set_bg_image},
            {"kind": "action", "label": "Background slideshow folder", "value": lambda: name_of("background_dir"),
             "run": self.set_bg_dir},
            {"kind": "number", "label": "Change background every (0 = never)", "key": "background_interval",
             "default": 60, "min": 0, "max": 3600, "step": 5, "unit": " s"},
            {"kind": "toggle", "label": "Shuffle the slideshow", "key": "background_shuffle", "default": False},
            {"kind": "number", "label": "Start fading cards after (0 = never)", "key": "idle_delay",
             "default": 30, "min": 0, "max": 3600, "step": 5, "unit": " s"},
            {"kind": "number", "label": "Time to fade out", "key": "idle_fade", "default": 60, "min": 5, "max": 600,
             "step": 5, "unit": " s"},
            {"kind": "number", "label": "Faintest card opacity", "key": "idle_min", "default": 15, "min": 0, "max": 100,
             "step": 5, "unit": " %"}]

    def set_font(self):
        f = self.pick_font()
        if f:
            self.cfg["tile_font"] = f

    def add_bg_pictures(self):
        i = self.choose("Add pictures to the default backgrounds",
                        ["Add one picture\u2026", "Add every picture in a folder\u2026", "Cancel"])
        n = 0
        if i == 0:
            p = self.pick_path("Choose a picture to add", images=True)
            n = add_backgrounds([p]) if p else 0
        elif i == 1:
            d = self.pick_path("Choose a folder of pictures", folder=True)
            n = add_backgrounds(list_images(d)) if d else 0
        if n:
            self.cfg["background_default"] = True
            self.hub.toast("Added %d picture%s to the backgrounds folder" % (n, "" if n == 1 else "s"))

    def set_bg_image(self):
        i = self.choose("Background picture", ["Choose a picture\u2026", "Remove the picture", "Cancel"])
        if i == 0:
            path = self.pick_path("Choose a background picture", images=True)
            if path:
                self.cfg["background"] = store_image(path)
        elif i == 1:
            self.cfg.pop("background", None)

    def set_bg_dir(self):
        i = self.choose("Background slideshow folder", ["Choose a folder\u2026", "Stop using a folder", "Cancel"])
        if i == 0:
            path = self.pick_path("Choose a folder of pictures", folder=True)
            if path:
                self.cfg["background_dir"] = path
        elif i == 1:
            self.cfg.pop("background_dir", None)

    def rows_system(self):
        c = self.cfg
        disp = Gdk.Display.get_default()
        screens = ["Auto (last screen)"] + ["Screen %d  (%dx%d)" % ((i + 1,) + (lambda g: (g.width, g.height))(disp.get_monitor(i).get_geometry()))
                                            for i in range(disp.get_n_monitors())]
        rows = [{"kind": "choice", "label": "Show anTV on", "opts": screens,
                 "get": lambda: 0 if c.get("monitor") is None else min(c["monitor"] + 1, len(screens) - 1),
                 "set": lambda i: c.__setitem__("monitor", None if i == 0 else i - 1)}]
        names = [n for n, _b, _f in installed_browsers()]
        rows.append({"kind": "choice", "label": "Web browser", "opts": names,
                     "get": lambda: names.index(c["browser"]) if c.get("browser") in names else 0,
                     "set": lambda i: c.__setitem__("browser", names[i])})
        rows.append({"kind": "action", "label": "Media folders",
                     "value": lambda: "%d folders" % len(c.get("media_dirs", DEFAULT["media_dirs"])), "run": self.set_media_dirs})
        modes = ["Auto (software only for NVIDIA)", "Always software (safest)", "Hardware (fastest)"]
        rows.append({"kind": "choice", "label": "Android display (Waydroid)", "opts": modes,
                     "get": lambda: {"auto": 0, "software": 1, "hardware": 2}.get(c.get("android_display", "auto"), 0),
                     "set": lambda i: c.__setitem__("android_display", ("auto", "software", "hardware")[i])})
        rows.append({"kind": "action", "label": "Android (Waydroid) check", "run": lambda: self.hidden(self.hub.android_check)})
        return rows

    def set_media_dirs(self):
        dirs = list(self.cfg.get("media_dirs", DEFAULT["media_dirs"]))
        i = self.choose("Media folders", ["+  Add a folder\u2026"] + ["Remove  " + d for d in dirs] + ["Cancel"])
        if i == 0:
            path = self.pick_path("Add a media folder", folder=True)
            if path:
                dirs.append(path)
        elif i is not None and 1 <= i <= len(dirs):
            dirs.pop(i - 1)
        self.cfg["media_dirs"] = dirs

    def rows_devices(self):
        c = self.cfg
        return [{"kind": "action", "label": "Phone remote", "value": lambda: "On" if c.get("web_remote") else "Off",
                 "run": lambda: self.hidden(self.hub.phone_setup)},
                {"kind": "action", "label": "Remote control setup (Fire TV)", "run": lambda: self.hidden(self.hub.remote_setup)},
                {"kind": "action", "label": "Game controller setup (Xbox)", "run": lambda: self.hidden(self.hub.gamepad_setup)}]

    def rows_popups(self):
        c = self.cfg
        names = ["Top right", "Top left", "Bottom right", "Bottom left"]
        return [{"kind": "toggle", "label": "Show pop-ups from my apps", "key": "popups", "default": True},
                {"kind": "choice", "label": "Where pop-ups appear", "opts": names,
                 "get": lambda: POPUP_POSITIONS.index(c.get("popup_pos", "top-right")) if c.get("popup_pos", "top-right") in POPUP_POSITIONS else 0,
                 "set": lambda i: c.__setitem__("popup_pos", POPUP_POSITIONS[i])},
                {"kind": "number", "label": "Keep a pop-up up for (0 = until dismissed)", "key": "popup_secs",
                 "default": 20, "min": 0, "max": 300, "step": 5, "unit": " s"},
                {"kind": "toggle", "label": "Play a sound", "key": "popup_sound", "default": True},
                {"kind": "action", "label": "Pop-up sources (apps that send pop-ups)",
                 "value": lambda: self.hub.popups.status(), "run": self.set_popup_sources},
                {"kind": "action", "label": "Send a test pop-up", "run": self.hub.popups.test},
                {"kind": "toggle", "label": "Let other programs on this PC send pop-ups", "key": "popup_push", "default": False},
                {"kind": "toggle", "label": "\u2026also from other devices on my network", "key": "popup_lan", "default": False},
                {"kind": "action", "label": "Show the address and key for sending pop-ups",
                 "run": lambda: self.hidden(lambda: self.hub.show_push_info(self.hub))}]

    def set_popup_sources(self):
        srcs = list(self.cfg.get("popup_sources", []))
        auto = [s for s in self.hub.popups.sources() if s["url"] not in [origin_of(x.get("url")) for x in srcs]]
        text = ("Apps ticked \u201cShow this app's pop-ups\u201d on their card are listened to automatically"
                + (": " + ", ".join(s["name"] for s in auto) if auto else ".") )
        opts = ["+  Add a source (address)\u2026"] + ["Remove  " + x.get("url", "") for x in srcs] + ["Cancel"]
        i = choose_dialog(self, self.cfg, "Pop-up sources", opts, text)
        if i == 0:
            u = self.hidden(lambda: ask_text(self.hub, self.cfg, "Add a pop-up source",
                                             "Address of the app, for example http://localhost:3000", "http://localhost:3000"))
            if u and origin_of(u):
                srcs.append({"url": origin_of(u), "enabled": True})
        elif i is not None and 1 <= i <= len(srcs):
            srcs.pop(i - 1)
        self.cfg["popup_sources"] = srcs

    def rows_updates(self):
        c = self.cfg
        names = ["Never check", "Check and tell me", "Install automatically"]

        def upd(fn):  # the flow returns True when the person chose "Restart anTV now"
            if self.hidden(fn):
                GLib.idle_add(self.restart_after_update)
        return [{"kind": "choice", "label": "Check for updates", "opts": names,
                 "get": lambda: UPDATE_MODES.index(c.get("update_mode", "ask")) if c.get("update_mode", "ask") in UPDATE_MODES else 1,
                 "set": lambda i: c.__setitem__("update_mode", UPDATE_MODES[i])},
                {"kind": "action", "label": "GitHub repository", "value": lambda: update_repo(c) or "not set",
                 "run": lambda: self.hidden(lambda: self.hub.update_set_repo(self.hub))},
                {"kind": "action", "label": "Check for updates now", "value": lambda: self.hub.update_status(),
                 "run": lambda: upd(lambda: self.hub.update_check_flow(self.hub))},
                {"kind": "action", "label": "Install an update from a file\u2026",
                 "run": lambda: upd(lambda: self.hub.update_file_flow(self.hub))},
                {"kind": "action", "label": "Go back to the previous version",
                 "value": lambda: ("to " + backup_version(list_backups()[-1])) if list_backups() else "none saved yet",
                 "run": lambda: upd(lambda: self.hub.update_rollback_flow(self.hub))}]

    def restart_after_update(self):
        self.hub.tvs = None
        self.destroy()
        self.hub.restart_app()

    def rows_data(self):
        def restore():
            if self.hidden(self.hub.restore_data):
                GLib.idle_add(self.finish)

        def wipe():
            if self.hidden(self.hub.wipe_flow):
                GLib.idle_add(self.finish)
        return [{"kind": "action", "label": "Save a backup of my data and settings", "value": lambda: "zip file",
                 "run": lambda: self.hidden(self.hub.backup_data)},
                {"kind": "action", "label": "Restore from a backup", "run": restore},
                {"kind": "action", "label": "Delete all data and start new", "run": wipe}]

    def rows_about(self):
        return [{"kind": "action", "label": "anTV version", "value": lambda: VERSION,
                 "run": lambda: show_history(self, self.cfg)},
                {"kind": "action", "label": "What's new (version history)", "run": lambda: show_history(self, self.cfg)},
                {"kind": "action", "label": "Keyboard shortcuts", "run": lambda: show_shortcuts(self, self.cfg)},
                *self.rows_style()]

    def rows_style(self):
        return [{"kind": "toggle", "label": "TV-friendly settings (this screen)", "key": "tenft_settings", "default": False}]


TILE_SIZES = {"small": 220, "medium": 300, "large": 380, "xlarge": 480}
TILE_SHAPES = {"wide": 9 / 16, "classic": 3 / 4, "square": 1.0, "poster": 3 / 2}


def tile_dims(cfg):
    """(width, height) of every card, from the Card size and Card shape settings. All cards share it."""
    w = TILE_SIZES.get(cfg.get("tile_size", "medium"), 300)
    return w, round(w * TILE_SHAPES.get(cfg.get("tile_shape", "wide"), 9 / 16))


def is_folder(a):
    return a.get("type") == "folder"


def describe_app(a):
    t = a.get("type")
    if t == "folder":
        n = len(a.get("apps", []))
        return "%d item%s" % (n, "" if n == 1 else "s")
    if t == "node":
        return "Node.js: " + a.get("dir", "")
    if t == "android":
        return "Android: %s on %s" % (a.get("package", ""), a.get("device") or "default device")
    return a.get("url") or a.get("cmd", "")


def find_parent(apps, item):
    """The list (the main list or a folder's 'apps') that holds `item`, or None. Compared by identity."""
    for a in apps:
        if a is item:
            return apps
        if is_folder(a):
            r = find_parent(a.setdefault("apps", []), item)
            if r is not None:
                return r
    return None


def remove_item(apps, item):
    parent = find_parent(apps, item)
    if parent is not None:
        parent[:] = [a for a in parent if a is not item]
        return True
    return False


def collect_favorites(apps):
    """Every starred app or folder, at any depth, in order."""
    out = []
    for a in apps:
        if a.get("favorite"):
            out.append(a)
        if is_folder(a):
            out += collect_favorites(a.get("apps", []))
    return out


def flatten_apps(apps, prefix=""):
    """[(label, app)] for every launchable app, including those inside folders (label shows the folder path)."""
    out = []
    for a in apps:
        if is_folder(a):
            out += flatten_apps(a.get("apps", []), prefix + a["name"] + " / ")
        else:
            out.append((prefix + a["name"], a))
    return out


def folder_choices(apps, exclude=None):
    """[(label, list)] places an item can be moved to: the main screen and every folder (not `exclude` or inside it)."""
    out = [("Main screen", apps)]

    def walk(lst, prefix):
        for a in lst:
            if is_folder(a) and a is not exclude:
                sub = a.setdefault("apps", [])
                out.append((prefix + a["name"], sub))
                walk(sub, prefix + a["name"] + " / ")
    walk(apps, "")
    return out


def move_item(apps, item, dest):
    """Move `item` into the list `dest`. False if it can't go there (already there, or a folder into itself)."""
    src = find_parent(apps, item)
    if src is None or src is dest:
        return False
    if is_folder(item) and any(dest is lst for _l, lst in folder_choices(item.get("apps", []))):
        return False
    src[:] = [a for a in src if a is not item]
    dest.append(item)
    return True


def split_tiles(full, favorite_builtins, show_others, nested_favs=()):
    """full = [apps and folders..., browser, local, drives..., add, addnode, apk].
    Returns (favorites_row, main_grid). Favorites are starred apps (also ones inside folders) plus chosen built-ins;
    with no favorites everything stays in one grid. Hiding 'other apps' keeps USB drives."""
    def is_fav(a):
        sp = a.get("special")
        if sp in ("browser", "local"):
            return sp in favorite_builtins
        return sp is None and bool(a.get("favorite"))
    favs = [a for a in full if is_fav(a)] + list(nested_favs)
    ids = {id(a) for a in favs}
    rest = [a for a in full if id(a) not in ids]
    if favs and not show_others:
        rest = [a for a in rest if a.get("special") == "drive"]
    return favs, rest


class Hub(Gtk.Window):
    def __init__(self):
        super().__init__(title="anTV")
        self.cfg = load()
        seed_backgrounds()
        self.set_name("hub")
        self.last_input, self.cur_op = time.monotonic(), 1.0
        self.browser = None
        self.android_active = False
        self.path = []          # folders opened on the main screen
        self.add_target = None  # set while a settings screen is open so "add" flows add into its list
        self.update_avail, self.update_pending, self._upd_busy = None, None, False  # newer version found / installed, restart needed
        self.vm = Gio.VolumeMonitor.get()  # watches for USB drives being plugged in / removed
        for sig in ("mount-added", "mount-removed", "mount-changed"):
            self.vm.connect(sig, lambda *a: GLib.timeout_add(700, self.on_mounts))
        self.set_decorated(False)
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", self.on_key)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        root.set_border_width(60)
        title = Gtk.Label(label="anTV"); title.set_name("title"); title.set_xalign(0)
        self.cog = Gtk.Button(label="\u2699"); self.cog.set_name("cog"); self.cog.set_relief(Gtk.ReliefStyle.NONE)
        self.cog.set_valign(Gtk.Align.CENTER); self.cog.set_tooltip_text("Settings")
        self.cog.connect("clicked", lambda _b: self.settings_dialog())
        self.clock = Gtk.Label(); self.clock.set_name("clock"); self.clock.set_valign(Gtk.Align.CENTER)
        head = Gtk.Box(spacing=18)
        head.pack_start(title, False, False, 0); head.pack_start(self.cog, False, False, 0)
        head.pack_start(self.clock, False, False, 24)
        # phone-remote address + PIN + QR code; shown while the remote is on, until clicked (or press I)
        self.rb_url, self.rb_qr, self.rb_dismissed, self.rb_ips_t, self.rb_ips = None, None, False, 0.0, []
        self.rb_label = Gtk.Label(); self.rb_label.set_name("rinfo"); self.rb_label.set_xalign(0)
        self.rb_area = Gtk.DrawingArea(); self.rb_area.connect("draw", self.draw_qr)
        rbh = Gtk.Box(spacing=14); rbh.pack_start(self.rb_label, False, False, 0); rbh.pack_start(self.rb_area, False, False, 0)
        rbh.show_all()  # children must be shown now: no_show_all (below) stops the window's show_all from reaching them
        self.rbox = Gtk.EventBox(); self.rbox.add(rbh); self.rbox.set_valign(Gtk.Align.CENTER)
        self.rbox.set_tooltip_text("Click to hide"); self.rbox.set_no_show_all(True); self.rbox.set_visible(False)
        self.rbox.connect("button-press-event", lambda *_a: self.hide_remote_badge())
        head.pack_start(self.rbox, False, False, 0)
        self.upd_btn = Gtk.Button(); self.upd_btn.set_name("upd"); self.upd_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.upd_btn.set_valign(Gtk.Align.CENTER); self.upd_btn.set_no_show_all(True); self.upd_btn.set_visible(False)
        self.upd_btn.connect("clicked", lambda _b: self.update_badge_click())
        head.pack_start(self.upd_btn, False, False, 0)
        self.status = Gtk.Label(); self.status.set_name("status"); self.status.set_valign(Gtk.Align.CENTER)
        head.pack_start(self.status, False, False, 0)
        def make_flow():
            fl = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.SINGLE)
            fl.set_homogeneous(True)
            fl.set_row_spacing(24); fl.set_column_spacing(24)
            fl.set_activate_on_single_click(True)
            fl.connect("child-activated", self.on_activate)
            return fl
        self.fav_flow, self.flow = make_flow(), make_flow()
        self.flow.set_max_children_per_line(5)
        self.flow.set_min_children_per_line(3)
        self.fav_label = Gtk.Label(label="Favorites", xalign=0)
        self.all_label = Gtk.Label(label="All apps", xalign=0)
        for w in (self.fav_label, self.all_label):
            w.set_name("sect")
        self.fav_scroll = Gtk.ScrolledWindow(); self.fav_scroll.add(self.fav_flow)
        self.fav_scroll.set_propagate_natural_height(True)  # scrolls sideways (or wraps in grid mode); rebuild sets the policy
        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for w in (self.fav_label, self.fav_scroll, self.all_label, self.flow):
            self.content.pack_start(w, False, False, 0)
        sc = Gtk.ScrolledWindow(); sc.add(self.content); sc.set_vexpand(True); self.main_scroll = sc
        for w in (head, sc):
            root.pack_start(w, w is sc, True, 0)
        self.add(root)
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.SCROLL_MASK)
        for sig in ("motion-notify-event", "button-press-event", "scroll-event"):
            self.connect(sig, self.touch_event)
        self.bg_i, self.bg_t = -1, time.monotonic()
        self.bgprov = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.bgprov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.apply_bg()
        self.rebuild()
        self.place()
        GLib.timeout_add(200, self.tick)
        GLib.timeout_add_seconds(1, self.tick_clock)
        GLib.timeout_add_seconds(1, self.bg_tick)
        if IS_WIN:  # Windows: poll for USB drives and register the Ctrl+Alt+K kill hotkey
            self.win_last = [d["path"] for d in self.drives()]
            GLib.timeout_add_seconds(3, self.win_poll)
            threading.Thread(target=win_hotkey_loop, daemon=True).start()
        self.gamepad = (XInputPad if IS_WIN else Gamepad)(self)
        self.gamepad.start()
        self.web = WebRemote(self)
        self.web.apply()
        self.bg_servers = {}  # Node.js apps flagged "keep running" (their pop-up feeds need them up)
        self.popups = PopupCenter(self)
        self.popups.apply()
        threading.Thread(target=self.start_keepalive_servers, daemon=True).start()
        GLib.timeout_add_seconds(45, lambda: (update_confirm(), False)[1])  # a just-installed version that got this far is fine
        GLib.timeout_add_seconds(30, self.update_first)

    # ---- idle fade ----
    def touch(self):
        self.last_input = time.monotonic()
        if self.cur_op != 1.0:
            self.cur_op = 1.0
            self.set_cards_opacity(1.0)

    def set_cards_opacity(self, v):
        self.fav_flow.set_opacity(v)
        self.flow.set_opacity(v)

    def touch_event(self, *_):
        self.touch()
        return False

    def other_windows(self):
        """Visible anTV windows besides the main one; the pop-up card does not count."""
        return [w for w in Gtk.Window.list_toplevels()
                if w is not self and w.get_visible() and not getattr(w, "_antv_popup", False)]

    def gamepad_action(self, act):
        if self.popups.handle(act):  # a pop-up is showing and wants this button
            return
        if act in DIR_KEYS:
            name = DIR_KEYS[act]
        else:  # reuse the remote-control key for this action so every screen reacts the same way
            names = self.cfg.get("remote", {}).get(act) or REMOTE_DEFAULTS.get(act) or []
            name = names[0] if names else None
        if name and not self.send_key(Gdk.keyval_from_name(name)) and self.android_active:
            os_key(name)  # Android is in front: pass the controller / remote press to it

    def send_key(self, keyval):
        win = next((w for w in Gtk.Window.list_toplevels() if w.get_visible() and w.is_active()), None)
        if win is None and self.get_visible():
            win = self
        if win is None or win.get_window() is None or not keyval:
            return False  # no anTV window in front (an app is running)
        try:
            disp = Gdk.Display.get_default()
            ev = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
            ev.window = win.get_window(); ev.send_event = True; ev.keyval = keyval
            ev.set_device(disp.get_default_seat().get_keyboard())
            ok, keys = Gdk.Keymap.get_for_display(disp).get_entries_for_keyval(keyval)
            if ok:
                ev.hardware_keycode = keys[0].keycode; ev.group = keys[0].group
            Gtk.main_do_event(ev)
            return True
        except Exception as ex:
            print("gamepad key failed:", ex)
        return False

    def remote_key(self, act):
        """Phone-remote button (GTK thread). TV Hub windows get it directly; other apps get it through xdotool."""
        def xdo(name):
            if name:
                os_key(name)
        if act != "home" and self.popups.handle({"escape": "back", "enter": "select"}.get(act, act)):
            return False
        if act == "home":
            threading.Thread(target=kill_current, daemon=True).start()
        elif act in ("backspace", "enter"):
            xdo(EXT_KEYS[act])
        elif any(w.get_visible() for w in Gtk.Window.list_toplevels() if not getattr(w, "_antv_popup", False)):
            self.gamepad_action("back" if act == "escape" else act)  # Esc never quits anTV from a phone
        else:
            xdo(EXT_KEYS.get(act))
        return False

    def remote_launch(self, idx):
        busy = bool(self.other_windows())
        items = getattr(self, "items", [])
        if self.get_visible() and not busy and 0 <= idx < len(items) \
                and items[idx].get("special") not in ("add", "addnode", "settings"):
            self.touch()
            self.on_activate(self.flow, types.SimpleNamespace(app=items[idx]))
        return False

    def phone_setup(self):
        dlg = Gtk.Dialog(title="Phone remote", transient_for=self, modal=True)
        hook_back(dlg, self.cfg)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        box = dlg.get_content_area(); box.set_spacing(10); box.set_border_width(24)
        en = Gtk.CheckButton(label="Enable phone remote (anyone on this Wi-Fi who knows the PIN can control TV Hub)")
        en.set_active(self.cfg.get("web_remote", False))
        port = Gtk.SpinButton.new_with_range(1024, 65535, 1); port.set_value(self.cfg.get("web_port", 8765))
        pin = Gtk.Label(xalign=0)

        def show_pin():
            pin.set_markup('<span size="x-large" weight="bold">PIN: %s</span>' % (self.cfg.get("web_pin") or "(created when enabled)"))

        def new_pin(_b):
            self.cfg["web_pin"] = f"{secrets.randbelow(10 ** 6):06d}"; save(self.cfg); show_pin()
        npb = Gtk.Button(label="New PIN"); npb.connect("clicked", new_pin)
        show_pin()
        urls = [f"http://{ip}:{self.cfg.get('web_port', 8765)}" for ip in local_ips()]
        info = Gtk.Label(xalign=0, selectable=True, label=("Open on your phone:\n" + "\n".join(urls)) if urls
                         else "No network address found. Connect this PC to your Wi-Fi.")
        note = Gtk.Label(xalign=0, wrap=True, max_width_chars=70, label=(
            "Traffic is not encrypted, so use this only on a home network you trust. The PIN is required for every "
            "action and wrong guesses are locked out. If you use a firewall (ufw), allow the port. On Linux, volume uses pactl; "
            "on Linux, the touchpad uses X11 (libXtst) and typing / other-app keys need xdotool (sudo apt install xdotool)."))
        for w in (en, Gtk.Label(label="Port", xalign=0), port, pin, npb, info):
            box.pack_start(w, False, False, 2)
        if self.cfg.get("web_remote") and urls:
            try:
                import qrcode
                qp = os.path.join(CFG_DIR, "qr.png"); os.makedirs(CFG_DIR, exist_ok=True)
                qrcode.make(urls[0]).save(qp)
                box.pack_start(Gtk.Image.new_from_file(qp), False, False, 4)
            except Exception:
                box.pack_start(Gtk.Label(label="(For a QR code: sudo apt install python3-qrcode)", xalign=0), False, False, 0)
        if self.web.error:
            box.pack_start(Gtk.Label(label=self.web.error, xalign=0), False, False, 0)
        box.pack_start(note, False, False, 4)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            self.cfg["web_remote"] = en.get_active(); self.cfg["web_port"] = int(port.get_value())
            save(self.cfg); self.web.apply(); dlg.destroy()
            if self.web.error and self.cfg["web_remote"]:
                self.msg(self.web.error, Gtk.MessageType.ERROR)
        else:
            dlg.destroy()

    def tick(self):
        """Cards get more transparent the longer nothing is touched."""
        delay = float(self.cfg.get("idle_delay", 30))   # seconds before fading starts (0 = never)
        span = max(1.0, float(self.cfg.get("idle_fade", 60)))  # seconds to reach the faintest level
        low = float(self.cfg.get("idle_min", 15)) / 100.0
        # don't fade while a dialog, the media browser or another TV Hub window is up
        busy = bool(self.other_windows())
        if delay <= 0 or busy or not self.get_visible():
            op = 1.0
            if busy or not self.get_visible():
                self.last_input = time.monotonic()
        else:
            t = min(1.0, max(0.0, time.monotonic() - self.last_input - delay) / span)
            op = 1.0 - (1.0 - low) * t
        if abs(op - self.cur_op) > 0.004:
            self.cur_op = op
            self.set_cards_opacity(op)
        return True

    def data_box(self, parent, text, kind=Gtk.MessageType.INFO):
        m = Gtk.MessageDialog(transient_for=parent, message_type=kind, buttons=Gtk.ButtonsType.OK, text=text)
        tenft(m, self.cfg)
        m.run(); m.destroy()

    def refresh_all(self):
        self.path = []
        self.apply_bg(); self.rebuild(); self.place(); self.web.apply()

    def backup_data(self, parent=None):
        """Save your data and settings: a zip in a folder you choose."""
        parent = parent or self
        save(self.cfg)
        d = choose_path(parent, self.cfg, "Choose where to save the backup", folder=True)
        if not d:
            return False
        try:
            p = make_backup(d)
        except Exception as e:
            self.data_box(parent, "Couldn't save the backup:\n%s" % e, Gtk.MessageType.ERROR)
            return False
        self.data_box(parent, "Saved your data and settings to:\n\n%s\n\nBrowser logins (Netflix, Hulu...) are not "
                              "included. Settings you just changed are included once you have pressed Save." % p)
        return True

    def restore_data(self, parent=None):
        """Replace everything with a backup zip. True if it was restored."""
        parent = parent or self
        p = choose_path(parent, self.cfg, "Choose an anTV backup (.zip)", pattern="*.zip")
        if not p:
            return False
        if choose_dialog(parent, self.cfg, "Restore this backup?",
                         ["No, keep my current data", "Yes, replace my apps and settings with the backup"],
                         "This replaces your current apps, settings, card pictures and backgrounds.") != 1:
            return False
        try:
            fresh = restore_backup(p)
        except Exception as e:
            self.data_box(parent, "Couldn't restore that backup:\n%s" % e, Gtk.MessageType.ERROR)
            return False
        self.cfg.clear(); self.cfg.update(fresh)
        seed_backgrounds(); self.refresh_all()
        self.toast("Backup restored")
        return True

    def wipe_flow(self, parent=None):
        """Delete all data and start new, after two warnings. True if everything was deleted."""
        parent = parent or self
        while True:
            i = choose_dialog(parent, self.cfg, "Delete ALL anTV data?  (warning 1 of 2)",
                              ["Cancel, keep everything", "Save a backup first\u2026", "Continue"],
                              "This deletes every app card you added, all settings, card pictures, backgrounds you "
                              "added, and the saved browser logins (Netflix, Hulu, Plex...). anTV starts again as new.")
            if i is None or i == 0:
                return False
            if i == 1:
                self.backup_data(parent)
                continue
            break
        if choose_dialog(parent, self.cfg, "Are you absolutely sure?  (warning 2 of 2)",
                         ["No, keep my data", "Yes, delete everything now"],
                         "This cannot be undone. Everything will be deleted right now.") != 1:
            return False
        wipe_data()
        self.cfg.clear(); self.cfg.update(json.loads(json.dumps(DEFAULT)))
        seed_backgrounds(); save(self.cfg); self.refresh_all()
        self.toast("All data deleted. anTV is as new.")
        return True

    # ---- updates (GitHub or a file)
    def restart_app(self):
        """Quit and start anTV again (used after an update)."""
        RESTART["want"] = True
        self.quit_app()

    def update_status(self):
        if self.update_pending:
            return "restart to use %s" % self.update_pending
        if self.update_avail:
            return "%s is available" % (self.update_avail.get("version") or "a new version")
        t = update_state().get("last_check")
        return time.strftime("checked %b %d, %H:%M", time.localtime(t)) if t else "not checked yet"

    def refresh_update_badge(self):
        if self.update_pending:
            self.upd_btn.set_label("\u21bb  Restart to finish updating to %s" % self.update_pending)
        elif self.update_avail:
            self.upd_btn.set_label("\u2b06  Update %s available" % (self.update_avail.get("version") or ""))
        else:
            self.upd_btn.set_visible(False)
            return
        self.upd_btn.set_visible(True)

    def update_badge_click(self):
        if not self.upd_btn.get_visible():
            return False
        if self.update_pending:
            if choose_dialog(self, self.cfg, "Restart anTV now?", ["Yes, restart now", "Not now"],
                             "anTV %s is installed. Restarting starts it." % self.update_pending) == 0:
                self.restart_app()
        elif self.update_avail and self.update_offer(self, self.update_avail):
            self.restart_app()
        return True

    def update_first(self):
        self.update_tick()
        GLib.timeout_add_seconds(3600, self.update_tick)
        return False

    def update_tick(self):
        """Automatic check (every 12 hours while anTV is open), unless it is off, no repository is set, or an
        update is already waiting for a restart."""
        mode = self.cfg.get("update_mode", "ask")
        repo = update_repo(self.cfg)
        if (mode == "off" or not parse_repo(repo) or self._upd_busy or self.update_pending
                or time.time() - update_state().get("last_check", 0) < UPDATE_EVERY):
            return True
        self._upd_busy = True
        threading.Thread(target=self.update_bg, args=(repo, mode), daemon=True).start()
        return True

    def update_bg(self, repo, mode):
        try:
            info = github_check(repo)
            update_state_set(last_check=time.time())
            v = info.get("version")
            if v and ver_tuple(v) <= ver_tuple(VERSION):
                return
            if mode == "auto":
                pkg = read_package(http_get(info["url"]))
                if ver_tuple(pkg["version"]) > ver_tuple(VERSION):
                    GLib.idle_add(self.update_installed, install_package(pkg), True)
            else:
                GLib.idle_add(self.update_found, info)
        except Exception:
            pass  # quiet: it tries again in an hour
        finally:
            self._upd_busy = False

    def update_found(self, info):
        if not (self.update_avail and self.update_avail.get("version") == info.get("version")):
            self.update_avail = info
            self.refresh_update_badge()
            self.toast("anTV %s is available (green button, or Settings > Updates)" % (info.get("version") or ""), 20)
        return False

    def update_installed(self, r, auto=False):
        self.update_pending, self.update_avail = r["to"], None
        self.refresh_update_badge()
        self.toast(("Updated to %s. " if auto else "Installed %s. ") % r["to"] + "Restart anTV to use it.", 20)
        return False

    def update_set_repo(self, parent=None):
        parent = parent or self
        r = ask_text(parent, self.cfg, "GitHub repository",
                     "Where anTV's updates live, as owner/name (for example myname/antv).\n"
                     "Add @branch to follow a branch instead of the latest release.", update_repo(self.cfg))
        if r is None:
            return False
        if not parse_repo(r):
            self.data_box(parent, "That doesn't look like a GitHub repository.\nUse owner/name, for example myname/antv.",
                          Gtk.MessageType.ERROR)
            return False
        self.cfg["update_repo"] = r.strip()
        save(self.cfg)
        return True

    def update_check_flow(self, parent=None, repo=None):
        """Check now. Returns True if the person chose to restart anTV (after installing)."""
        parent = parent or self
        if repo is not None and repo.strip():
            if not parse_repo(repo):
                self.data_box(parent, "That doesn't look like a GitHub repository.\nUse owner/name, for example myname/antv.",
                              Gtk.MessageType.ERROR)
                return False
            self.cfg["update_repo"] = repo.strip(); save(self.cfg)
        elif not parse_repo(update_repo(self.cfg)) and not self.update_set_repo(parent):
            return False
        res = run_busy(parent, self.cfg, "Checking GitHub for updates\u2026", lambda: github_check(update_repo(self.cfg)))
        if "e" in res:
            self.data_box(parent, "Couldn't check for updates:\n\n%s" % res["e"], Gtk.MessageType.ERROR)
            return False
        update_state_set(last_check=time.time())
        return self.update_offer(parent, res["v"])

    def update_offer(self, parent, info):
        v = info.get("version")
        if v and ver_tuple(v) <= ver_tuple(VERSION):
            self.update_avail = None; self.refresh_update_badge()
            self.data_box(parent, "You're up to date.\nanTV %s is the newest version (%s)." % (VERSION, info["source"]))
            return False
        text = "You have %s.  Source: %s." % (VERSION, info["source"])
        if info.get("notes"):
            text += "\n\n" + info["notes"]
        if choose_dialog(parent, self.cfg, "anTV %s is available" % (v or "update"), ["Download and install it", "Not now"], text) != 0:
            return False
        res = run_busy(parent, self.cfg, "Downloading the update\u2026", lambda: read_package(http_get(info["url"])))
        if "e" in res:
            self.data_box(parent, "Couldn't download the update:\n\n%s" % res["e"], Gtk.MessageType.ERROR)
            return False
        pkg = res["v"]
        if ver_tuple(pkg["version"]) <= ver_tuple(VERSION):
            self.data_box(parent, "You're up to date.\nThe download holds anTV %s, and you have %s." % (pkg["version"], VERSION))
            return False
        return self.update_apply(parent, pkg)

    def update_apply(self, parent, pkg):
        res = run_busy(parent, self.cfg, "Testing and installing anTV %s\u2026" % pkg["version"], lambda: install_package(pkg))
        if "e" in res:
            self.data_box(parent, "The update was not installed:\n\n%s" % res["e"], Gtk.MessageType.ERROR)
            return False
        r = res["v"]
        self.update_installed(r)
        text = "anTV %s is installed (it replaced %s, which is kept so you can go back)." % (r["to"], r["from"])
        if r["extra"]:
            text += "\n%d other file%s updated." % (r["extra"], "" if r["extra"] == 1 else "s")
        if r["skipped"]:
            text += "\nCouldn't write: " + ", ".join(r["skipped"][:4])
        return choose_dialog(parent, self.cfg, "Updated to %s" % r["to"], ["Restart anTV now", "Later (it starts the next time)"], text) == 0

    def update_file_flow(self, parent=None):
        """Install from a tvhub.py or an all-files zip you pick. True if the person chose to restart."""
        parent = parent or self
        p = choose_path(parent, self.cfg, "Choose an anTV update (tvhub.py or the all-files .zip)")
        if not p:
            return False
        try:
            if os.path.getsize(p) > UPDATE_MAX:
                raise UpdateError("That file is too big to be an anTV update.")
            with open(p, "rb") as f:
                pkg = read_package(f.read())
        except (OSError, UpdateError) as e:
            self.data_box(parent, "Can't use that file:\n\n%s" % e, Gtk.MessageType.ERROR)
            return False
        v, extra = pkg["version"], len(pkg["files"]) - 1
        more = ("\nIt also holds %d other file%s (setup scripts, Tasks app, backgrounds...)." % (extra, "" if extra == 1 else "s")) if extra else ""
        if ver_tuple(v) <= ver_tuple(VERSION):
            ok = choose_dialog(parent, self.cfg, "This file is not newer", ["No, keep anTV %s" % VERSION, "Install %s anyway" % v],
                               "The file holds anTV %s and you have %s.%s" % (v, VERSION, more)) == 1
        else:
            ok = choose_dialog(parent, self.cfg, "Install anTV %s?" % v, ["Yes, install it", "Cancel"],
                               "You have %s. The version you have now is kept so you can go back.%s" % (VERSION, more)) == 0
        return self.update_apply(parent, pkg) if ok else False

    def update_rollback_flow(self, parent=None):
        """Go back to the version that was replaced last. True if the person chose to restart."""
        parent = parent or self
        bks = list_backups()
        if not bks:
            self.data_box(parent, "There is no earlier version saved yet.\nOne is saved each time anTV updates itself.")
            return False
        v = backup_version(bks[-1])
        if choose_dialog(parent, self.cfg, "Go back to anTV %s?" % v, ["No, keep this version", "Yes, go back to %s" % v],
                         "You have %s. Your apps and settings stay as they are." % VERSION) != 1:
            return False
        try:
            rollback_update()
        except UpdateError as e:
            self.data_box(parent, "Couldn't go back:\n\n%s" % e, Gtk.MessageType.ERROR)
            return False
        self.update_pending, self.update_avail = v, None
        self.refresh_update_badge()
        return choose_dialog(parent, self.cfg, "Back to %s" % v, ["Restart anTV now", "Later"],
                             "anTV %s is back in place. Restart to use it." % v) == 0

    def hide_to_taskbar(self):
        """Minimize anTV to the taskbar; click it there to bring it back."""
        self.iconify()
        return False

    def quit_app(self):
        self.destroy()  # the destroy handler ends the program

    def bg_css(self):
        return "scrolledwindow,viewport,flowbox{background:transparent;}"

    def bg_files(self):
        """Images for the background: the chosen folder, else the single chosen picture, else the default
        backgrounds folder (unless 'Use the default backgrounds' is off)."""
        d = self.cfg.get("background_dir")
        if d and os.path.isdir(d):
            return list_images(d)
        b = self.cfg.get("background")
        if b and os.path.isfile(b):
            return [b]
        if self.cfg.get("background_default", True):
            return list_images(BG_DIR)
        return []

    def apply_bg(self, advance=False):
        files = self.bg_files()
        self.bg_t = time.monotonic()
        if not files:
            self.bgprov.load_from_data(b"")
            return
        n, shuffle = len(files), self.cfg.get("background_shuffle", False)
        i = self.bg_i if 0 <= self.bg_i < n else (random.randrange(n) if shuffle else 0)
        if advance:
            if n <= 1:
                return
            i = random.choice([k for k in range(n) if k != i]) if shuffle else (i + 1) % n
        self.bg_i = i
        uri = Gio.File.new_for_path(files[i]).get_uri()  # slight dark overlay keeps titles readable
        css = ('#hub{background-color:#0b0d12;background-image:linear-gradient(rgba(0,0,0,.3),rgba(0,0,0,.3)),'
               'url("%s");background-size:cover;background-position:center;}' % uri)
        self.bgprov.load_from_data(css.encode())

    def bg_tick(self):
        iv = int(self.cfg.get("background_interval", 60))  # seconds between images; 0 = never change
        if iv > 0 and self.get_visible() and time.monotonic() - self.bg_t >= iv:
            self.apply_bg(advance=True)
        return True

    # ---- layout ----
    def all_children(self):
        return self.fav_flow.get_children() + self.flow.get_children()

    def focus_child(self):
        return self.fav_flow.get_focus_child() or self.flow.get_focus_child()

    def hide_remote_badge(self):
        self.rb_dismissed = True
        self.rbox.set_visible(False)
        return True

    def draw_qr(self, w, cr):
        m = self.rb_qr
        if not m:
            return False
        n, q = len(m), 2
        s = max(1, min(w.get_allocated_width(), w.get_allocated_height()) // (n + 2 * q))
        cr.set_source_rgb(1, 1, 1); cr.paint(); cr.set_source_rgb(0, 0, 0)
        for y, row in enumerate(m):
            for x, v in enumerate(row):
                if v:
                    cr.rectangle((x + q) * s, (y + q) * s, s, s)
        cr.fill()
        return False

    def refresh_remote_badge(self):
        web = getattr(self, "web", None)
        on = bool(self.cfg.get("web_remote")) and web is not None and web.httpd is not None
        url = None
        if on:
            if time.monotonic() - self.rb_ips_t > 15:  # name lookups can be slow, so not every second
                self.rb_ips, self.rb_ips_t = local_ips(), time.monotonic()
            if self.rb_ips:
                url = f"http://{self.rb_ips[0]}:{web.port}"
        else:
            self.rb_dismissed = False  # turning the remote off and on again shows it again
        if url != self.rb_url:
            self.rb_url = url
            self.rb_qr = qr_matrix(url) if url else None
            if url:
                px = max(3, 130 // (len(self.rb_qr) + 4)) * (len(self.rb_qr) + 4) if self.rb_qr else 1
                self.rb_area.set_size_request(px, px)
            self.rb_area.queue_draw()
        if url:
            self.rb_label.set_text(f"Phone remote\n{url.split('//')[1]}\nPIN {self.cfg.get('web_pin', '')}")
        self.rbox.set_visible(bool(url) and not self.rb_dismissed)

    def tick_clock(self):
        self.refresh_remote_badge()
        mode = self.cfg.get("clock", "12h")
        if mode == "off":
            text = ""
        elif mode == "24h":
            text = time.strftime("%H:%M")
        else:
            text = time.strftime("%I:%M %p").lstrip("0")
        if text != self.clock.get_text():
            self.clock.set_text(text)
        return True

    def on_tile_focus(self, child, _event):
        """Keep the focused card on screen (sideways in the favorites row, up/down in the page)."""
        if child.get_parent() is self.fav_flow:
            pos = child.translate_coordinates(self.fav_flow, 0, 0)
            if pos:
                self.fav_scroll.get_hadjustment().clamp_page(pos[0] - 40, pos[0] + child.get_allocated_width() + 40)
        pos = child.translate_coordinates(self.content, 0, 0)
        if pos:
            self.main_scroll.get_vadjustment().clamp_page(pos[1] - 20, pos[1] + child.get_allocated_height() + 20)
        return False

    def nav(self, k):
        """Arrow keys between the settings cog, the favorites row and the main grid."""
        if self.cog.has_focus():
            if k == "Down":
                kids = self.all_children()
                if kids:
                    kids[0].grab_focus()
            return True  # arrows never wander off the cog
        f = self.focus_child()
        if f is None:
            return False
        top = self.fav_flow if self.fav_scroll.get_visible() else self.flow
        if k == "Up" and f.get_parent() is top:
            if f.get_allocation().y == min(c.get_allocation().y for c in top.get_children()):
                self.cog.grab_focus()
                return True
        return self.edge_move(k)

    def edge_move(self, k):
        """Up/Down between the favorites row and the main grid (FlowBox only moves inside itself)."""
        f = self.focus_child()
        if f is None or not self.fav_scroll.get_visible():
            return False
        in_fav = f.get_parent() is self.fav_flow
        src, dst = (self.fav_flow, self.flow) if in_fav else (self.flow, self.fav_flow)
        y = f.get_allocation().y
        ys = [c.get_allocation().y for c in src.get_children()]
        if (k == "Down" and in_fav and y == max(ys)) or (k == "Up" and not in_fav and y == min(ys)):
            cand = dst.get_children()
            if not cand:
                return False
            pick = min if dst is self.flow else max
            ty = pick(c.get_allocation().y for c in cand)
            x = f.get_allocation().x
            min((c for c in cand if c.get_allocation().y == ty),
                key=lambda c: abs(c.get_allocation().x - x)).grab_focus()
            return True
        return False

    def cur_apps(self):
        """The list new cards go into: a settings screen's list, the open folder, or the main screen."""
        if self.add_target is not None:
            return self.add_target()
        return self.path[-1].setdefault("apps", []) if self.path else self.cfg["apps"]

    def open_folder(self, folder):
        self.path.append(folder)
        self.rebuild(0)

    def up_folder(self):
        if self.path:
            child = self.path.pop()
            self.rebuild(child)

    def rebuild(self, focus=0):
        """focus: index into favorites-then-main order, or an app dict to focus."""
        for fl in (self.fav_flow, self.flow):
            for c in fl.get_children():
                fl.remove(c)
        css = ("window{background:#0b0d12;} #title{color:white;font-size:56px;font-weight:bold;}"
               "#hint{color:#7d8590;font-size:20px;} #sect{color:#9aa4b2;font-size:26px;font-weight:bold;}"
               "#cog{background:transparent;border:none;box-shadow:none;color:#d6deee;font-size:34px;padding:2px 14px;border-radius:26px;}"
               "#cog:hover,#cog:focus{background:#2a6df4;color:white;}#clock{color:#e8eef9;font-size:38px;font-weight:bold;}#status{color:#9ecbff;font-size:26px;font-weight:bold;}#rinfo{color:#9ecbff;font-size:22px;font-weight:bold;}"
               "#upd{background:#1f6f43;border:none;box-shadow:none;color:white;font-size:26px;font-weight:bold;padding:4px 18px;border-radius:22px;}"
               "#upd:hover,#upd:focus{background:#2a9d5c;}"
               "flowboxchild{padding:0;border-radius:18px;}"
               "flowboxchild:focus,flowboxchild:selected{outline:5px solid white;background:transparent;}"
               + self.font_css() + self.bg_css())
        SPECIAL = {"addnode": ("+  Node.js app", "#3c873a"), "browser": ("Web Browser", "#5b6cff"),
                   "local": ("Local Media", "#3b4a63"), "add": ("+  Add app", "#222733"),
                   "apk": ("+  Install APK", "#2e8b57"), "up": ("\u25c2  Back", "#222733")}
        tw, th = tile_dims(self.cfg)
        drv = self.drives()
        flat = flatten_apps(self.cfg["apps"])
        builtin = [("Web Browser", {"special": "browser"}), ("Local Media", {"special": "local"})] + [(d["name"], d) for d in drv]
        self.items = [a for _l, a in flat] + [a for _l, a in builtin]  # what the phone remote can launch (folders opened up)
        self.item_labels = [l for l, _a in flat] + [l for l, _a in builtin]
        show_others = self.cfg.get("show_others", True)
        if self.path:  # inside a folder: just its contents
            favs, main = [], [{"special": "up"}] + list(self.path[-1].get("apps", [])) + [{"special": "add"}]
        else:
            full = (self.cfg["apps"] + [{"special": "browser"}, {"special": "local"}] + drv
                    + [{"special": "add"}, {"special": "addnode"}, {"special": "apk"}])
            root_ids = {id(a) for a in self.cfg["apps"]}
            nested = [a for a in collect_favorites(self.cfg["apps"]) if id(a) not in root_ids]
            favs, main = split_tiles(full, self.cfg.get("favorite_builtins", []), show_others, nested)
        tiles = [(self.fav_flow, a) for a in favs] + [(self.flow, a) for a in main]
        for i, (fl, a) in enumerate(tiles):
            sp = SPECIAL.get(a.get("special"))
            lab = Gtk.Label(); lab.set_justify(Gtk.Justification.CENTER); lab.set_line_wrap(True)
            if sp:
                lab.set_text(sp[0])
            elif is_folder(a):
                n = len(a.get("apps", []))
                lab.set_markup("\u25a4  %s\n<span size=\"small\">%d item%s</span>" % (GLib.markup_escape_text(a["name"]), n, "" if n == 1 else "s"))
            else:
                lab.set_text(a["name"])
            if a.get("picture_only") and a.get("image") and os.path.isfile(a["image"]):
                lab.set_text("")  # picture-only card: the picture stands in for the card
            box = Gtk.EventBox(); box.add(lab); box.set_size_request(tw, th)
            box.get_style_context().add_class("tile"); box.set_name(f"t{i}")
            css += f"#t{i}{{{self.tile_bg(a, sp[1] if sp else a['color'])}border-radius:18px;}}"
            child = Gtk.FlowBoxChild(); child.add(box); child.app = a
            child.connect("focus-in-event", self.on_tile_focus)
            fl.add(child)
        if self.cfg.get("fav_layout") == "grid":  # wrap onto several rows so every favorite is on screen
            self.fav_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
            per = max(1, min(len(favs), 5))
        else:  # one long row that scrolls sideways when it doesn't fit
            self.fav_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
            per = max(1, len(favs))
        self.fav_flow.set_max_children_per_line(per)
        self.fav_flow.set_min_children_per_line(per)
        self.css.load_from_data(css.encode())
        self.all_label.set_text("\u25a4  " + "  \u203a  ".join(f["name"] for f in self.path) if self.path else "All apps")
        self.show_all()
        for w in (self.fav_label, self.fav_scroll):
            w.set_visible(bool(favs))
        for c in self.fav_flow.get_children():
            c.show_all()
        self.all_label.set_visible(bool(self.path) or (bool(favs) and show_others))
        kids = self.all_children()
        if isinstance(focus, dict):
            idx = next((j for j, c in enumerate(kids) if c.app is focus), 0)
        else:
            idx = min(focus, len(kids) - 1)
        kids[idx].grab_focus()
        self.touch()
        self.tick_clock()

    def place(self):
        d = Gdk.Display.get_default()
        n = d.get_n_monitors()
        m = self.cfg.get("monitor")
        self.mon_idx = (n - 1 if m is None else m) % n
        self.mon = d.get_monitor(self.mon_idx)
        self.fullscreen_on_monitor(Gdk.Screen.get_default(), self.mon_idx)

    # ---- actions ----
    def on_key(self, _w, e):
        k = Gdk.keyval_name(e.keyval)
        self.touch()
        if k in ("Up", "Down", "Left", "Right") and self.nav(k):
            return True
        if k in ("i", "I") and self.rbox.get_visible():
            return self.hide_remote_badge()
        if k in ("u", "U") and self.upd_btn.get_visible():
            return self.update_badge_click()
        act = remote_action(self.cfg, k)
        if act in ("select", "playpause"):
            f = self.focus_child()
            if self.cog.has_focus():
                self.settings_dialog()
            elif f is not None:
                self.on_activate(self.flow, f)
            return True
        if act == "menu":
            self.settings_dialog()
            return True
        if act == "back":
            if self.path:
                self.up_folder()
            return True  # Back on the home screen does nothing (Esc quits)
        if k in ("Escape", "q", "BackSpace") and self.path:
            self.up_folder()
        elif k in ("Escape", "q"):
            Gtk.main_quit()
        elif k in ("h", "H"):
            self.hide_to_taskbar()
        elif k == "F1":
            n = Gdk.Display.get_default().get_n_monitors()
            self.cfg["monitor"] = (self.mon_idx + 1) % n
            save(self.cfg); self.place()
        elif k in ("a", "A"):
            self.add_menu()
        elif k in ("s", "S"):
            self.settings_dialog()
        elif k in ("n", "N"):
            self.add_dialog("node")
        elif k in ("i", "I"):
            self.install_apk()
        elif k in ("b", "B"):
            self.pick_browser()
        elif k in ("e", "E"):
            f = self.focus_child()
            if f is not None and f.app.get("special") == "drive":
                eject_drive(f.app["path"])
        elif k == "Delete":
            f = self.focus_child()
            if f is not None and "special" not in f.app:
                if is_folder(f.app) and f.app.get("apps") and choose_dialog(
                        self, self.cfg, "Remove %s?" % f.app["name"],
                        ["Yes, remove the folder and everything in it", "No, keep it"]) != 0:
                    return True
                idx = self.all_children().index(f)
                remove_item(self.cfg["apps"], f.app); save(self.cfg)
                self.rebuild(idx)
        else:
            return False
        return True

    def on_activate(self, _fb, child):
        sp = child.app.get("special")
        if sp == "add":
            self.add_menu()
        elif sp == "settings":
            self.settings_dialog()
        elif sp == "addnode":
            self.add_dialog("node")
        elif sp == "apk":
            self.install_apk()
        elif sp == "browser":
            self.open_browser()
        elif sp == "local":
            roots = self.local_roots()
            if roots:
                Browser(self, roots)
            else:
                m = Gtk.MessageDialog(transient_for=self, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
                                      text="No media folders found. Add some in Settings.")
                m.run(); m.destroy()
        elif sp == "drive":
            Browser(self, [child.app["path"]])
        elif sp == "up":
            self.up_folder()
        elif is_folder(child.app):
            self.open_folder(child.app)
        else:
            self.launch(child.app)

    def pick_browser(self):
        """Card-style picker of installed browsers; saves the choice. Returns the name or None."""
        avail = installed_browsers()
        if not avail:
            m = Gtk.MessageDialog(transient_for=self, message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.OK,
                                  text="No web browser found. Install one, e.g.  sudo apt install firefox")
            m.run(); m.destroy(); return None
        dlg = Gtk.Dialog(title="Choose your web browser", transient_for=self, modal=True)
        hook_back(dlg, self.cfg)
        box = dlg.get_content_area(); box.set_spacing(10); box.set_border_width(24)
        cur = self.cfg.get("browser")
        for i, (name, _b, _f) in enumerate(avail):
            b = Gtk.Button(label=("\u2713  " if name == cur else "") + name)
            b.set_size_request(380, 64); b.connect("clicked", lambda _b, i=i: dlg.response(i))
            box.pack_start(b, False, False, 0)
        dlg.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dlg.show_all(); r = dlg.run(); dlg.destroy()
        if 0 <= r < len(avail):
            self.cfg["browser"] = avail[r][0]; save(self.cfg)
            return avail[r][0]
        return None

    def open_browser(self):
        avail = {n: (b, f) for n, b, f in installed_browsers()}
        name = self.cfg.get("browser")
        if name not in avail:
            name = self.pick_browser()
            if not name:
                return
            avail = {n: (b, f) for n, b, f in installed_browsers()}
        binary, fam = avail[name]
        g = self.mon.get_geometry()
        prof = os.path.join(CFG_DIR, "profiles", "browse-" + "".join(c for c in name if c.isalnum()).lower())
        os.makedirs(prof, exist_ok=True)  # own profile: keeps your logins here and lets the kill hotkey work
        url = self.cfg.get("home_url", "https://duckduckgo.com")
        after = None
        if fam == "chromium":
            cmd = [binary, f"--user-data-dir={prof}", f"--window-position={g.x},{g.y}",
                   f"--window-size={g.width},{g.height}", "--start-fullscreen", "--no-first-run",
                   "--autoplay-policy=no-user-gesture-required", url]
        else:
            cmd = [binary, "--new-instance", "--profile", prof, url]
            if shutil.which("xdotool"):  # Firefox can't pick a monitor itself; move its window
                def after(proc):
                    threading.Thread(target=lambda: subprocess.run(
                        ["xdotool", "search", "--sync", "--onlyvisible", "--pid", str(proc.pid),
                         "windowmove", str(g.x), str(g.y), "windowsize", str(g.width), str(g.height)],
                        stderr=subprocess.DEVNULL), daemon=True).start()
        self.run_cmd(cmd, prof, self, after)

    def font_css(self):
        fd = Pango.FontDescription(self.cfg.get("tile_font") or "Sans Bold 26")
        scale = min(1.6, max(0.7, tile_dims(self.cfg)[0] / 300.0))  # text follows the card size
        size = ((fd.get_size() / Pango.SCALE) or 26) * scale
        style = "normal" if fd.get_style() == Pango.Style.NORMAL else "italic"
        return (f'.tile label{{color:white;font-family:"{fd.get_family() or "Sans"}";font-size:{size:.1f}pt;'
                f'font-weight:{int(fd.get_weight())};font-style:{style};text-shadow:0 2px 6px black;}}')

    def tile_bg(self, a, color):
        css = f"background-color:{color};"
        img = a.get("image")
        if img and os.path.isfile(img):
            uri = Gio.File.new_for_path(img).get_uri()
            size = "contain" if self.cfg.get("picture_fit") == "fit" else "cover"  # same card size either way
            if a.get("picture_only"):
                css += (f'background-image:url("{uri}");background-size:{size};'
                        'background-repeat:no-repeat;background-position:center;')
            else:  # dark overlay keeps the name readable
                css += (f'background-image:linear-gradient(rgba(0,0,0,.35),rgba(0,0,0,.35)),url("{uri}");'
                        f'background-size:100% 100%,{size};background-repeat:no-repeat,no-repeat;'
                        'background-position:center,center;')
        return css

    def remote_setup(self):
        """Pair help, live key viewer, and Learn buttons for remote buttons (Amazon Fire TV remote etc.)."""
        dlg = Gtk.Dialog(title="Remote setup", transient_for=self, modal=True)
        tenft(dlg, self.cfg)
        dlg.add_button("Close", Gtk.ResponseType.CLOSE)
        box = dlg.get_content_area(); box.set_spacing(10); box.set_border_width(24)
        intro = Gtk.Label(wrap=True, xalign=0, max_width_chars=70, label=(
            "Amazon Fire TV remote: hold the Home button for about 10 seconds until the LED blinks, then "
            "pair it in Mint's Bluetooth settings. It then acts like a keyboard: D-pad = arrows, Select = Enter.\n\n"
            "Press any remote button to see its key name. Click Learn to assign a button. Buttons like volume, "
            "power, or app shortcuts may not send anything to the PC."))
        seen = Gtk.Label(label="Last key seen: (press a remote button)", xalign=0)
        box.pack_start(intro, False, False, 0); box.pack_start(seen, False, False, 6)
        learning, labels = {"act": None}, {}

        def refresh():
            m = self.cfg.get("remote", {})
            for act, lab in labels.items():
                lab.set_text(", ".join(m.get(act, REMOTE_DEFAULTS[act])) or "(not set)")

        def on_key(_w, e):
            k = Gdk.keyval_name(e.keyval)
            seen.set_text(f"Last key seen: {k}")
            act = learning["act"]
            if act and k:
                self.cfg.setdefault("remote", {})[act] = [k]; save(self.cfg)
                learning["act"] = None; refresh()
                if act == "home":
                    ok = install_hotkey(os.path.abspath(__file__), [k])
                    seen.set_text(f"Home = {k}" + ("" if ok else "  (couldn't set the system hotkey; see terminal)"))
                else:
                    seen.set_text(f"{REMOTE_LABELS[act]} = {k}")
                return True
            return False
        dlg.connect("key-press-event", on_key)

        def learn(act):
            learning["act"] = act
            seen.set_text(f"Now press the remote button for: {REMOTE_LABELS[act]}\u2026")

        def reset(act):
            self.cfg.get("remote", {}).pop(act, None); save(self.cfg); refresh()
            if act == "home":
                install_hotkey(os.path.abspath(__file__), [])

        for act in REMOTE_DEFAULTS:
            row = Gtk.Box(spacing=12)
            name = Gtk.Label(label=REMOTE_LABELS[act], xalign=0); name.set_size_request(280, -1)
            labels[act] = Gtk.Label(xalign=0); labels[act].set_size_request(200, -1)
            b1, b2 = Gtk.Button(label="Learn"), Gtk.Button(label="Reset")
            b1.connect("clicked", lambda _b, a=act: learn(a)); b2.connect("clicked", lambda _b, a=act: reset(a))
            for w in (name, labels[act], b1, b2):
                row.pack_start(w, False, False, 0)
            box.pack_start(row, False, False, 0)
        refresh(); dlg.show_all(); dlg.run(); dlg.destroy()

    def gamepad_setup(self):
        """Controller status, live input viewer, and Learn buttons (button numbers vary by driver)."""
        gp = self.gamepad
        dlg = Gtk.Dialog(title="Controller setup (Xbox)", transient_for=self, modal=True)
        hook_back(dlg, self.cfg)
        dlg.add_button("Close", Gtk.ResponseType.CLOSE)
        box = dlg.get_content_area(); box.set_spacing(10); box.set_border_width(24)
        status = Gtk.Label(label=gp.status(), xalign=0, wrap=True, max_width_chars=70)
        intro = Gtk.Label(wrap=True, xalign=0, max_width_chars=70, label=(
            "Wired Xbox controllers work over USB. Bluetooth: hold the pair button on top until the Xbox button "
            "flashes fast, then pair it in Mint's Bluetooth settings. The Xbox wireless USB adapter needs the "
            "separate 'xone' driver.\n\nMove the controller to see the input name below. Click Learn to assign "
            "a button. Defaults assume the Linux xpad layout; other drivers number buttons differently."))
        if IS_WIN:
            intro.set_text("Xbox controllers use Windows' built-in XInput: plug it in by USB, or hold the pair button "
                           "until the Xbox button flashes fast and pair it in Windows Bluetooth settings.\n\nMove the "
                           "controller to see the input name below. Click Learn to assign a button.")
        seen = Gtk.Label(label="Last input: (press a button)", xalign=0)
        for w in (status, intro, seen):
            box.pack_start(w, False, False, 4)
        learning, labels = {"act": None}, {}

        def refresh():
            for act, lab in labels.items():
                lab.set_text(", ".join(gp_map(self.cfg)[act]) or "(not set)")

        def on_learn(spec):
            act = learning["act"]
            if not act:
                return
            m = self.cfg.setdefault("gamepad", {})
            for other, specs in gp_map(self.cfg).items():  # one input = one action
                if other != act and spec in specs:
                    m[other] = [x for x in specs if x != spec]
            m[act] = [spec]; save(self.cfg)
            learning["act"] = None; gp.learn_cb = None
            seen.set_text(f"{GAMEPAD_LABELS[act]} = {spec}"); refresh()

        def learn(act):
            learning["act"] = act; gp.learn_cb = on_learn
            seen.set_text(f"Now press the controller button for: {GAMEPAD_LABELS[act]}\u2026")

        def reset(act):
            self.cfg.get("gamepad", {}).pop(act, None); save(self.cfg); refresh()

        gp.watch = lambda spec: None if learning["act"] else seen.set_text(f"Last input: {spec}")
        for act in GAMEPAD_DEFAULTS:
            row = Gtk.Box(spacing=12)
            name = Gtk.Label(label=GAMEPAD_LABELS[act], xalign=0); name.set_size_request(280, -1)
            labels[act] = Gtk.Label(xalign=0); labels[act].set_size_request(160, -1)
            b1, b2 = Gtk.Button(label="Learn"), Gtk.Button(label="Reset")
            b1.connect("clicked", lambda _b, a=act: learn(a)); b2.connect("clicked", lambda _b, a=act: reset(a))
            for w in (name, labels[act], b1, b2):
                row.pack_start(w, False, False, 0)
            box.pack_start(row, False, False, 0)
        tid = GLib.timeout_add(1000, lambda: (status.set_text(gp.status()), True)[1])
        refresh(); dlg.show_all(); dlg.run()
        GLib.source_remove(tid); gp.watch = gp.learn_cb = None
        dlg.destroy()

    def msg(self, text, kind=Gtk.MessageType.INFO):
        m = Gtk.MessageDialog(transient_for=self, message_type=kind, buttons=Gtk.ButtonsType.OK, text=text)
        tenft(m, self.cfg)
        m.run(); m.destroy()

    def launch_node(self, a):
        folder = os.path.expanduser(a.get("dir", ""))
        if not os.path.isdir(folder):
            return self.msg(f"Project folder not found:\n{folder}", Gtk.MessageType.ERROR)
        if not node_present():
            how = ("Install it from https://nodejs.org (or: winget install OpenJS.NodeJS.LTS)" if IS_WIN
                   else "Install it with:  sudo apt install nodejs npm\n"
                        "(If you use nvm, start TV Hub from a terminal after loading it.)")
            return self.msg("Node.js isn't installed.\n" + how, Gtk.MessageType.ERROR)
        cancel = threading.Event()
        splash = Splash(self, cancel)
        splash.set_text(f"Starting {a['name']}\u2026")
        self.hide()
        threading.Thread(target=self.node_worker, args=(a, folder, cancel, splash), daemon=True).start()

    def node_worker(self, a, folder, cancel, splash):
        """Install deps if needed -> start server -> wait for its port -> open in kiosk browser -> stop server on exit."""
        say = lambda t: GLib.idle_add(splash.set_text, t)
        slug = "".join(c for c in a["name"] if c.isalnum()).lower() or "node"
        os.makedirs(os.path.join(CFG_DIR, "logs"), exist_ok=True)
        log_path = os.path.join(CFG_DIR, "logs", slug + ".log")
        log = open(log_path, "w")
        try:
            os.remove(KILLED)
        except OSError:
            pass
        pgids, match, err = [], None, None
        url = a.get("url") or "http://localhost:3000"
        u = urlparse(url)
        host, port = u.hostname or "localhost", u.port or (443 if u.scheme == "https" else 80)

        def save_state():  # lets the Ctrl+Alt+K hotkey kill the server and browser at any stage
            with open(STATE, "w") as f:
                json.dump({"pgids": pgids, "match": match}, f)

        def spawn(cmd, **kw):
            p = subprocess.Popen(cmd, cwd=folder, stdout=log, stderr=subprocess.STDOUT, **NEWGRP, **kw)
            pgids.append(p.pid); save_state()
            return p

        try:
            if os.path.isfile(os.path.join(folder, "package.json")) and not os.path.isdir(os.path.join(folder, "node_modules")):
                say(f"Installing {a['name']} dependencies\u2026\nthis can take a few minutes")
                p = spawn(shell_cmd("npm install"))
                while p.poll() is None:
                    if cancel.is_set():
                        raise InterruptedError
                    time.sleep(0.3)
                if p.returncode < 0 or os.path.exists(KILLED):  # stopped by the hotkey
                    raise InterruptedError
                if p.returncode != 0:
                    raise RuntimeError("npm install failed")
            say(f"Starting {a['name']}\u2026")
            env = dict(os.environ, BROWSER="none")  # stop dev servers from opening their own browser
            if u.port:
                env["PORT"] = str(u.port)
            if a.get("keepalive"):  # the server belongs to anTV, not to this window: reuse it or start it detached
                server = None if self.port_open(host, port) else self.start_background_server(a)
            else:
                server = spawn(shell_cmd(a.get("cmd") or "node server.js"), env=env)
            deadline = time.time() + float(a.get("wait", 60))
            while True:
                if cancel.is_set():
                    raise InterruptedError
                if server is not None and server.poll() is not None:
                    if server.returncode < 0 or os.path.exists(KILLED):
                        raise InterruptedError
                    raise RuntimeError("The server exited right after starting.")
                try:
                    socket.create_connection((host, port), timeout=1).close()
                    break
                except OSError:
                    pass
                if time.time() > deadline:
                    raise RuntimeError(f"Timed out waiting for {url}")
                time.sleep(0.5)
            cmd, match = self.command_for({"type": "web", "name": a["name"], "url": url})
            browser = spawn(cmd)
            GLib.timeout_add(2000, splash.destroy)
            browser.wait()
        except InterruptedError:
            pass
        except Exception as ex:
            err = str(ex)
        finally:
            for force in (False, True):
                for g in pgids:
                    kill_tree(g, force)
                if not force:
                    time.sleep(1)
            log.close()
            try:
                os.remove(STATE)
            except OSError:
                pass
        GLib.idle_add(self.node_done, splash, err, log_path)

    def show_push_info(self, parent):
        cfg = self.cfg
        if not cfg.get("popup_token"):
            cfg["popup_token"] = secrets.token_urlsafe(16); save(cfg)
        port = int(cfg.get("popup_port", 8767))
        host = (local_ips() or ["localhost"])[0] if cfg.get("popup_lan") else "127.0.0.1"
        state = ("Listening." if self.popups.push else "Turned off (or could not start).") + \
                (" " + self.popups.push_error if self.popups.push_error else "")
        show_text(parent, cfg, "Push address", "Send pop-ups to anTV",
                  "Address:  http://%s:%d/notify\nHeader:   X-Antv-Token: %s\n\n%s\n\n"
                  "POST JSON such as {\"app\":\"My app\",\"title\":\"Hello\",\"body\":\"From a script\"}.\n"
                  "Full details: anTV_Popup_Protocol_Spec.md" % (host, port, cfg["popup_token"], state))

    def node_paths(self, a):
        url = a.get("url") or "http://localhost:3000"
        u = urlparse(url)
        slug = "".join(c for c in a["name"] if c.isalnum()).lower() or "node"
        return url, u, u.hostname or "localhost", u.port or (443 if u.scheme == "https" else 80), slug

    @staticmethod
    def port_open(host, port):
        try:
            socket.create_connection((host, port), timeout=1).close()
            return True
        except OSError:
            return False

    def start_background_server(self, a):
        """Start a 'keep running' Node.js app's server unless something already answers on its port.
        Returns the Popen (or None if it was already up / could not start). Runs in a worker thread."""
        url, u, host, port, slug = self.node_paths(a)
        folder = os.path.expanduser(a.get("dir", ""))
        if self.port_open(host, port) or not os.path.isdir(folder) or not node_present():
            return None
        os.makedirs(os.path.join(CFG_DIR, "logs"), exist_ok=True)
        env = dict(os.environ, BROWSER="none")
        if u.port:
            env["PORT"] = str(u.port)
        log = open(os.path.join(CFG_DIR, "logs", slug + ".log"), "a")
        p = subprocess.Popen(shell_cmd(a.get("cmd") or "node server.js"), cwd=folder, env=env, stdout=log,
                             stderr=subprocess.STDOUT, **NEWGRP)
        self.bg_servers[slug] = p
        return p

    def start_keepalive_servers(self):
        for _l, a in flatten_apps(self.cfg.get("apps", [])):
            if a.get("type") == "node" and a.get("keepalive"):
                try:
                    self.start_background_server(a)
                except Exception as ex:
                    print("background server failed:", ex)

    def stop_bg_servers(self):
        for p in list(self.bg_servers.values()):
            if p.poll() is None:
                kill_tree(p.pid)
        self.bg_servers.clear()

    def open_source_app(self, source, origin):
        """The pop-up's Open button: stop whatever is running and launch the app card the pop-up came from."""
        app = next((a for _l, a in flatten_apps(self.cfg.get("apps", []))
                    if (origin and origin_of(a.get("url")) == origin) or a.get("name") == source), None)
        if app is None:
            return self.toast("No app card found for %s" % source)

        def work():
            if os.path.exists(STATE):
                kill_current(); time.sleep(3)  # let the running app's launcher finish and the home screen return
            GLib.idle_add(self.launch, app)
        threading.Thread(target=work, daemon=True).start()

    def node_done(self, splash, err, log_path):
        try:
            splash.destroy()
        except Exception:
            pass
        self.back()
        if err:
            try:
                tail = "".join(open(log_path).readlines()[-12:])
            except OSError:
                tail = ""
            self.msg(f"{err}\n\n{tail}\nFull log: {log_path}", Gtk.MessageType.ERROR)
        return False

    def toast(self, text, secs=6):
        self.status.set_text(text)
        if getattr(self, "_toast_id", None):
            GLib.source_remove(self._toast_id)
        self._toast_id = GLib.timeout_add_seconds(secs, self._clear_toast)

    def _clear_toast(self):
        self.status.set_text(""); self._toast_id = None
        return False

    def launch_android(self, a):
        if a.get("device") == "waydroid":
            return self.launch_waydroid(a)
        self.toast("Launching %s\u2026" % a["name"])

        def work():
            ok, out = android_launch(a.get("device"), a.get("package", ""))
            GLib.idle_add(self.launch_android_done, a, ok, out)
        threading.Thread(target=work, daemon=True).start()

    def launch_android_done(self, a, ok, out):
        if ok:
            self.toast("%s is open on %s" % (a["name"], "this PC (Waydroid)" if a.get("device") == "waydroid"
                                            else (a.get("device") or "your Android device")))
        else:
            self.toast("")
            self.msg("Couldn't open %s.\n\n%s\n\nCheck that the device is on, on the same network, and that ADB debugging "
                     "is enabled." % (a["name"], (out or "").splitlines()[-1] if out else "No answer from the device."),
                     Gtk.MessageType.ERROR)
        return False

    def launch_waydroid(self, a):
        problem = waydroid_problem(self.cfg)
        if problem:
            return self.msg(problem + "\n\nSettings > System > Android check shows the details.", Gtk.MessageType.WARNING)
        cancel = threading.Event()
        splash = Splash(self, cancel)
        splash.set_text("Starting Android\u2026")
        g = self.mon.get_geometry()
        self.hide()
        threading.Thread(target=self.waydroid_worker, args=(a, cancel, splash, (g.x, g.y, g.width, g.height)),
                         daemon=True).start()

    def waydroid_worker(self, a, cancel, splash, geom):
        """Start weston + Android, open the app, wait until the window is closed (or the close-app hotkey), then clean up."""
        say = lambda t: GLib.idle_add(splash.set_text, t)
        os.makedirs(os.path.join(CFG_DIR, "logs"), exist_ok=True)
        log_path = os.path.join(CFG_DIR, "logs", "waydroid.log")
        log = open(log_path, "w")
        try:
            os.remove(KILLED)
        except OSError:
            pass
        sess, err = AndroidSession(self.cfg, log), None
        self.android_active = True
        try:
            sess.start(geom, fullscreen=True, say=say, cancel=cancel)
            say("Opening %s\u2026" % a["name"])
            sess.launch_app(a.get("package", ""), cancel)
            GLib.timeout_add(1500, splash.destroy)
            sess.wait()
        except InterruptedError:
            pass
        except Exception as ex:
            err = str(ex)
        finally:
            self.android_active = False
            sess.stop()
            log.close()
        GLib.idle_add(self.node_done, splash, None if os.path.exists(KILLED) else err, log_path)

    def android_check(self):
        res = run_busy(self, self.cfg, "Checking your Android setup\u2026", lambda: android_report(self.cfg))
        show_text(self, self.cfg, "Android (Waydroid) check", "Android check", res.get("v") or res.get("e", ""))

    def add_card(self, card, note=None):
        self.cur_apps().append(card)
        save(self.cfg); self.rebuild(card)
        self.toast(note or "Added %s" % card["name"])

    def add_menu(self):
        """One place for everything you can add."""
        i = choose_dialog(self, self.cfg, "Add an app", ["Popular apps and links (YouTube, FreeBirth\u2026)", "A website or program\u2026",
                                                         "A folder to organize apps\u2026", "A Node.js app\u2026",
                                                         "An Android APK\u2026", "Cancel"])
        if i == 0:
            self.quick_add()
        elif i == 1:
            self.add_dialog("web")
        elif i == 2:
            self.add_dialog("folder")
        elif i == 3:
            self.add_dialog("node")
        elif i == 4:
            self.install_apk()

    def quick_add(self):
        cfg = self.cfg
        keys, options = ["youtube"], ["YouTube   (youtube.com/tv in the kiosk browser)"]
        if not IS_WIN:
            keys.append("freetube"); options.append("FreeTube   (ad-free YouTube desktop app, Flatpak)")
        keys += ["piped", "smarttube"]
        options += ["Piped / Invidious   (privacy YouTube websites)", "SmartTube   (Android app, runs in Waydroid)"]
        for n, (nm, url, _c) in enumerate(POPULAR_LINKS):
            keys.append("link%d" % n); options.append("%s   (%s)" % (nm, url.split("//", 1)[-1]))
        keys.append("cancel"); options.append("Cancel")
        i = choose_dialog(self, cfg, "Popular apps", options,
                          "These add a card for you. Nothing is downloaded except by the apps themselves.")
        if i is None or keys[i] == "cancel":
            return
        key = keys[i]
        if key == "youtube":
            if any(a["name"] == "YouTube" for _l, a in flatten_apps(cfg["apps"])):
                return self.msg("You already have a YouTube card.")
            self.add_card({"name": "YouTube", "type": "web", "url": "https://www.youtube.com/tv", "color": "#ff0000"})
        elif key.startswith("link"):
            nm, url, col = POPULAR_LINKS[int(key[4:])]
            if any(a["name"] == nm for _l, a in flatten_apps(cfg["apps"])):
                return self.msg("You already have a %s card." % nm)
            self.add_card({"name": nm, "type": "web", "url": url, "color": col})
        elif key == "freetube":
            fid = "io.freetubeapp.FreeTube"
            if not shutil.which("flatpak") or subprocess.run(["flatpak", "info", fid], capture_output=True).returncode != 0:
                return self.msg("FreeTube isn't installed. Install it, then add it again:\n\n  sudo apt install flatpak\n"
                                "  flatpak install flathub " + fid)
            self.add_card({"name": "FreeTube", "type": "cmd", "cmd": "flatpak run " + fid, "color": "#2f6fed"})
        elif key == "piped":
            url = ask_text(self, cfg, "Piped or Invidious", "Address of the Piped or Invidious site you use\n(for example https://piped.example.com):")
            if url:
                if not url.startswith("http"):
                    url = "https://" + url
                self.add_card({"name": "Piped", "type": "web", "url": url, "color": "#e6734f"})
        elif key == "smarttube":
            self.msg("SmartTube isn't in any app store. Download its APK from the author's own GitHub releases page "
                     "(not from APK websites), and put it in your Downloads folder or on a USB stick.\n\n"
                     "Next, anTV will install it into Waydroid and add a SmartTube card.")
            self.install_apk(waydroid_only=True)

    def pick_android_target(self):
        """Choose where to install: a device adb can see, a new device by IP, or Waydroid. -> ('adb', serial) / ('waydroid', None) / None"""
        cfg = self.cfg
        help_text = ("Fire TV / Android TV: turn on ADB debugging in Developer options (and allow apps from unknown "
                     "sources), then connect by IP address. Android phone: turn on USB debugging and plug it in. "
                     "An Android emulator is usually at 127.0.0.1:5555.")

        def look():
            for h in cfg.get("android_hosts", []):
                adb_connect(h)
            return adb_devices()
        while True:
            devs = run_busy(self, cfg, "Looking for Android devices\u2026", look).get("v") or []
            options, actions = [], []
            for d in devs:
                note = {"device": "", "unauthorized": "   (accept the prompt on the device)", "offline": "   (offline)"}[d["state"]]
                options.append("%s  (%s)%s" % (d["model"] or "Android device", d["serial"], note)); actions.append(("dev", d))
            options.append("Connect to a device by IP address\u2026"); actions.append(("ip", None))
            if waydroid_available():
                options.append("This PC (Waydroid)"); actions.append(("waydroid", None))
            options += ["Search again", "Cancel"]; actions += [("again", None), ("cancel", None)]
            i = choose_dialog(self, cfg, "Install on which device?", options, help_text)
            if i is None or actions[i][0] == "cancel":
                return None
            kind, d = actions[i]
            if kind == "again":
                continue
            if kind == "waydroid":
                problem = waydroid_problem(cfg)
                if problem:
                    self.msg(problem, Gtk.MessageType.WARNING)
                    continue
                return ("waydroid", None)
            if kind == "ip":
                addr = ask_text(self, cfg, "Connect to a device", "IP address of the device (for example 192.168.1.50):",
                                (cfg.get("android_hosts") or [""])[-1])
                if addr:
                    if ":" not in addr:
                        addr += ":5555"
                    ok, out = run_busy(self, cfg, "Connecting to %s\u2026" % addr, lambda: adb_connect(addr)).get("v", (False, ""))
                    if ok:
                        hosts = cfg.setdefault("android_hosts", [])
                        if addr not in hosts:
                            hosts.append(addr); save(cfg)
                    else:
                        self.msg("Couldn't connect to %s.\n\n%s\n\nIs ADB debugging turned on, and is it on the same network?"
                                 % (addr, out or "No answer."), Gtk.MessageType.ERROR)
                continue
            if d["state"] != "device":
                self.msg("That device hasn't allowed this PC yet. Look at its screen and choose Allow (tick 'Always allow'), then try again.")
                continue
            return ("adb", d["serial"])

    def pick_apk(self):
        cfg = self.cfg
        roots = [os.path.expanduser("~/Downloads"), os.path.expanduser("~/Desktop")] + [d["path"] for d in self.drives()]
        apks = run_busy(self, cfg, "Looking for APK files\u2026",
                        lambda: find_apks([r for r in roots if os.path.isdir(r)])).get("v") or []
        options = ["%s   (%s)" % (os.path.basename(a), os.path.basename(os.path.dirname(a)) or a) for a in apks]
        options += ["Browse for a file\u2026", "Cancel"]
        i = choose_dialog(self, cfg, "Which APK?", options,
                          "APK files found in Downloads, Desktop and USB drives:" if apks
                          else "No APK files found in Downloads, Desktop or on USB drives.")
        if i is None or i == len(options) - 1:
            return None
        if i < len(apks):
            return apks[i]
        dlg = Gtk.FileChooserDialog(title="Choose an APK", transient_for=self, action=Gtk.FileChooserAction.OPEN)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Choose", Gtk.ResponseType.OK)
        hook_back(dlg, cfg)
        flt = Gtk.FileFilter(); flt.set_name("Android apps (.apk)"); flt.add_pattern("*.apk"); flt.add_pattern("*.APK")
        dlg.add_filter(flt); dlg.set_default_size(1100, 760)
        r = dlg.run(); path = dlg.get_filename() if r == Gtk.ResponseType.OK else None
        dlg.destroy()
        return path

    def install_apk(self, waydroid_only=False):
        """Pick a device, pick an APK, install it, and offer to add a card that launches it."""
        cfg = self.cfg
        if not waydroid_only and find_adb() is None and not waydroid_available():
            return self.msg("anTV needs Android's adb tool to install APKs.\n\nLinux Mint:  sudo apt install adb\n"
                            "Windows:  run Setup-TVHub.bat again and say yes to the Android tools "
                            "(or: winget install Google.PlatformTools)", Gtk.MessageType.WARNING)
        if waydroid_only:
            problem = waydroid_problem(cfg)
            if problem:
                return self.msg(problem + "\n\nSettings > System > Android check shows the details.", Gtk.MessageType.WARNING)
            target = ("waydroid", None)
        else:
            target = self.pick_android_target()
        if not target:
            return
        apk = self.pick_apk()
        if not apk:
            return
        kind, serial = target
        where = "this PC (Waydroid)" if kind == "waydroid" else serial
        g = self.mon.get_geometry()
        geom = (g.x + 60, g.y + 60, 960, 540)
        res = run_busy(self, cfg, "Installing %s on %s\u2026\nThis can take a minute." % (os.path.basename(apk), where),
                       (lambda: waydroid_install_in_session(cfg, apk, geom)) if kind == "waydroid" else (lambda: android_install(serial, apk)))
        if "e" in res:
            return self.msg("The install failed: " + res["e"], Gtk.MessageType.ERROR)
        ok, out, pkg = res["v"]
        if not ok:
            return self.msg("The install didn't work:\n\n" + ((out or "").splitlines()[-1] if out else "No answer from the device.")
                            + "\n\nSplit or bundle files (.apks, .xapk, .apkm) can't be installed this way.", Gtk.MessageType.ERROR)
        if not pkg:
            return self.msg("Installed on %s. (It updated an app that was already there, so no new card was made.)" % where)
        guess = "SmartTube" if "smarttube" in pkg.lower() else pkg.split(".")[-1].replace("_", " ").replace("-", " ").title()
        name = ask_text(self, cfg, "Installed", "Installed %s on %s.\n\nName for a new anTV card that opens it (Cancel = no card):" % (pkg, where), guess)
        if name:
            self.add_card({"name": name, "type": "android", "package": pkg,
                           "device": "waydroid" if kind == "waydroid" else serial, "color": "#3ddc84"}, "Added %s" % name)
        else:
            self.toast("Installed %s" % pkg)

    def local_roots(self):
        dirs = self.cfg.get("media_dirs", DEFAULT["media_dirs"])
        return [p for p in (os.path.expanduser(d) for d in dirs) if os.path.isdir(p)]

    def win_poll(self):
        cur = [d["path"] for d in self.drives()]
        if cur != self.win_last:
            self.win_last = cur
            self.on_mounts()
        return True

    def drives(self):
        if IS_WIN:
            return [{"special": "drive", "name": "USB  " + label, "path": root, "color": "#2e7d5b"}
                    for root, label in win_removable_drives()]
        out, seen = [], set()
        for m in self.vm.get_mounts():
            root = m.get_root().get_path()
            drv = m.get_drive()
            if not root or root in seen or m.is_shadowed():
                continue
            if root.startswith(("/media/", "/run/media/")) or (drv and drv.is_removable()):
                seen.add(root)
                out.append({"special": "drive", "name": "USB  " + m.get_name(), "path": root, "color": "#2e7d5b"})
        return out

    def on_mounts(self):
        """A drive was plugged in or removed: refresh tiles and jump to the new drive."""
        if self.browser and not all(os.path.isdir(r) for r in self.browser.roots):
            self.browser.close_win()
        if self.get_visible():
            old = {c.app.get("path") for c in self.all_children()}
            f = self.focus_child()
            self.rebuild(self.all_children().index(f) if f is not None else 0)
            for c in self.all_children():
                if c.app.get("special") == "drive" and c.app["path"] not in old:
                    c.grab_focus()
        return False  # one-shot timer

    def app_form(self, app=None):
        """Add/edit form for Website, Command, Node.js, Android apps and Folders. Returns a dict or None."""
        app = app or {}
        typ = app.get("type", "web")
        dlg = Gtk.Dialog(title="Edit" if app.get("name") else "Add", transient_for=self, modal=True)
        hook_back(dlg, self.cfg)
        dlg.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        name = Gtk.Entry(text=app.get("name", ""))
        kind = Gtk.ComboBoxText()
        for t in ("Website (opens in kiosk browser)", "Command (local program)", "Node.js app (runs a local server)",
                  "Android app (opens on a connected device)", "Folder (holds other apps)"):
            kind.append_text(t)
        kind.set_active({"web": 0, "cmd": 1, "node": 2, "android": 3, "folder": 4}.get(typ, 0))
        dev = Gtk.Entry(text=app.get("device", ""))
        dev.set_placeholder_text("192.168.1.50:5555, a device serial, or waydroid")
        target = Gtk.Entry(text=app.get("url", "") if typ == "web" else app.get("package", "") if typ == "android" else app.get("cmd") or ("node server.js" if typ == "node" else ""))
        folder = Gtk.FileChooserButton(title="Choose the Node.js project folder", action=Gtk.FileChooserAction.SELECT_FOLDER)
        if app.get("dir") and os.path.isdir(app["dir"]):
            folder.set_filename(app["dir"])
        node_url = Gtk.Entry(text=app.get("url", "http://localhost:3000") if typ == "node" else "http://localhost:3000")
        state = {"img": app.get("image")}
        fc = Gtk.FileChooserButton(title="Choose a picture", action=Gtk.FileChooserAction.OPEN)
        flt = Gtk.FileFilter(); flt.set_name("Images"); flt.add_pixbuf_formats(); fc.add_filter(flt)
        if state["img"] and os.path.isfile(state["img"]):
            fc.set_filename(state["img"])
        fc.connect("file-set", lambda b: state.update(img=b.get_filename()))
        clear = Gtk.Button(label="None")
        clear.connect("clicked", lambda _b: (state.update(img=None), fc.unselect_all()))
        imgbox = Gtk.Box(spacing=8); imgbox.pack_start(fc, True, True, 0); imgbox.pack_start(clear, False, False, 0)
        color = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.parse(app.get("color", {"node": "#3c873a", "folder": "#7a6cff"}.get(typ, "#3a6ea5"))); color.set_rgba(rgba)
        fav = Gtk.CheckButton(label="Show in the favorites row (top of the main screen)")
        fav.set_active(bool(app.get("favorite")))
        pic_only = Gtk.CheckButton(label="Show only the picture (hide the name)")
        pic_only.set_active(bool(app.get("picture_only")))
        pop_cb = Gtk.CheckButton(label="Show this app's pop-ups (reminders, alerts) on top of other apps")
        pop_cb.set_active(bool(app.get("popups")))
        keep_cb = Gtk.CheckButton(label="Keep its server running in the background (needed for pop-ups when it is closed)")
        keep_cb.set_active(bool(app.get("keepalive")))
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, margin=24)
        tlabel = Gtk.Label(xalign=1)
        rows = [(Gtk.Label(label="Name", xalign=1), name), (Gtk.Label(label="Type", xalign=1), kind),
                (tlabel, target), (Gtk.Label(label="Project folder", xalign=1), folder),
                (Gtk.Label(label="Open at (URL)", xalign=1), node_url),
                (Gtk.Label(label="Card color", xalign=1), color), (Gtk.Label(label="Picture", xalign=1), imgbox),
                (Gtk.Label(label="Favorite", xalign=1), fav), (Gtk.Label(label="Device", xalign=1), dev),
                (Gtk.Label(label="", xalign=1), pic_only),
                (Gtk.Label(label="Pop-ups", xalign=1), pop_cb), (Gtk.Label(label="", xalign=1), keep_cb)]
        for r, (l, w) in enumerate(rows):
            grid.attach(l, 0, r, 1, 1); grid.attach(w, 1, r, 1, 1)
        name.set_size_request(380, -1)

        def sync(*_):
            k = kind.get_active()
            tlabel.set_text(("URL", "Command", "Start command", "Package name", "")[k])
            cur = target.get_text().strip()
            if k == 2 and not cur:
                target.set_text("node server.js")  # the default for Node.js apps
            elif k != 2 and cur == "node server.js":
                target.set_text("")
            target.set_placeholder_text(("https://example.com", "kodi --fullscreen", "node server.js  (or: npm start)",
                                         "com.example.app", "")[k])
            for i, v in {2: k != 4, 3: k == 2, 4: k == 2, 8: k == 3, 10: k in (0, 2), 11: k == 2}.items():
                rows[i][0].set_visible(v); rows[i][1].set_visible(v)
        kind.connect("changed", sync)
        dlg.get_content_area().add(grid); dlg.show_all(); sync()
        result = None
        if dlg.run() == Gtk.ResponseType.OK and name.get_text().strip():
            t, k, c = target.get_text().strip(), kind.get_active(), color.get_rgba()
            base = {"name": name.get_text().strip(), "favorite": fav.get_active(), "picture_only": pic_only.get_active(),
                    "color": "#%02x%02x%02x" % tuple(round(v * 255) for v in (c.red, c.green, c.blue))}
            fix = lambda u: u if u.startswith("http") else "https://" + u
            if pop_cb.get_active() and k in (0, 2):
                base["popups"] = True
            if keep_cb.get_active() and k == 2:
                base["keepalive"] = True
            if k == 0 and t:
                result = {**base, "type": "web", "url": fix(t)}
            elif k == 1 and t:
                result = {**base, "type": "cmd", "cmd": t}
            elif k == 3 and t:
                result = {**base, "type": "android", "package": t, "device": dev.get_text().strip()}
            elif k == 2 and folder.get_filename():
                result = {**base, "type": "node", "dir": folder.get_filename(), "cmd": t or "node server.js",
                          "url": fix(node_url.get_text().strip() or "http://localhost:3000")}
            elif k == 4:  # a folder keeps what is already inside it
                result = {**base, "type": "folder", "apps": app.get("apps", []) if typ == "folder" else []}
        if result and state["img"] and os.path.isfile(state["img"]):
            result["image"] = store_image(state["img"])
        dlg.destroy()
        return result

    def add_dialog(self, kind="web"):
        new = self.app_form({"type": kind})
        if new:
            self.add_card(new)

    def tv_settings(self):
        if getattr(self, "tvs", None) is None:
            self.tvs = TVSettings(self)

    def settings_dialog(self):
        if self.cfg.get("tenft_settings"):
            return self.tv_settings()
        dlg = Gtk.Dialog(title="anTV settings", transient_for=self, modal=True)
        hook_back(dlg, self.cfg)
        HIDE_R, QUIT_R, DONE_R, RESTART_R = 100, 101, 102, 103
        dlg.add_buttons("Quit anTV", QUIT_R, "Hide anTV", HIDE_R, "Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.OK)
        dlg.set_default_size(1100, 760)  # 25% wider than before

        # ---- Apps tab: the list (with folders) and its buttons
        apps = copy.deepcopy(self.cfg["apps"])
        stack = []  # folders opened in this list
        store = Gtk.ListStore(str, str, str)
        tree = Gtk.TreeView(model=store)
        for i, t in enumerate(("\u2605", "Name", "Opens")):
            tree.append_column(Gtk.TreeViewColumn(t, Gtk.CellRendererText(ypad=6), text=i))
        path_lab = Gtk.Label(xalign=0)

        def cur_list():
            return stack[-1].setdefault("apps", []) if stack else apps

        def refill(sel=0):
            store.clear()
            lst = cur_list()
            for a in lst:
                store.append(["\u2605" if a.get("favorite") else "", ("\u25a4  " if is_folder(a) else "") + a["name"], describe_app(a)])
            path_lab.set_text("Main screen" + "".join("  \u203a  " + f["name"] for f in stack))
            if lst:
                tree.get_selection().select_path(Gtk.TreePath(max(0, min(sel, len(lst) - 1))))

        def selected():
            m, it = tree.get_selection().get_selected()
            lst = cur_list()
            i = m.get_path(it)[0] if it else None
            return (i, lst[i]) if i is not None and i < len(lst) else (None, None)

        def add(_b):
            n = self.app_form()
            if n:
                cur_list().append(n); refill(len(cur_list()) - 1)

        def new_folder(_b):
            n = self.app_form({"type": "folder"})
            if n:
                cur_list().append(n); refill(len(cur_list()) - 1)

        def open_sel(*_):
            i, a = selected()
            if a is not None and is_folder(a):
                stack.append(a); refill(0)

        def up(_b):
            if stack:
                child = stack.pop()
                refill(next((j for j, x in enumerate(cur_list()) if x is child), 0))

        def edit(*_):
            i, a = selected()
            if a is not None:
                n = self.app_form(a)
                if n:
                    cur_list()[i] = n; refill(i)

        def activate_row(*_):
            i, a = selected()
            if a is not None and is_folder(a):
                open_sel()
            else:
                edit()

        def remove(_b):
            i, a = selected()
            if a is None:
                return
            if is_folder(a) and a.get("apps") and choose_dialog(
                    self, self.cfg, "Remove %s?" % a["name"], ["Yes, remove the folder and everything in it", "No, keep it"]) != 0:
                return
            cur_list().pop(i); refill(i)

        def move(d):
            i, a = selected()
            lst = cur_list()
            if a is not None and 0 <= i + d < len(lst):
                lst[i], lst[i + d] = lst[i + d], lst[i]; refill(i + d)

        def move_to(_b):
            i, a = selected()
            if a is None:
                return
            lst = cur_list()
            dests = [d for d in folder_choices(apps, exclude=a) if d[1] is not lst]
            k = choose_dialog(self, self.cfg, "Move %s to\u2026" % a["name"], [d[0] for d in dests] + ["Cancel"])
            if k is not None and k < len(dests):
                move_item(apps, a, dests[k][1]); refill(min(i, max(0, len(cur_list()) - 1)))

        def reset(_b):
            apps[:] = [dict(a) for a in DEFAULT["apps"]]; stack.clear(); refill()

        def toggle_fav(_b):
            i, a = selected()
            if a is not None:
                a["favorite"] = not a.get("favorite", False); refill(i)

        def hub_add(fn):  # run one of the main screen's add flows so it adds into this list
            def go(_b):
                self.add_target = cur_list
                try:
                    fn()
                finally:
                    self.add_target = None
                    refill(max(0, len(cur_list()) - 1))
            return go

        tree.connect("row-activated", activate_row)
        sc = Gtk.ScrolledWindow(); sc.add(tree); sc.set_size_request(700, 380); sc.set_hexpand(True); sc.set_vexpand(True)
        bgrid = Gtk.Grid(column_spacing=10, row_spacing=10)
        for n, (label, fn) in enumerate((
                ("Add\u2026", add), ("New folder\u2026", new_folder),
                ("Popular apps\u2026", hub_add(self.quick_add)), ("Install APK\u2026", hub_add(self.install_apk)),
                ("Open folder", open_sel), ("Up one folder", up), ("Edit\u2026", edit), ("Remove", remove),
                ("Toggle \u2605 favorite", toggle_fav), ("Move to folder\u2026", move_to),
                ("Move up", lambda b: move(-1)), ("Move down", lambda b: move(1)), ("Reset to defaults", reset))):
            b = Gtk.Button(label=label); b.connect("clicked", fn); b.set_size_request(190, -1)
            bgrid.attach(b, n % 2, n // 2, 1, 1)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left.pack_start(path_lab, False, False, 0); left.pack_start(sc, True, True, 0)
        apps_page = Gtk.Box(spacing=18, margin=24)
        apps_page.pack_start(left, True, True, 0); apps_page.pack_start(bgrid, False, False, 0)

        # ---- Main screen tab
        fav_lay = Gtk.ComboBoxText()
        for t in ("Scroll sideways when there are many", "Grid: show them all"):
            fav_lay.append_text(t)
        fav_lay.set_active(1 if self.cfg.get("fav_layout") == "grid" else 0)
        fav_b = Gtk.CheckButton(label="Favorites row: include Web Browser")
        fav_b.set_active("browser" in self.cfg.get("favorite_builtins", []))
        fav_l = Gtk.CheckButton(label="Favorites row: include Local Media")
        fav_l.set_active("local" in self.cfg.get("favorite_builtins", []))
        show_o = Gtk.CheckButton(label="Show the other apps below the favorites row")
        show_o.set_active(self.cfg.get("show_others", True))
        clk = Gtk.ComboBoxText()
        for t in ("12-hour", "24-hour", "Off"):
            clk.append_text(t)
        clk.set_active({"12h": 0, "24h": 1, "off": 2}.get(self.cfg.get("clock", "12h"), 0))

        tsz = Gtk.ComboBoxText()
        for t in ("Small", "Medium", "Large", "Extra large"):
            tsz.append_text(t)
        tsz.set_active(("small", "medium", "large", "xlarge").index(self.cfg.get("tile_size", "medium"))
                       if self.cfg.get("tile_size", "medium") in TILE_SIZES else 1)
        tsh = Gtk.ComboBoxText()
        for t in ("Wide (16:9)", "Classic (4:3)", "Square", "Poster (2:3)"):
            tsh.append_text(t)
        tsh.set_active(("wide", "classic", "square", "poster").index(self.cfg.get("tile_shape", "wide"))
                       if self.cfg.get("tile_shape", "wide") in TILE_SHAPES else 0)
        pfit = Gtk.ComboBoxText()
        for t in ("Fill the card (crop to fit)", "Fit the whole picture"):
            pfit.append_text(t)
        pfit.set_active(1 if self.cfg.get("picture_fit") == "fit" else 0)

        # ---- Look tab
        font = Gtk.FontButton.new_with_font(self.cfg.get("tile_font") or "Sans Bold 26")
        font.set_show_size(True)
        bgs = {"img": self.cfg.get("background")}
        bfc = Gtk.FileChooserButton(title="Choose a background graphic", action=Gtk.FileChooserAction.OPEN)
        bflt = Gtk.FileFilter(); bflt.set_name("Images"); bflt.add_pixbuf_formats(); bfc.add_filter(bflt)
        if bgs["img"] and os.path.isfile(bgs["img"]):
            bfc.set_filename(bgs["img"])
        bfc.connect("file-set", lambda b: bgs.update(img=b.get_filename()))
        bclear = Gtk.Button(label="None")
        bclear.connect("clicked", lambda _b: (bgs.update(img=None), bfc.unselect_all()))
        bbox = Gtk.Box(spacing=8); bbox.pack_start(bfc, True, True, 0); bbox.pack_start(bclear, False, False, 0)
        bgd = {"dir": self.cfg.get("background_dir")}
        dfc = Gtk.FileChooserButton(title="Choose a folder of background images", action=Gtk.FileChooserAction.SELECT_FOLDER)
        if bgd["dir"] and os.path.isdir(bgd["dir"]):
            dfc.set_filename(bgd["dir"])
        dfc.connect("file-set", lambda b: bgd.update(dir=b.get_filename()))
        dclear = Gtk.Button(label="None")
        dclear.connect("clicked", lambda _b: (bgd.update(dir=None), dfc.unselect_all()))
        dbox = Gtk.Box(spacing=8); dbox.pack_start(dfc, True, True, 0); dbox.pack_start(dclear, False, False, 0)
        def_cb = Gtk.CheckButton(label="Use the default backgrounds (when no picture or folder is chosen above)")
        def_cb.set_active(self.cfg.get("background_default", True))
        addbg = Gtk.Button(label="Add pictures to the default backgrounds\u2026")
        def add_pics(_b):
            f = Gtk.FileChooserDialog(title="Add pictures to the default backgrounds", transient_for=dlg,
                                      action=Gtk.FileChooserAction.OPEN)
            f.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK)
            f.set_select_multiple(True); f.set_default_size(1000, 700)
            flt = Gtk.FileFilter(); flt.set_name("Images"); flt.add_pixbuf_formats(); f.add_filter(flt)
            names = f.get_filenames() if f.run() == Gtk.ResponseType.OK else []
            f.destroy()
            if names:
                added = add_backgrounds(names)
                def_cb.set_active(True)
                self.toast("Added %d picture%s to the backgrounds folder" % (added, "" if added == 1 else "s"))
        addbg.connect("clicked", add_pics)
        openbg = Gtk.Button(label="Open the default backgrounds folder")
        openbg.connect("clicked", lambda _b: open_path(BG_DIR))
        sp_int = Gtk.SpinButton.new_with_range(0, 86400, 5); sp_int.set_value(self.cfg.get("background_interval", 60))
        shuf = Gtk.CheckButton(label="Shuffle the folder's images"); shuf.set_active(self.cfg.get("background_shuffle", False))
        sp_delay = Gtk.SpinButton.new_with_range(0, 3600, 5); sp_delay.set_value(self.cfg.get("idle_delay", 30))
        sp_fade = Gtk.SpinButton.new_with_range(5, 600, 5); sp_fade.set_value(self.cfg.get("idle_fade", 60))
        sp_min = Gtk.SpinButton.new_with_range(0, 100, 5); sp_min.set_value(self.cfg.get("idle_min", 15))

        # ---- System tab
        disp = Gdk.Display.get_default()
        mon = Gtk.ComboBoxText(); mon.append_text("Auto (last monitor)")
        for i in range(disp.get_n_monitors()):
            g = disp.get_monitor(i).get_geometry()
            mon.append_text(f"Monitor {i + 1}  ({g.width}x{g.height})")
        m = self.cfg.get("monitor")
        mon.set_active(0 if m is None else min(m + 1, disp.get_n_monitors()))
        br = Gtk.ComboBoxText()
        names = [n for n, _b, _f in installed_browsers()]
        for n in names:
            br.append_text(n)
        br.set_active(names.index(self.cfg["browser"]) if self.cfg.get("browser") in names else 0)
        media = Gtk.Entry(text="; ".join(self.cfg.get("media_dirs", DEFAULT["media_dirs"])))
        pb = Gtk.Button(label="Phone remote (control from your phone)\u2026")
        pb.connect("clicked", lambda _b: self.phone_setup())
        rb = Gtk.Button(label="Remote setup (Amazon Fire TV remote)\u2026")
        rb.connect("clicked", lambda _b: self.remote_setup())
        gb = Gtk.Button(label="Controller setup (Xbox)\u2026")
        gb.connect("clicked", lambda _b: self.gamepad_setup())
        disp_mode = Gtk.ComboBoxText()
        for t in ("Auto (software display only for NVIDIA)", "Always software (safest)", "Hardware (fastest, may fail on NVIDIA)"):
            disp_mode.append_text(t)
        disp_mode.set_active({"auto": 0, "software": 1, "hardware": 2}.get(self.cfg.get("android_display", "auto"), 0))
        ab = Gtk.Button(label="Android (Waydroid) check\u2026")
        ab.connect("clicked", lambda _b: self.android_check())

        # ---- Pop-ups tab
        pu_on = Gtk.CheckButton(label="Show pop-ups from my apps on top of whatever is running")
        pu_on.set_active(self.cfg.get("popups", True))
        pu_pos = Gtk.ComboBoxText()
        for t in ("Top right", "Top left", "Bottom right", "Bottom left"):
            pu_pos.append_text(t)
        cur_pos = self.cfg.get("popup_pos", "top-right")
        pu_pos.set_active(POPUP_POSITIONS.index(cur_pos) if cur_pos in POPUP_POSITIONS else 0)
        pu_secs = Gtk.SpinButton.new_with_range(0, 300, 5); pu_secs.set_value(self.cfg.get("popup_secs", 20))
        pu_snd = Gtk.CheckButton(label="Play a sound"); pu_snd.set_active(self.cfg.get("popup_sound", True))
        pu_src = {"list": [dict(x) for x in self.cfg.get("popup_sources", [])]}
        pu_src_lab = Gtk.Label(xalign=0, wrap=True, max_width_chars=60)

        def src_text():
            pu_src_lab.set_text("Extra sources: " + (", ".join(x.get("url", "") for x in pu_src["list"]) or "none")
                                + "\n(Apps with \u201cShow this app's pop-ups\u201d ticked in their card are listened to automatically.)")
        src_text()

        def add_src(_b):
            u = ask_text(dlg, self.cfg, "Add a pop-up source", "Address of the app, for example http://localhost:3000",
                         "http://localhost:3000")
            if u and origin_of(u):
                pu_src["list"].append({"url": origin_of(u), "enabled": True}); src_text()

        def clear_src(_b):
            pu_src["list"] = []; src_text()
        pu_add = Gtk.Button(label="Add a source (address)\u2026"); pu_add.connect("clicked", add_src)
        pu_clr = Gtk.Button(label="Remove all extra sources"); pu_clr.connect("clicked", clear_src)
        pu_test = Gtk.Button(label="Send a test pop-up"); pu_test.connect("clicked", lambda _b: self.popups.test())
        pu_push = Gtk.CheckButton(label="Let other programs on this PC send pop-ups to anTV (push)")
        pu_push.set_active(self.cfg.get("popup_push", False))
        pu_lan = Gtk.CheckButton(label="\u2026also from other devices on my network")
        pu_lan.set_active(self.cfg.get("popup_lan", False))
        pu_info = Gtk.Button(label="Show the push address and key\u2026")
        pu_info.connect("clicked", lambda _b: self.show_push_info(dlg))

        # ---- About tab
        tv_cb = Gtk.CheckButton(label="Use the TV-friendly (10-foot) settings screen: huge text, remote and gamepad friendly")
        tv_cb.set_active(self.cfg.get("tenft_settings", False))
        ver = Gtk.Box(spacing=14)
        ver.pack_start(Gtk.Label(label="anTV version " + VERSION, xalign=0), False, False, 0)
        hb = Gtk.Button(label="Version history\u2026"); hb.connect("clicked", lambda _b: show_history(dlg, self.cfg))
        scb = Gtk.Button(label="Keyboard shortcuts\u2026"); scb.connect("clicked", lambda _b: show_shortcuts(dlg, self.cfg))
        ver.pack_start(hb, False, False, 0); ver.pack_start(scb, False, False, 0)

        def form(rows):
            """Label on the left, control on the right; rows with no label (checkboxes, buttons) use the full width."""
            g = Gtk.Grid(column_spacing=28, row_spacing=18, margin=28)
            for r, (t, w) in enumerate(rows):
                if t is None:
                    w.set_halign(Gtk.Align.START)
                    g.attach(w, 0, r, 2, 1)
                else:
                    g.attach(Gtk.Label(label=t, xalign=0), 0, r, 1, 1)
                    w.set_hexpand(True)
                    g.attach(w, 1, r, 1, 1)
            return g

        nb = Gtk.Notebook()

        def tab(title, widget):
            sw = Gtk.ScrolledWindow(); sw.set_min_content_height(520); sw.add(widget)
            nb.append_page(sw, Gtk.Label(label=title))
        tab("Apps", apps_page)
        tab("Main screen", form([("Favorites row layout", fav_lay), (None, fav_b), (None, fav_l), (None, show_o),
                                 ("Clock next to anTV", clk), ("Card size", tsz), ("Card shape", tsh),
                                 ("Pictures on cards", pfit)]))
        tab("Look", form([("Card font", font), (None, def_cb), (None, addbg), (None, openbg), ("Background picture", bbox), ("Background slideshow folder", dbox),
                          ("Change picture every (seconds, 0 = never)", sp_int), (None, shuf),
                          ("Fade cards after idle (seconds, 0 = never)", sp_delay),
                          ("Time to fade out (seconds)", sp_fade), ("Faintest card opacity (%)", sp_min)]))
        tab("System", form([("Show anTV on", mon), ("Web browser", br), ("Local media folders (separate with ;)", media),
                            ("Android display (Waydroid)", disp_mode), (None, ab), (None, pb), (None, rb), (None, gb)]))
        tab("Pop-ups", form([(None, pu_on), ("Where pop-ups appear", pu_pos), ("Keep a pop-up up for (seconds, 0 = until dismissed)", pu_secs),
                             (None, pu_snd), (None, pu_src_lab), (None, pu_add), (None, pu_clr), (None, pu_test),
                             (None, pu_push), (None, pu_lan), (None, pu_info)]))
        up_mode = Gtk.ComboBoxText()
        for t in ("Never check", "Check and tell me", "Install automatically (used the next time anTV starts)"):
            up_mode.append_text(t)
        up_mode.set_active(UPDATE_MODES.index(self.cfg.get("update_mode", "ask")) if self.cfg.get("update_mode", "ask") in UPDATE_MODES else 1)
        up_repo = Gtk.Entry(text=update_repo(self.cfg)); up_repo.set_placeholder_text("owner/name   (add @branch to follow a branch)")
        up_note = Gtk.Label(label="anTV looks at the latest release of this GitHub repository (or a branch) every 12 hours while it is open.\n"
                                  "The old version is kept, so you can go back. Public repositories only.", xalign=0)
        up_chk = Gtk.Button(label="Check for updates now\u2026")
        up_chk.connect("clicked", lambda _b: self.update_check_flow(dlg, up_repo.get_text()) and dlg.response(RESTART_R))
        up_file = Gtk.Button(label="Install an update from a file\u2026")
        up_file.connect("clicked", lambda _b: self.update_file_flow(dlg) and dlg.response(RESTART_R))
        up_back = Gtk.Button(label="Go back to the previous version\u2026")
        up_back.connect("clicked", lambda _b: self.update_rollback_flow(dlg) and dlg.response(RESTART_R))
        tab("Updates", form([(None, up_note), ("Check for updates", up_mode), ("GitHub repository", up_repo),
                             (None, up_chk), (None, up_file), (None, up_back)]))
        data_note = Gtk.Label(label="Backups hold your apps, settings, card pictures and backgrounds (not browser logins).\n"
                                    "Press Save first if you just changed something.", xalign=0)
        bk = Gtk.Button(label="Save a backup of my data and settings\u2026")
        bk.connect("clicked", lambda _b: self.backup_data(dlg))
        rs = Gtk.Button(label="Restore from a backup\u2026")
        rs.connect("clicked", lambda _b: self.restore_data(dlg) and dlg.response(DONE_R))
        wp = Gtk.Button(label="Delete all data and start new\u2026")
        wp.connect("clicked", lambda _b: self.wipe_flow(dlg) and dlg.response(DONE_R))
        tab("Your data", form([(None, data_note), (None, bk), (None, rs), (None, wp)]))
        tab("About", form([(None, tv_cb), (None, ver)]))
        nb.set_size_request(1000, 600)
        dlg.get_content_area().pack_start(nb, True, True, 0)
        dlg.show_all(); refill()
        while True:
            resp = dlg.run()
            if resp == QUIT_R:
                if choose_dialog(dlg, self.cfg, "Quit anTV?", ["Yes, quit anTV", "No, go back"]) == 0:
                    dlg.destroy(); self.quit_app(); return
                continue
            break
        if resp == DONE_R:  # data was restored or deleted: the main screen is already refreshed
            dlg.destroy()
            return
        if resp in (Gtk.ResponseType.OK, HIDE_R, RESTART_R):
            self.cfg["apps"] = apps
            self.cfg["background_default"] = def_cb.get_active()
            self.cfg["idle_delay"] = int(sp_delay.get_value())
            self.cfg["idle_fade"] = int(sp_fade.get_value())
            self.cfg["idle_min"] = int(sp_min.get_value())
            if bgs["img"] and os.path.isfile(bgs["img"]):
                self.cfg["background"] = store_image(bgs["img"])
            else:
                self.cfg.pop("background", None)
            if bgd["dir"] and os.path.isdir(bgd["dir"]):
                self.cfg["background_dir"] = bgd["dir"]
            else:
                self.cfg.pop("background_dir", None)
            self.cfg["background_interval"] = int(sp_int.get_value())
            self.cfg["background_shuffle"] = shuf.get_active()
            self.cfg["tile_font"] = font.get_font_name()
            self.cfg["favorite_builtins"] = [k for k, w in (("browser", fav_b), ("local", fav_l)) if w.get_active()]
            self.cfg["show_others"] = show_o.get_active()
            newly = tv_cb.get_active() and not self.cfg.get("tenft_settings", False)
            self.cfg["tenft_settings"] = tv_cb.get_active()
            self.cfg["fav_layout"] = "grid" if fav_lay.get_active() == 1 else "scroll"
            self.cfg["clock"] = ("12h", "24h", "off")[max(0, clk.get_active())]
            self.cfg["tile_size"] = ("small", "medium", "large", "xlarge")[max(0, tsz.get_active())]
            self.cfg["tile_shape"] = ("wide", "classic", "square", "poster")[max(0, tsh.get_active())]
            self.cfg["picture_fit"] = "fit" if pfit.get_active() == 1 else "fill"
            if br.get_active_text():
                self.cfg["browser"] = br.get_active_text()
            self.cfg["media_dirs"] = [d.strip() for d in media.get_text().split(";") if d.strip()]
            self.cfg["android_display"] = ("auto", "software", "hardware")[max(0, disp_mode.get_active())]
            self.cfg["monitor"] = None if mon.get_active() <= 0 else mon.get_active() - 1
            self.cfg["popups"] = pu_on.get_active()
            self.cfg["popup_pos"] = POPUP_POSITIONS[max(0, pu_pos.get_active())]
            self.cfg["popup_secs"] = int(pu_secs.get_value())
            self.cfg["popup_sound"] = pu_snd.get_active()
            self.cfg["popup_sources"] = pu_src["list"]
            self.cfg["popup_push"] = pu_push.get_active()
            self.cfg["popup_lan"] = pu_lan.get_active()
            self.cfg["update_mode"] = UPDATE_MODES[max(0, up_mode.get_active())]
            self.cfg["update_repo"] = up_repo.get_text().strip()
            save(self.cfg)
            dlg.destroy(); self.path = []; self.apply_bg(); self.rebuild(); self.place(); self.popups.apply()
            if resp == RESTART_R:
                self.restart_app()
            elif resp == HIDE_R:
                GLib.timeout_add(200, self.hide_to_taskbar)
            elif newly:
                self.tv_settings()
        else:
            dlg.destroy()

    def command_for(self, a):
        if a["type"] == "cmd":
            if IS_WIN:  # let "vlc" / "kodi" work without being on PATH
                head, _, rest = a["cmd"].strip().partition(" ")
                real = next((r for r in (exe_path(x) for x in WIN_ALIASES.get(head.lower(), [])) if r), None)
                return (f'"{real}" {rest}'.strip() if real else a["cmd"]), None
            return shlex.split(a["cmd"]), None
        browser, chromium = find_browser()
        if not browser:
            raise RuntimeError("No browser found (install Edge, Chrome or Firefox)")
        prof = os.path.join(CFG_DIR, "profiles", "".join(c for c in a["name"] if c.isalnum()).lower())
        os.makedirs(prof, exist_ok=True)
        g = self.mon.get_geometry()
        if chromium:  # separate profile per service keeps each login saved
            cmd = [browser, f"--user-data-dir={prof}", f"--app={a['url']}", "--kiosk",
                   f"--window-position={g.x},{g.y}", f"--window-size={g.width},{g.height}",
                   "--no-first-run", "--autoplay-policy=no-user-gesture-required"]
            if IS_WIN:
                cmd.append("--start-fullscreen")
            return cmd, prof
        return [browser, "--new-instance", "--profile", prof, "--kiosk", a["url"]], prof

    def launch(self, a):
        if a["type"] == "node":
            return self.launch_node(a)
        if a["type"] == "android":
            return self.launch_android(a)
        try:
            cmd, match = self.command_for(a)
        except Exception as ex:
            m = Gtk.MessageDialog(transient_for=self, message_type=Gtk.MessageType.ERROR,
                                  buttons=Gtk.ButtonsType.OK, text=str(ex))
            m.run(); m.destroy(); return
        self.run_cmd(cmd, match, self)

    def run_cmd(self, cmd, match, win, after_start=None):
        """Hide `win`, run cmd in its own process group (so the kill hotkey works), then bring `win` back."""
        win.hide()

        def run():
            try:
                os.makedirs(CFG_DIR, exist_ok=True)
                proc = subprocess.Popen(cmd, **NEWGRP)
                with open(STATE, "w") as f:
                    json.dump({"pgid": proc.pid, "match": match}, f)
                if after_start:
                    after_start(proc)
                proc.wait()
            except Exception as ex:
                print("launch failed:", ex)
            GLib.idle_add(self.restore, win)
        threading.Thread(target=run, daemon=True).start()

    def restore(self, win):
        if win is self:
            self.back()
        else:
            win.show_all(); win.present(); win.tree.grab_focus()
        return False

    def back(self):
        self.rebuild(); self.place(); self.present()


def install_hotkey(path, extra=None):
    """Cinnamon global hotkey(s) -> `tvhub.py --kill`. `extra` = additional keys, e.g. the remote's Home button."""
    if IS_WIN:
        print("Windows: Ctrl+Alt+K is built in while TV Hub is running (no system shortcut needed).")
        return False
    base = "org.cinnamon.desktop.keybindings"
    key = "tvhub-kill"
    try:
        cur = subprocess.run(["gsettings", "get", base, "custom-list"], capture_output=True, text=True).stdout.strip()
        lst = ast.literal_eval(cur.replace("@as ", "")) if cur else []
        if key not in lst:
            lst.append(key)
            subprocess.run(["gsettings", "set", base, "custom-list", str(lst)], check=True)
        sub = f"{base}.custom-keybinding:/org/cinnamon/desktop/keybindings/custom-keybindings/{key}/"
        subprocess.run(["gsettings", "set", sub, "name", "TV Hub: kill app"], check=True)
        subprocess.run(["gsettings", "set", sub, "command", f"python3 {path} --kill"], check=True)
        binding = ["<Primary><Alt>k", "<Super>Escape"] + list(extra or [])
        subprocess.run(["gsettings", "set", sub, "binding", str(binding)], check=True)
        print("Kill hotkeys set:", ", ".join(binding), "(change in Keyboard settings)")
        return True
    except Exception as ex:
        print("Could not set hotkey automatically:", ex,
              "\nAdd one in Keyboard > Shortcuts > Custom: python3", path, "--kill")
        return False


def add_node_app(name, folder, url="http://localhost:3000"):
    """Add (or fix up) a Node.js card that shows pop-ups and keeps its server running. Used by Setup-TVHub.
    Run it while anTV is closed, otherwise anTV's next save overwrites it. Returns 'added', 'updated' or 'exists'."""
    cfg = load()
    apps = cfg.setdefault("apps", [])
    folder = os.path.abspath(os.path.expanduser(folder))
    same = lambda a: a.get("type") == "node" and (
        a.get("name") == name or os.path.normcase(os.path.abspath(os.path.expanduser(a.get("dir", "")))) == os.path.normcase(folder))
    for _l, a in flatten_apps(apps):
        if same(a):
            if a.get("popups") and a.get("keepalive"):
                return "exists"
            a["popups"] = a["keepalive"] = True
            save(cfg)
            return "updated"
    apps.append({"name": name, "type": "node", "dir": folder, "cmd": "node server.js", "url": url,
                 "color": "#ffb84d", "favorite": True, "popups": True, "keepalive": True})
    save(cfg)
    return "added"


def install():
    if IS_WIN:
        print("On Windows, run Setup-TVHub.bat: it installs everything and creates the TV Hub shortcut.")
        return
    path = os.path.abspath(__file__)
    d = os.path.expanduser("~/.local/share/applications"); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "tvhub.desktop"), "w") as f:
        f.write(f"[Desktop Entry]\nType=Application\nName=TV Hub\nComment=Fullscreen media launcher\n"
                f"Exec=python3 {path}\nIcon=video-display\nCategories=AudioVideo;Video;\n")
    print("Installed: find 'TV Hub' in your Mint menu.")
    install_hotkey(path, load().get("remote", {}).get("home") or [])


if __name__ == "__main__":
    if "--version" in sys.argv:
        print("anTV " + VERSION)
        sys.exit(0)
    if "--kill" in sys.argv:
        sys.exit(0 if kill_current() else 1)
    if "--add-node-app" in sys.argv:
        i = sys.argv.index("--add-node-app")
        args = sys.argv[i + 1:]
        if len(args) < 2:
            print("usage: tvhub.py --add-node-app NAME FOLDER [URL]")
            sys.exit(2)
        print(add_node_app(*args[:3]))
        sys.exit(0)
    if "--install" in sys.argv:
        install()
    else:
        hub = None
        if update_boot_guard():  # a fresh update kept failing and was just rolled back: start the old version
            RESTART["want"] = True
        else:
            try:
                hub = Hub()
            except Exception:
                if not update_failed_start():  # a just-installed version can't build its window: go back
                    raise
                RESTART["want"] = True
        if hub is not None:
            Gtk.main()
            hub.stop_bg_servers()
            update_confirm()  # this version ran and was closed normally
        if RESTART["want"]:
            spawn_self()
