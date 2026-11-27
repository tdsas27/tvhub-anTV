<#
.SYNOPSIS
  Installs everything TV Hub (tvhub.py) needs on Windows 10/11 and creates a TV Hub shortcut.

.DESCRIPTION
  TV Hub is a GTK3 + Python app. On Windows the supported way to get both is MSYS2 (MinGW64), so this script:
    1. Installs MSYS2 (winget, or a direct download if winget is missing)
    2. Updates it and installs Python, PyGObject and GTK3 (plus optional QR-code/image helpers)
    3. Installs VLC (media playback) - Microsoft Edge is already part of Windows
    4. Optionally installs Node.js (for Node.js app cards and the Tasks app) and Google Chrome
    5. Checks that tvhub.py really imports, then creates TVHub.bat and Desktop / Start Menu shortcuts
    6. Optionally adds the Tasks app (the tasks folder next to this script) as a TV Hub card with pop-ups
       turned on and its server kept running in the background, so reminders appear on top of any app

  Run it by double-clicking Setup-TVHub.bat (next to this file). It asks for administrator rights.

.PARAMETER Check      Only report what is installed; change nothing.
.PARAMETER Node       Also install Node.js LTS (no question asked).
.PARAMETER Chrome     Also install Google Chrome (no question asked).
.PARAMETER NoVlc      Skip VLC.
.PARAMETER Autostart  Start TV Hub when you log in.
.PARAMETER Tasks      Add the Tasks app (tasks folder next to this script) as a TV Hub card with pop-ups. Installs Node.js too.
.PARAMETER Firewall   Allow the phone remote (and Node.js apps such as Tasks) through Windows Firewall on Private networks.
.PARAMETER Yes        Never ask questions (unattended); optional items happen only if their switch is given.
#>
[CmdletBinding()]
param(
    [switch]$Check, [switch]$Node, [switch]$Chrome, [switch]$NoVlc,
    [switch]$Autostart, [switch]$Firewall, [switch]$Tasks, [switch]$Yes
)

$ErrorActionPreference = "Continue"
$Msys    = "C:\msys64"
$Bash    = Join-Path $Msys "usr\bin\bash.exe"
$MsysPy  = Join-Path $Msys "mingw64\bin\python.exe"
$MsysPyW = Join-Path $Msys "mingw64\bin\pythonw.exe"
$Script  = Join-Path $PSScriptRoot "tvhub.py"
$Launcher = Join-Path $PSScriptRoot "TVHub.bat"
$TasksDir = Join-Path $PSScriptRoot "tasks"
$TvConfig = Join-Path $env:APPDATA "tvhub\config.json"
$Results = New-Object System.Collections.ArrayList

function Say([string]$m, [string]$c = "Cyan") { Write-Host $m -ForegroundColor $c }
function Add-Result([string]$item, [bool]$ok, [string]$note = "") {
    $status = "MISSING"; if ($ok) { $status = "OK" }
    [void]$Results.Add([pscustomobject]@{ Item = $item; Status = $status; Note = $note })
}
function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Have-Winget { return [bool](Get-Command winget -ErrorAction SilentlyContinue) }
function Ask([string]$q) {
    if ($Yes) { return $false }
    return ((Read-Host "$q [y/N]") -match '^(y|yes)$')
}
function Find-First([string[]]$paths) {
    foreach ($p in $paths) { if ($p -and (Test-Path $p)) { return $p } }
    return $null
}
function Find-Vlc    { Find-First @("$env:ProgramFiles\VideoLAN\VLC\vlc.exe", "${env:ProgramFiles(x86)}\VideoLAN\VLC\vlc.exe") }
function Find-Edge   { Find-First @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") }
function Find-Chrome { Find-First @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LocalAppData\Google\Chrome\Application\chrome.exe") }
function Find-Node   { return [bool](Get-Command node -ErrorAction SilentlyContinue) -or [bool](Find-First @("$env:ProgramFiles\nodejs\node.exe")) }
function Find-NodeExe {
    $c = Get-Command node -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return Find-First @("$env:ProgramFiles\nodejs\node.exe")
}
function Find-Tasks  { return (Test-Path (Join-Path $TasksDir "server.js")) }
function Tasks-Card-Configured {
    if (-not (Test-Path $TvConfig)) { return $false }
    return [bool](Select-String -Path $TvConfig -Pattern '"keepalive": true' -Quiet) -and [bool](Select-String -Path $TvConfig -Pattern '"name": "Tasks"' -Quiet)
}
function Tvhub-Running {
    # True when anTV is open (it would overwrite config changes made by this script when it saves).
    $p = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
         Where-Object { $_.CommandLine -like "*tvhub.py*" -and $_.CommandLine -notlike "*--add-node-app*" }
    return [bool]$p
}

function Invoke-Msys([string]$cmd) {
    $env:MSYSTEM = "MINGW64"
    $env:CHERE_INVOKING = "1"
    & $Bash -lc $cmd
    if ($LASTEXITCODE -ne 0) { throw "MSYS2 command failed (exit $LASTEXITCODE): $cmd" }
}
function Winget-Install([string]$id) {
    winget install --id $id -e --silent --accept-package-agreements --accept-source-agreements
    # -1978335189 = "already installed / no upgrade available"
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { throw "winget could not install $id (exit $LASTEXITCODE)" }
}
function Gtk-Works {
    if (-not (Test-Path $MsysPy)) { return $false }
    $env:PATH = "$Msys\mingw64\bin;$env:PATH"
    & $MsysPy -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk, Gdk, GLib, Gio, Pango" 2>$null
    return ($LASTEXITCODE -eq 0)
}
function Tvhub-Imports {
    if (-not (Test-Path $MsysPy) -or -not (Test-Path $Script)) { return $false }
    $env:PATH = "$Msys\mingw64\bin;$env:PATH"
    $code = "import importlib.util as u; s=u.spec_from_file_location('tvhub', r'$Script'); m=u.module_from_spec(s); s.loader.exec_module(m); print('imports OK')"
    & $MsysPy -c $code 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}
function Tvhub-Version {
    if (-not (Test-Path $MsysPy) -or -not (Test-Path $Script)) { return "" }
    $env:PATH = "$Msys\mingw64\bin;$env:PATH"
    return ((& $MsysPy $Script --version 2>$null) | Out-String).Trim()
}
function New-Shortcut([string]$lnk, [string]$target, [string]$workDir, [string]$desc) {
    $w = New-Object -ComObject WScript.Shell
    $s = $w.CreateShortcut($lnk)
    $s.TargetPath = $target
    $s.WorkingDirectory = $workDir
    $s.Description = $desc
    $s.WindowStyle = 7   # minimized, so no console flash
    $s.Save()
}
function Show-Summary {
    Write-Host ""
    Say "==== Summary ====" "Green"
    $Results | Format-Table -AutoSize | Out-String | Write-Host
}
function Finish {
    if (-not $Yes) { [void](Read-Host "Press Enter to close") }
}

Say "TV Hub - Windows setup" "Green"
if ([Environment]::OSVersion.Version.Major -lt 10) { Say "Windows 10 or newer is required." "Red"; Finish; exit 1 }

# ---------------------------------------------------------------- check-only mode
if ($Check) {
    Add-Result "MSYS2" (Test-Path $Bash) $Msys
    Add-Result "Python + GTK3 (PyGObject)" (Gtk-Works) "needed to run tvhub.py"
    Add-Result "tvhub.py next to this script" (Test-Path $Script) $Script
    Add-Result "tvhub.py imports cleanly" (Tvhub-Imports)
    $ver = Tvhub-Version
    Add-Result "anTV version" ($ver -ne "") $ver
    Add-Result "VLC" ([bool](Find-Vlc)) "media playback"
    Add-Result "Microsoft Edge" ([bool](Find-Edge)) "kiosk browser for streaming apps (Netflix etc.)"
    Add-Result "Google Chrome (optional)" ([bool](Find-Chrome))
    Add-Result "Node.js (optional)" (Find-Node) "needed for Node.js app cards and the Tasks app"
    Add-Result "Tasks app folder (optional)" (Find-Tasks) $TasksDir
    Add-Result "Tasks card with pop-ups in anTV (optional)" (Tasks-Card-Configured) "run Setup-TVHub.bat -Tasks to add it"
    Add-Result "winget" (Have-Winget) "used to install the rest"
    Add-Result "TVHub.bat launcher" (Test-Path $Launcher)
    Show-Summary
    Finish
    exit 0
}

# ---------------------------------------------------------------- elevate
if (-not (Test-Admin)) {
    Say "Asking for administrator rights..." "Yellow"
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
    foreach ($k in $PSBoundParameters.Keys) {
        if ($PSBoundParameters[$k] -is [switch] -and $PSBoundParameters[$k].IsPresent) { $argList += "-$k" }
    }
    try { Start-Process powershell -Verb RunAs -ArgumentList $argList -Wait } catch { Say "Administrator rights were declined." "Red" }
    exit
}

# ---------------------------------------------------------------- ask optional questions up front
$wantTasks     = (Find-Tasks) -and ($Tasks -or (Ask "Add the Tasks app to TV Hub, with its reminders popping up on top of any app?"))
$wantNode      = $Node      -or $wantTasks -or (Ask "Install Node.js LTS (needed only for Node.js app cards)?")
$wantChrome    = $Chrome    -or (Ask "Install Google Chrome too? (Edge already works for Netflix/Hulu/Peacock)")
$wantAutostart = $Autostart -or (Ask "Start TV Hub automatically when you log in?")
$wantFirewall  = $Firewall  -or (Ask "Allow the phone remote and Node.js apps (such as Tasks) through Windows Firewall (Private networks only)?")

if ($Tasks -and -not (Find-Tasks)) {
    Say "WARNING: -Tasks was given but the tasks folder was not found next to this script ($TasksDir)." "Yellow"
}
if (-not (Test-Path $Script)) {
    Say "WARNING: tvhub.py was not found next to this script ($Script). Put them in the same folder." "Yellow"
}
if (-not (Have-Winget)) {
    Say "winget was not found. MSYS2 will be downloaded directly; for VLC/Node/Chrome install 'App Installer' from the Microsoft Store or install them by hand." "Yellow"
}

# ---------------------------------------------------------------- 1. MSYS2
try {
    if (-not (Test-Path $Bash)) {
        Say "Installing MSYS2 (Python + GTK come from here)..."
        if (Have-Winget) { try { Winget-Install "MSYS2.MSYS2" } catch { Say "  winget failed: $($_.Exception.Message)" "Yellow" } }
        if (-not (Test-Path $Bash)) {
            Say "  Downloading the MSYS2 installer directly..."
            $exe = Join-Path $env:TEMP "msys2-x86_64-latest.exe"
            Invoke-WebRequest "https://repo.msys2.org/distrib/msys2-x86_64-latest.exe" -OutFile $exe -UseBasicParsing
            Start-Process $exe -ArgumentList @("in", "--confirm-command", "--accept-messages", "--root", "C:/msys64") -Wait
        }
    }
    if (-not (Test-Path $Bash)) { throw "MSYS2 did not install." }
    Add-Result "MSYS2" $true $Msys
} catch {
    Add-Result "MSYS2" $false $_.Exception.Message
    Show-Summary; Say "Cannot continue without MSYS2." "Red"; Finish; exit 1
}

# ---------------------------------------------------------------- 2. Python + GTK3
try {
    Say "Updating MSYS2 packages (first run can take several minutes)..."
    try { Invoke-Msys "pacman -Syu --noconfirm" } catch { Say "  (core update ended early - normal; running it again)" "Yellow" }
    Invoke-Msys "pacman -Syu --noconfirm"
    Say "Installing Python, PyGObject and GTK3..."
    Invoke-Msys "pacman -S --needed --noconfirm mingw-w64-x86_64-python mingw-w64-x86_64-python-gobject mingw-w64-x86_64-gtk3"
    foreach ($pkg in @("mingw-w64-x86_64-python-pillow", "mingw-w64-x86_64-python-qrcode", "mingw-w64-x86_64-webp-pixbuf-loader")) {
        try { Invoke-Msys "pacman -S --needed --noconfirm $pkg" } catch { Say "  optional package skipped: $pkg" "Yellow" }
    }
    if (-not (Gtk-Works)) { throw "Python/GTK installed but 'import gi' with Gtk 3 still fails." }
    Add-Result "Python + GTK3 (PyGObject)" $true "MSYS2 mingw64"
} catch {
    Add-Result "Python + GTK3 (PyGObject)" $false $_.Exception.Message
}

# ---------------------------------------------------------------- 3. VLC / Node / Chrome (+ Edge check)
if (-not $NoVlc) {
    try {
        if (-not (Find-Vlc)) {
            if (-not (Have-Winget)) { throw "winget missing - install VLC from https://www.videolan.org" }
            Say "Installing VLC..."; Winget-Install "VideoLAN.VLC"
        }
        Add-Result "VLC" ([bool](Find-Vlc)) "media playback"
    } catch { Add-Result "VLC" $false $_.Exception.Message }
}
Add-Result "Microsoft Edge" ([bool](Find-Edge)) "built into Windows; used for streaming apps"
if ($wantChrome) {
    try {
        if (-not (Find-Chrome)) {
            if (-not (Have-Winget)) { throw "winget missing - install Chrome from google.com/chrome" }
            Say "Installing Google Chrome..."; Winget-Install "Google.Chrome"
        }
        Add-Result "Google Chrome" ([bool](Find-Chrome))
    } catch { Add-Result "Google Chrome" $false $_.Exception.Message }
}
if ($wantNode) {
    try {
        if (-not (Find-Node)) {
            if (-not (Have-Winget)) { throw "winget missing - install Node.js from nodejs.org" }
            Say "Installing Node.js LTS..."; Winget-Install "OpenJS.NodeJS.LTS"
        }
        Add-Result "Node.js" $true "open a new TV Hub session so PATH is refreshed"
    } catch { Add-Result "Node.js" $false $_.Exception.Message }
}

# ---------------------------------------------------------------- 4. launcher, shortcuts, extras
try {
    $bat = @"
@echo off
rem Starts TV Hub with the MSYS2 Python that has GTK. Extra arguments are passed through (for example --kill).
set "PATH=$Msys\mingw64\bin;%PATH%"
start "" "$MsysPyW" "%~dp0tvhub.py" %*
"@
    Set-Content -Path $Launcher -Value $bat -Encoding ASCII
    $desktop = [Environment]::GetFolderPath("Desktop")
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    New-Shortcut (Join-Path $desktop "TV Hub.lnk") $Launcher $PSScriptRoot "Fullscreen media launcher"
    New-Shortcut (Join-Path $startMenu "TV Hub.lnk") $Launcher $PSScriptRoot "Fullscreen media launcher"
    if ($wantAutostart) {
        New-Shortcut (Join-Path ([Environment]::GetFolderPath("Startup")) "TV Hub.lnk") $Launcher $PSScriptRoot "Fullscreen media launcher"
    }
    Add-Result "TVHub.bat + shortcuts" $true "Desktop and Start Menu"
} catch { Add-Result "TVHub.bat + shortcuts" $false $_.Exception.Message }

if ($wantFirewall) {
    try {
        foreach ($exe in @($MsysPyW, $MsysPy)) {
            if (-not (Get-NetFirewallRule -DisplayName "TV Hub phone remote ($(Split-Path $exe -Leaf))" -ErrorAction SilentlyContinue)) {
                New-NetFirewallRule -DisplayName "TV Hub phone remote ($(Split-Path $exe -Leaf))" -Direction Inbound -Action Allow `
                    -Program $exe -Protocol TCP -Profile Private | Out-Null
            }
        }
        $nodeExe = Find-NodeExe
        if ($nodeExe) {
            $rule = "TV Hub Node.js apps (node.exe)"
            if (-not (Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue)) {
                New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Allow -Program $nodeExe -Protocol TCP -Profile Private | Out-Null
            }
        }
        $fwNote = "phone remote"
        if ($nodeExe) { $fwNote = "phone remote and Node.js apps (Tasks on your phone)" }
        Add-Result "Firewall rule (Private networks)" $true $fwNote
    } catch { Add-Result "Firewall rule (Private networks)" $false $_.Exception.Message }
}

# ---------------------------------------------------------------- 5. verify tvhub.py
if (Test-Path $Script) {
    Add-Result "tvhub.py imports cleanly" (Tvhub-Imports) "checks the Windows code paths load"
} else {
    Add-Result "tvhub.py next to this script" $false $Script
}

if ($wantTasks) {
    try {
        if (-not (Test-Path $Script) -or -not (Gtk-Works)) { throw "needs tvhub.py and a working Python/GTK first" }
        if (Tvhub-Running) {
            throw "TV Hub is open. Close it (Settings > Quit), then run Setup-TVHub.bat -Tasks again."
        }
        $env:PATH = "$Msys\mingw64\bin;$env:PATH"
        $out = ((& $MsysPy $Script --add-node-app "Tasks" $TasksDir "http://localhost:3000") | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) { throw "could not add the card: $out" }
        Add-Result "Tasks card in TV Hub (pop-ups on, server kept running)" $true $out
    } catch { Add-Result "Tasks card in TV Hub (pop-ups on, server kept running)" $false $_.Exception.Message }
}

Show-Summary
$bad = @($Results | Where-Object { $_.Status -ne "OK" })
if ($bad.Count -eq 0) {
    Say "All set. Start TV Hub from the 'TV Hub' shortcut on your Desktop or Start Menu." "Green"
    Say "Tips: Ctrl+Alt+K closes the running app. Xbox controllers work through Windows XInput." "Green"
    Say "Pop-ups: Settings > Pop-ups in TV Hub (send a test pop-up there). Apps need 'Show this app's pop-ups' ticked on their card." "Green"
} else {
    Say "Some items need attention (see MISSING above). You can re-run this script any time." "Yellow"
}
Finish
