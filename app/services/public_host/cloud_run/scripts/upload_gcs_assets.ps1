# Upload GliNER + red-flags v2 graph to GCS; ensure sessions/ prefix exists.
# Requires: gcloud auth, permissions to create/write the bucket.
#
# Usage (from repo root):
#   .\bot\app\services\public_host\cloud_run\scripts\upload_gcs_assets.ps1
#   .\bot\app\services\public_host\cloud_run\scripts\upload_gcs_assets.ps1 -GliNERDir "E:\DigiMSKbot\GliNER-BioMed"

param(
  [string]$ProjectId = $(if ($env:DIGIMSK_GCP_PROJECT) { $env:DIGIMSK_GCP_PROJECT } else { "YOUR_GCP_PROJECT" }),
  [string]$Bucket = $(if ($env:DIGIMSK_GCS_BUCKET) { $env:DIGIMSK_GCS_BUCKET } else { "digimsk-cloudrun-$ProjectId" }),
  [string]$Region = $(if ($env:DIGIMSK_VERTEX_LOCATION) { $env:DIGIMSK_VERTEX_LOCATION } else { "us-central1" }),
  [string]$GliNERDir = $(if ($env:DIGIMSK_GLINER_MODEL_DIR) { $env:DIGIMSK_GLINER_MODEL_DIR } else { "E:\DigiMSKbot\GliNER-BioMed" }),
  [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  # scripts -> cloud_run -> public_host -> services -> app -> bot (git root)
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..\..")).Path
}

# Knowledge graph packs live in the DigiMSKbot workspace sibling of this git repo.
$WorkspaceRoot = (Resolve-Path (Join-Path $RepoRoot "..")).Path
$GraphCsv = Join-Path $WorkspaceRoot "Graphs\backups\red flags\v2\source\red_flags_manual_v2.csv"
$GraphInv = Join-Path $WorkspaceRoot "Graphs\backups\red flags\v2\inventory.json"

if (-not (Test-Path $GraphCsv)) { throw "Missing graph CSV: $GraphCsv" }
if (-not (Test-Path $GraphInv)) { throw "Missing inventory: $GraphInv" }
if (-not (Test-Path $GliNERDir)) {
  throw "GliNER directory not found: $GliNERDir — set -GliNERDir or DIGIMSK_GLINER_MODEL_DIR"
}

Write-Host "Project:  $ProjectId"
Write-Host "Bucket:   gs://$Bucket"
Write-Host "GliNER:   $GliNERDir"
Write-Host "Graph:    $GraphCsv"

gcloud config set project $ProjectId | Out-Null

$bucketUri = "gs://$Bucket"
$exists = $false
try {
  gcloud storage buckets describe $bucketUri 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { $exists = $true }
} catch { $exists = $false }

if (-not $exists) {
  Write-Host "Creating bucket $bucketUri in $Region ..."
  gcloud storage buckets create $bucketUri --project=$ProjectId --location=$Region --uniform-bucket-level-access
}

Write-Host "Uploading knowledge graph v2 ..."
gcloud storage cp "$GraphCsv" "$bucketUri/graph/v2/red_flags_manual_v2.csv"
gcloud storage cp "$GraphInv" "$bucketUri/graph/v2/inventory.json"

Write-Host "Uploading GliNER model tree (may take a while) ..."
gcloud storage rsync --recursive "$GliNERDir" "$bucketUri/models/gliner"

Write-Host "Ensuring sessions/ prefix ..."
$tmp = New-TemporaryFile
Set-Content -Path $tmp.FullName -Value "DigiMSK session store root`n" -NoNewline
gcloud storage cp $tmp.FullName "$bucketUri/sessions/.keep"
Remove-Item $tmp.FullName -Force

Write-Host ""
Write-Host "Done. Mount gs://$Bucket at /mnt/digimsk on digimsk-bot."
Write-Host "  DIGIMSK_GLINER_MODEL_DIR=/mnt/digimsk/models/gliner"
Write-Host "  DIGIMSK_GRAPH_CSV=/mnt/digimsk/graph/v2/red_flags_manual_v2.csv"
Write-Host "  DIGIMSK_GRAPH_INVENTORY=/mnt/digimsk/graph/v2/inventory.json"
Write-Host "  DIGIMSK_SESSION_STORE_DIR=/mnt/digimsk/sessions"
