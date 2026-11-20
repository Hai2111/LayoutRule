# tools/route_pipeline.ps1 — one-command KiCad -> Freerouting JAR -> KiCad -> native DRC.
#
# Usage from rule/ repo root:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\route_pipeline.ps1 -Board path\to\board.kicad_pcb
# Optional:
#   -OutputDir path       (default: <board directory>\routing_candidate)
#   -MaxPasses 20         (Freerouting autorouter passes)
#   -AllowDrcViolations   (default: false; pipeline exits nonzero on DRC error)
#
# SAFETY: never overwrites the input board. Creates isolated candidate artifacts.
# Passing the pipeline is NOT proof of electrical correctness; agent must inspect
# the candidate image, compare connectivity, and report the region to the owner.

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Board,
    [string]$OutputDir = "",
    [int]$MaxPasses = 20,
    [switch]$AllowDrcViolations
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$boardPath = (Resolve-Path $Board).Path
$boardDir = Split-Path -Parent $boardPath
$base = [IO.Path]::GetFileNameWithoutExtension($boardPath)
if (-not $OutputDir) { $OutputDir = Join-Path $boardDir "routing_candidate" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputDir = (Resolve-Path $OutputDir).Path

# Locate KiCad 10 tools. Allow explicit environment overrides for another machine.
$kicadBin = $env:KICAD_BIN
if (-not $kicadBin) { $kicadBin = "C:\Program Files\KiCad\10.0\bin" }
$py = Join-Path $kicadBin "python.exe"
$cli = Join-Path $kicadBin "kicad-cli.exe"
$jar = Join-Path $repo "setup\freerouting\freerouting-2.5.0.jar"
foreach ($p in @($py,$cli,$jar)) { if (-not (Test-Path $p)) { throw "Missing tool: $p. Run setup\setup.ps1 first." } }

$dsn = Join-Path $OutputDir "$base.dsn"
$ses = Join-Path $OutputDir "$base.ses"
$candidate = Join-Path $OutputDir "$base-routed.kicad_pcb"
$drc = Join-Path $OutputDir "$base-drc.json"
$image = Join-Path $OutputDir "$base-routed.png"

Write-Host "[1/5] Export DSN (input board is read-only)..."
& $py (Join-Path $repo "tools\export_dsn.py") $boardPath $dsn
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $dsn)) { throw "DSN export failed. Input board untouched; see export_dsn.py output." }

Write-Host "[2/5] Freerouting JAR..."
& java -jar $jar -de $dsn -do $ses -mp $MaxPasses
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ses)) { throw "Freerouting failed or produced no SES. Input board untouched." }

Write-Host "[3/5] Import SES into a candidate copy..."
& $py (Join-Path $repo "tools\import_ses.py") $boardPath $ses $candidate
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $candidate)) { throw "SES import failed. Input board untouched." }

Write-Host "[4/5] Native KiCad DRC on candidate..."
& $cli pcb drc $candidate -o $drc --format json --severity-all
$drcExit = $LASTEXITCODE
if (-not (Test-Path $drc)) { throw "DRC did not produce a report." }

Write-Host "[5/5] Render candidate image..."
& $cli pcb render $candidate -o $image --floor --width 1600 --height 1200 --quality high
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $image)) { Write-Warning "3D image render failed; candidate and DRC are still available." }

# Summarize DRC counts from JSON; don't infer electrical success from route score.
$report = Get-Content $drc -Raw | ConvertFrom-Json
$violations = @($report.violations).Count
$unconnected = @($report.unconnected_items).Count
Write-Host ""
Write-Host "Candidate:   $candidate"
Write-Host "DSN / SES:   $dsn / $ses"
Write-Host "DRC report:  $drc (violations=$violations, unconnected=$unconnected)"
Write-Host "Image:       $image"
if (($violations -gt 0 -or $unconnected -gt 0) -and -not $AllowDrcViolations) {
    Write-Error "Candidate has DRC/connectivity findings. Not accepted; inspect report/image and iterate placement/routing."
    exit 3
}
Write-Host "Pipeline completed. Candidate is NOT accepted until agent visual + logic review passes."
exit 0
