# tools/route_pipeline.ps1 — reference-gated KiCad candidate check (no auto approval).
#
# Usage from rule/ repo root:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\route_pipeline.ps1 -Board board.kicad_pcb -SessionManifest session.json -CandidateBoard agent_candidate.kicad_pcb -IntentPath layout_intent.json
# Optional:
#   -OutputDir path       (default: <board directory>\routing_candidate)
#   -FreeroutingProposal (experimental whole-board autorouter, not agent-guided)
#   -MaxPasses 20         (Freerouting autorouter passes)
#   -AllowDrcViolations   (default: false; pipeline exits nonzero on DRC error)
#
# SAFETY: never overwrites the input board. Creates isolated candidate artifacts.
# Passing the pipeline is NOT proof of electrical correctness; agent must inspect
# the candidate image, compare connectivity, and report the region to the owner.

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Board,
    [Parameter(Mandatory=$true)][string]$SessionManifest,
    [string]$CandidateBoard = "",
    [string]$IntentPath = "",
    [switch]$FreeroutingProposal,
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
foreach ($p in @($py,$cli)) { if (-not (Test-Path $p)) { throw "Missing tool: $p. Run setup\setup.ps1 first." } }

$dsn = Join-Path $OutputDir "$base.dsn"
$ses = Join-Path $OutputDir "$base.ses"
$candidate = Join-Path $OutputDir "$base-routed.kicad_pcb"
$drc = Join-Path $OutputDir "$base-drc.json"
$image = Join-Path $OutputDir "$base-routed.png"

# Fail closed: never mutate or generate a routed board with missing reference evidence.
if ([bool]$CandidateBoard -eq [bool]$FreeroutingProposal) {
    throw "Select exactly one of -CandidateBoard (agent geometry) or -FreeroutingProposal (experimental)."
}
$manifestPath = (Resolve-Path $SessionManifest).Path
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
$manifestBoard = [IO.Path]::GetFullPath([IO.Path]::Combine((Split-Path -Parent $manifestPath), [string]$manifest.board))
if (-not [string]::Equals($manifestBoard, $boardPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Manifest board and -Board differ. GLOBAL STOP."
}
$boardHashBefore = (Get-FileHash -LiteralPath $boardPath -Algorithm SHA256).Hash
Write-Host "[1/5] Reference preflight for ALL regions ..."
$preflightDir = Join-Path $OutputDir "preflight"
& $py (Join-Path $repo "tools\session_gate.py") preflight $manifestPath --output-dir $preflightDir
if ($LASTEXITCODE -ne 0) { throw "GLOBAL STOP: incomplete reference evidence. See $preflightDir\preflight.json" }

Write-Host "[2/5] Generate isolated candidate ..."
if ($CandidateBoard) {
    $sourceCandidate = (Resolve-Path $CandidateBoard).Path
    if ([string]::Equals($sourceCandidate, $boardPath, [StringComparison]::OrdinalIgnoreCase) -or
        [string]::Equals($sourceCandidate, $candidate, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Candidate must be a separate file from input and pipeline output."
    }
    Copy-Item -LiteralPath $sourceCandidate -Destination $candidate -Force
    $engine = "AGENT_SUPPLIED"
} else {
    if (-not (Test-Path $jar)) { throw "Missing pinned Freerouting JAR: $jar" }
    & $py (Join-Path $repo "tools\export_dsn.py") $boardPath $dsn
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $dsn)) { throw "DSN export failed." }
    & java -jar $jar -de $dsn -do $ses -mp $MaxPasses
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ses)) { throw "Freerouting failed or SES missing." }
    & $py (Join-Path $repo "tools\import_ses.py") $boardPath $ses $candidate
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $candidate)) { throw "SES import failed." }
    $engine = "FREEROUTING_EXPERIMENTAL"
}
if (-not (Test-Path $candidate)) { throw "Candidate PCB missing after generation." }

Write-Host "[4/5] Native KiCad DRC on candidate..."
& $cli pcb drc $candidate -o $drc --format json --severity-all
$drcExit = $LASTEXITCODE
if (-not (Test-Path $drc)) { throw "DRC did not produce a report." }

Write-Host "[5/5] Render candidate image..."
& $cli pcb render $candidate -o $image --floor --width 1600 --height 1200 --quality high
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $image)) { Write-Warning "3D image render failed; candidate and DRC are still available." }

# Native DRC is authoritative for connectivity/clearance; audits add separate findings.
$report = Get-Content $drc -Raw | ConvertFrom-Json
if ($null -eq $report.violations -or $null -eq $report.unconnected_items) {
    throw "Invalid KiCad DRC JSON: expected violations and unconnected_items arrays."
}
$violations = @($report.violations).Count
$unconnected = @($report.unconnected_items).Count
$auditPath = Join-Path $OutputDir "$base-audit.json"
$keepoutLog = Join-Path $OutputDir "$base-keepout.txt"
& $py (Join-Path $repo "tools\drc_body_keepout.py") $candidate *> $keepoutLog
$keepoutExit = $LASTEXITCODE
$auditExit = 2
if ($IntentPath) {
    $intent = (Resolve-Path $IntentPath).Path
    & $py (Join-Path $repo "tools\layout_audit.py") $candidate $intent --json $auditPath | Out-Null
    $auditExit = $LASTEXITCODE
    if (-not (Test-Path $auditPath)) { $auditExit = 2 }
} else {
    Write-Warning "IntentPath absent; cannot approve candidate until geometry audit is run."
}
$boardHashAfter = (Get-FileHash -LiteralPath $boardPath -Algorithm SHA256).Hash
if ($boardHashAfter -ne $boardHashBefore) { throw "FATAL: original PCB hash changed." }
$findings = @()
if ($drcExit -ne 0 -or $violations -gt 0 -or $unconnected -gt 0) { $findings += "KiCad native DRC" }
if ($keepoutExit -ne 0) { $findings += "Body-keepout heuristic (inspect for exceptions)" }
if ($auditExit -ne 0) { $findings += "Geometry audit missing or findings" }
$summaryPath = Join-Path $OutputDir "$base-pipeline-summary.json"
[ordered]@{
    engine = $engine
    input_board_sha256 = $boardHashBefore
    candidate_board = $candidate
    candidate_sha256 = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
    drc = $drc
    drc_violations = $violations
    drc_unconnected = $unconnected
    geometry_audit = $(if (Test-Path $auditPath) { $auditPath } else { $null })
    keepout_log = $keepoutLog
    supplemental_render = $(if (Test-Path $image) { $image } else { $null })
    findings = $findings
    approval = "PENDING"
    accepted = $false
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $summaryPath
Write-Host "Candidate: $candidate"
Write-Host "Native DRC: violations=$violations, unconnected=$unconnected"
Write-Host "Summary: $summaryPath"
Write-Host "NOT APPROVED: produce F.Cu/B.Cu screenshots and run session_gate.py review for owner batch approval."
if ($findings.Count -gt 0 -and -not $AllowDrcViolations) { exit 3 }
exit 0
