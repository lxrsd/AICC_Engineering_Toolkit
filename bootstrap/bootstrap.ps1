<#
.SYNOPSIS
  AICC Engineering Toolkit — Windows one-command bootstrapper.

.DESCRIPTION
  TRUE one command on a fresh Windows machine: assumes nothing but Windows
  PowerShell (5.1+) and TLS access to github.com. It detects / installs the
  prerequisites the AICC installer needs, fetches a PINNED Toolkit release
  (no git clone required), and hands off to installer\install.py.

  Coordinated steps:
    1. Detect OS + CPU arch; refuse unsupported combinations honestly.
    2. Detect Python 3 (>= 3.9). If missing, install with explicit consent via
       winget (official 'Python.Python.3.12' package, verified publisher) and,
       if winget is unavailable or its source is broken, fall back to the
       OFFICIAL python.org per-user installer (downloaded over TLS, SHA-256
       verifiable). User scope — no admin required.
    3. Detect git; install with consent via winget if missing (optional).
    4. Acquire the Toolkit: use this checkout when run from one, else download
       the PINNED release .zip over TLS and verify its SHA-256.
    5. Hand off to installer\install.py, which selects/uses the AI harness,
       installs+verifies the official AWS Labs AI-DLC runtime (its own consent
       prompt / PowerShell installer), wires the sync hook, registers the
       project against the default Workbench endpoint, and opens the Workbench.

  Security: user-scope installs (no hidden elevation), no remote script runs
  without consent, downloads are integrity-checked where a digest is given, and
  no update_token or Workbench secret is ever printed (those live only in
  install.py's project config). OneDrive-backed paths with spaces are supported.

.PARAMETER Target       Project directory for the AI-DLC build (prompted if omitted).
.PARAMETER Tool         claude-code | kiro-cli (installer prompts if omitted).
.PARAMETER Yes          Consent to prerequisite installs without prompting.
.PARAMETER NoBrowser    Do not open the Workbench in a browser.
.PARAMETER Ref          Pinned release tag to download (default: v0.1.0).
.PARAMETER Sha256       Expected SHA-256 of the release .zip (integrity check).
.PARAMETER DryRun       Print the plan; change nothing.

.EXAMPLE
  .\bootstrap.ps1 -Target "C:\Users\Engineer\OneDrive - Company\Desktop\AICC-Test\expense-tracker" -Tool kiro-cli
#>
[CmdletBinding()]
param(
  [string]$Target = "",
  [ValidateSet("claude-code", "kiro-cli", "")]
  [string]$Tool = "",
  [switch]$Yes,
  [switch]$NoBrowser,
  [string]$Ref = "v0.1.0",
  [string]$Sha256 = "",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ToolkitRepo = "lxrsd/AICC_Engineering_Toolkit"
$MinPyMinor = 9

# Prefer modern TLS for all web requests (older Windows PowerShell defaults low).
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

function Say($m)  { Write-Host $m }
function Info($m) { Write-Host "  $m" }
function Warn($m) { Write-Warning $m }
function Die($m)  { Write-Error $m; exit 1 }

function Confirm-Action($prompt) {
  if ($Yes) { return $true }
  if ([Console]::IsInputRedirected) {
    Warn "no interactive console and -Yes not given; declining: $prompt"
    return $false
  }
  $ans = Read-Host "$prompt [y/N]"
  return ($ans -match '^(y|yes)$')
}

function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

Say "== AICC Engineering Toolkit bootstrap (Windows) =="

# --------------------------------------------------------------------------
# 1. OS + CPU detection
# --------------------------------------------------------------------------
$archRaw = $env:PROCESSOR_ARCHITECTURE
switch -Regex ($archRaw) {
  "ARM64"          { $ArchName = "arm64" }
  "AMD64|x86_64"   { $ArchName = "x64" }
  default          { Die "unsupported CPU architecture '$archRaw'. Supported: x64 and arm64." }
}
Info "Detected: Windows / $ArchName"

# --------------------------------------------------------------------------
# 2. Python 3 (>= 3.9): detect, else install via winget, else python.org
# --------------------------------------------------------------------------
$Python = $null
function Resolve-Python {
  foreach ($cand in @("py -3", "python3", "python")) {
    $exe, $pre = $cand.Split(" ", 2)
    if (-not (Have $exe)) { continue }
    try {
      $code = "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, $MinPyMinor) else 1)"
      if ($pre) { & $exe $pre -c $code 2>$null } else { & $exe -c $code 2>$null }
      if ($LASTEXITCODE -eq 0) { return $cand }
    } catch {}
  }
  return $null
}

function Install-PythonViaWinget {
  if (-not (Have winget)) { return $false }
  Info "Installing Python 3 via winget (user scope, verified publisher)…"
  if ($DryRun) { Info "DRY-RUN would run: winget install --id Python.Python.3.12 --scope user"; return $true }
  # --silent + user scope => no admin elevation. winget verifies the publisher.
  & winget install --id Python.Python.3.12 --source winget --scope user --silent `
      --accept-package-agreements --accept-source-agreements
  return ($LASTEXITCODE -eq 0)
}

function Install-PythonViaOrg {
  # Official python.org per-user installer fallback when winget is unavailable
  # or its source is broken (a known corporate failure mode).
  $pyVer = "3.12.7"
  $file = if ($ArchName -eq "arm64") { "python-$pyVer-arm64.exe" } else { "python-$pyVer-amd64.exe" }
  $url = "https://www.python.org/ftp/python/$pyVer/$file"
  Info "Falling back to the official python.org per-user installer:"
  Info "  $url"
  if ($DryRun) { Info "DRY-RUN would download + run the official installer (InstallAllUsers=0)."; return $true }
  $dest = Join-Path $env:TEMP $file
  try {
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
  } catch {
    Warn "download failed: $($_.Exception.Message)"
    Warn "corporate cause? outbound HTTPS blocked or a TLS-inspecting proxy. Set HTTPS_PROXY or ask IT to allowlist python.org."
    return $false
  }
  # Per-user, no admin; adds to PATH for this user.
  & $dest /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1
  return ($LASTEXITCODE -eq 0)
}

$Python = Resolve-Python
if ($Python) {
  Info "Python: found ($Python)"
} else {
  Warn "A supported Python 3 ($MinPyMinor+) was not found."
  if (Confirm-Action "Install Python 3 now (user scope, no admin)?") {
    $ok = Install-PythonViaWinget
    if (-not $ok) {
      Warn "winget install unavailable or failed; trying the official python.org installer."
      $ok = Install-PythonViaOrg
    }
    if (-not $ok -and -not $DryRun) { Die "Python installation did not complete. Install Python 3.$MinPyMinor+ and re-run." }
    if (-not $DryRun) {
      # PATH may not be refreshed in THIS process; re-read user+machine PATH.
      $env:Path = [Environment]::GetEnvironmentVariable("Path", "User") + ";" + [Environment]::GetEnvironmentVariable("Path", "Machine")
      $Python = Resolve-Python
      if (-not $Python) { Die "Python still not detected. Open a NEW PowerShell window (PATH refresh) and re-run." }
      Info "Python: found ($Python)"
    } else {
      $Python = "py -3"
    }
  } else {
    Die "Python 3 is required and installation was declined."
  }
}

# --------------------------------------------------------------------------
# 3. Git (optional)
# --------------------------------------------------------------------------
if (Have git) {
  Info "git: $(git --version)"
} else {
  Warn "git not found (not required to install the Toolkit; recommended for your work)."
  if ((Confirm-Action "Install git now via winget?") -and (Have winget)) {
    if ($DryRun) { Info "DRY-RUN would run: winget install --id Git.Git --scope user" }
    else { & winget install --id Git.Git --source winget --scope user --silent --accept-package-agreements --accept-source-agreements }
  }
}

# --------------------------------------------------------------------------
# 4. Acquire the Toolkit (no git clone required)
# --------------------------------------------------------------------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolkitDir = $null
$CleanupDir = $null

if (Test-Path (Join-Path $ScriptDir "..\installer\install.py")) {
  $ToolkitDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path
  Info "Using the Toolkit from this checkout: $ToolkitDir"
} else {
  $work = Join-Path $env:TEMP ("aicc-bootstrap-" + [guid]::NewGuid().ToString("N"))
  $CleanupDir = $work
  New-Item -ItemType Directory -Force -Path $work | Out-Null
  $zip = Join-Path $work "toolkit.zip"
  $url = "https://github.com/$ToolkitRepo/archive/refs/tags/$Ref.zip"
  Info "Downloading pinned Toolkit $Ref over TLS:"
  Info "  $url"
  if ($DryRun) {
    Info "DRY-RUN would download + verify + extract the release .zip."
    $ToolkitDir = Join-Path $work "AICC_Engineering_Toolkit-pinned"
  } else {
    try {
      Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    } catch {
      Warn "download failed: $($_.Exception.Message)"
      Warn "corporate causes: outbound HTTPS to github.com blocked, or a TLS-inspecting proxy."
      Warn "set `$env:HTTPS_PROXY, or ask IT to allowlist github.com, then re-run."
      Die "could not obtain the Toolkit release $Ref."
    }
    if ($Sha256 -ne "") {
      Info "Verifying archive SHA-256…"
      $actual = (Get-FileHash -Algorithm SHA256 -Path $zip).Hash.ToLower()
      if ($actual -ne $Sha256.ToLower()) { Die "archive SHA-256 mismatch: expected $Sha256, got $actual. Aborting (integrity)." }
      Info "SHA-256 OK."
    } else {
      Warn "no -Sha256 provided; skipping digest verification (GitHub TLS still protects transport)."
      Warn "For a verifiable install, pass -Sha256 <digest> from the release notes."
    }
    Expand-Archive -Path $zip -DestinationPath $work -Force
    $ToolkitDir = (Get-ChildItem -Path $work -Directory -Filter "AICC_Engineering_Toolkit-*" | Select-Object -First 1).FullName
    if (-not $ToolkitDir -or -not (Test-Path (Join-Path $ToolkitDir "installer\install.py"))) {
      Die "extracted archive missing installer\install.py."
    }
    Info "Extracted to $ToolkitDir"
  }
}

try {
  # --------------------------------------------------------------------------
  # 5. Hand off to the existing installer.
  # --------------------------------------------------------------------------
  if ($Target -eq "") {
    if (-not [Console]::IsInputRedirected -and -not $Yes -and -not $DryRun) {
      $Target = Read-Host "Project directory for your AI-DLC build"
    }
    if ($Target -eq "") { Die "a project directory is required. Pass -Target <dir>." }
  }

  $installPy = Join-Path $ToolkitDir "installer\install.py"
  # Build the argument list. Quoting is handled by PowerShell's native call
  # operator with an array, so a Target path with spaces (OneDrive) is safe.
  $pyArgs = @($installPy, "--target", $Target, "--allow-runtime-install")
  if ($Tool -ne "")  { $pyArgs += @("--tool", $Tool) }
  if ($Yes)          { $pyArgs += "--yes" }
  if ($NoBrowser)    { $pyArgs += "--no-browser" }
  if ($DryRun)       { $pyArgs += "--dry-run" }

  Say ""
  Say "Handing off to the AICC installer…"
  Info "$Python $($pyArgs -join ' ')"
  Say ""

  # $Python may be "py -3" (launcher + arg) or a single exe.
  $pyExe, $pyPre = $Python.Split(" ", 2)
  if ($pyPre) { & $pyExe $pyPre @pyArgs } else { & $pyExe @pyArgs }
  exit $LASTEXITCODE
}
finally {
  if ($CleanupDir -and (Test-Path $CleanupDir)) {
    Remove-Item -Recurse -Force $CleanupDir -ErrorAction SilentlyContinue
  }
}
