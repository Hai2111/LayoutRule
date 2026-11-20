# setup/setup.ps1 - LayoutRule agent toolchain check/install (Windows)
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File setup\setup.ps1
# Checks python, kicad-cli, java; downloads + SHA256-verifies Freerouting CLI if missing.
# Exit: 0 = all OK, 1 = bad checksum, 2 = missing tools.

$ErrorActionPreference = "Stop"
$frDir  = Join-Path $PSScriptRoot "freerouting"
$frExe  = Join-Path $frDir "cli\freerouting-cli.exe"
$frVer  = "2.5.0"
$frZip  = "freerouting-cli-$frVer-windows-x64.zip"
$frUrl  = "https://github.com/freerouting/freerouting/releases/download/v$frVer/$frZip"
$frSha  = "5750dc0bed261eefae29d79784301b478af978fd472407d77e01e85dbb794857"

$pyOk = $false
$kicadOk = $false
$javaOk = $false
$frOk = $false

# --- 1) Python (repo tools use stdlib only, no pip packages needed) ---
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    $verOut = (& cmd /c "python --version 2>&1") -join " "
    $pyOk = $false
    if ($verOut -match '(\d+)\.(\d+)') {
        $maj = $Matches[1] -as [int]; $min = $Matches[2] -as [int]
        if ($maj -gt 3 -or ($maj -eq 3 -and $min -ge 10)) { $pyOk = $true }
    }
    Write-Host "[OK]   python -> $($pythonCmd.Source) ($verOut)"
} else {
    Write-Host "[MISS] python not found. Install: https://www.python.org/downloads/"
}

# --- 2) KiCad CLI (ERC/DRC + image render + DSN/SES export) ---
$kicadCli = $null
$kc = Get-Command kicad-cli -ErrorAction SilentlyContinue
if ($kc) { $kicadCli = $kc.Source }
else {
    $candidates = @(
        "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
        "C:\Program Files\KiCad\bin\kicad-cli.exe"
    )
    foreach ($d in $candidates) { if (Test-Path $d) { $kicadCli = $d; break } }
}
if ($kicadCli) {
    $kv = (& $kicadCli version 2>&1) -join " "
    if ($kv -match "10\.") {
        $kicadOk = $true
        Write-Host "[OK]   kicad-cli -> $kicadCli ($kv)"
    } else {
        Write-Host "[WARN] kicad-cli -> $kicadCli, version: $kv (not 10.x?)"
    }
} else {
    Write-Host "[MISS] kicad-cli not found. Install KiCad 10: https://www.kicad.org/download/"
}

# --- 3) Java (Freerouting CLI runtime, needs >= 17) ---
$javaCmd = Get-Command java -ErrorAction SilentlyContinue
if ($javaCmd) {
    $jvOut = (& cmd /c "java -version 2>&1") -join " "
    $jnum = 0
    if ($jvOut -match '"?(\d+)') { $jnum = $Matches[1] -as [int] }
    if ($jnum -ge 17) {
        $javaOk = $true
        Write-Host "[OK]   java -> $($javaCmd.Source) ($jvOut)"
    } else {
        Write-Host "[WARN] java version $jnum (need >= 17). $jvOut"
    }
} else {
    Write-Host "[MISS] java not found. Install JDK 17+: https://adoptium.net/"
}

# --- 4) Freerouting CLI - download + verify checksum if missing ---
if (Test-Path $frExe) {
    $frOk = $true
    Write-Host "[OK]   freerouting-cli.exe present -> $frExe"
} else {
    Write-Host "[....] freerouting-cli.exe missing. Downloading $frVer (windows-x64)..."
    New-Item -ItemType Directory -Force -Path $frDir | Out-Null
    $zipPath = Join-Path $frDir $frZip
    Invoke-WebRequest -Uri $frUrl -OutFile $zipPath -UseBasicParsing
    $actual = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $frSha) {
        Write-Host "[FAIL] SHA256 MISMATCH! expected $frSha, got $actual. Do NOT run this binary."
        exit 1
    }
    Write-Host "[OK]   SHA256 verified (match)."
    Expand-Archive $zipPath -DestinationPath (Join-Path $frDir "cli") -Force
    if (Test-Path $frExe) {
        $frOk = $true
        Write-Host "[OK]   extracted -> $frExe"
    }
}

# --- Summary ---
Write-Host ""
Write-Host "=== setup summary ==="
Write-Host ("python       : " + $(if ($pyOk)    { "OK" }    else { "MISSING" }))
Write-Host ("kicad-cli    : " + $(if ($kicadOk) { "OK" } else { "MISSING" }))
Write-Host ("java         : " + $(if ($javaOk)  { "OK" } else { "MISSING" }))
Write-Host ("freerouting  : " + $(if ($frOk)    { "OK ($frVer)" } else { "MISSING" }))
Write-Host ""
if ($pyOk -and $kicadOk -and $javaOk -and $frOk) {
    Write-Host "All tools ready. Agent can start:"
    Write-Host "  - DRC/ERC + image render: kicad-cli (see paths above)"
    Write-Host "  - Routing engine:         $frExe (DSN/SES, see ROUTING_ENGINE_INTEGRATION.md)"
    Write-Host "  - Geometry audit:         python tools\layout_audit.py / tools\drc_body_keepout.py"
    exit 0
} else {
    Write-Host "Some tools missing - see MANIFEST.json for install instructions."
    exit 2
}
