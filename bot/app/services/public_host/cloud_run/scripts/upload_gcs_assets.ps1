# Upload GliNER + red-flags v2 graph to GCS; ensure sessions/ prefix exists.
# Requires: gcloud auth, permissions to create/write the bucket.
# Default bucket stays digimsk-cloudrun-$ProjectId (GCS cannot rename).
#
# Usage (from repo root):
#   .\bot\app\services\public_host\cloud_run\scripts\upload_gcs_assets.ps1
#   .\bot\app\services\public_host\cloud_run\scripts\upload_gcs_assets.ps1 -GliNERDir "E:\TRI-BACK\GliNER-BioMed"

param(
  [string]$ProjectId = $(if ($env:TRI_BACK_GCP_PROJECT) { $env:TRI_BACK_GCP_PROJECT } elseif ($env:DIGIMSK_GCP_PROJECT) { $env:DIGIMSK_GCP_PROJECT } else { "YOUR_GCP_PROJECT" }),
  [string]$Bucket = $(if ($env:TRI_BACK_GCS_BUCKET) { $env:TRI_BACK_GCS_BUCKET } elseif ($env:DIGIMSK_GCS_BUCKET) { $env:DIGIMSK_GCS_BUCKET } else { "digimsk-cloudrun-$ProjectId" }),
  [string]$Region = $(if ($env:TRI_BACK_VERTEX_LOCATION) { $env:TRI_BACK_VERTEX_LOCATION } elseif ($env:DIGIMSK_VERTEX_LOCATION) { $env:DIGIMSK_VERTEX_LOCATION } else { "us-central1" }),
  [string]$GliNERDir = $(if ($env:TRI_BACK_GLINER_MODEL_DIR) { $env:TRI_BACK_GLINER_MODEL_DIR } elseif ($env:DIGIMSK_GLINER_MODEL_DIR) { $env:DIGIMSK_GLINER_MODEL_DIR } elseif (Test-Path "E:\TRI-BACK\GliNER-BioMed") { "E:\TRI-BACK\GliNER-BioMed" } else { "E:\DigiMSKbot\GliNER-BioMed" }),
  [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $RepoRoot) {
  $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..\..\..")).Path
}

$GraphCsv = Join-Path $RepoRoot "bot\Knowledge Base\Red Flags\chunks\manual\red_flags_edges_v4_2026.9.10.csv"
$GraphFactors = Join-Path $RepoRoot "bot\Knowledge Base\Red Flags\chunks\manual\red_flags_factors_v4_2026.9.10.csv"
$GraphInv = Join-Path $RepoRoot "bot\Knowledge Base\Red Flags\chunks\manual\red_flags_inventory_v4_2026.9.10.json"

if (-not (Test-Path $GraphCsv)) { throw "Missing graph CSV: $GraphCsv" }
if (-not (Test-Path $GraphFactors)) { throw "Missing factors CSV: $GraphFactors" }
if (-not (Test-Path $GraphInv)) { throw "Missing inventory: $GraphInv" }
if (-not (Test-Path $GliNERDir)) {
  throw "GliNER directory not found: $GliNERDir - set -GliNERDir or TRI_BACK_GLINER_MODEL_DIR"
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

Write-Host "Uploading knowledge graph v4 ..."
gcloud storage cp "$GraphCsv" "$bucketUri/graph/v4/red_flags_edges_v4_2026.9.10.csv"
gcloud storage cp "$GraphFactors" "$bucketUri/graph/v4/red_flags_factors_v4_2026.9.10.csv"
gcloud storage cp "$GraphInv" "$bucketUri/graph/v4/red_flags_inventory_v4_2026.9.10.json"

Write-Host "Uploading GliNER model tree (may take a while) ..."
gcloud storage rsync --recursive "$GliNERDir" "$bucketUri/models/gliner"

Write-Host "Ensuring sessions/ prefix ..."
$tmp = New-TemporaryFile
Set-Content -Path $tmp.FullName -Value "TRI-BACK session store root`n" -NoNewline
gcloud storage cp $tmp.FullName "$bucketUri/sessions/.keep"
Remove-Item $tmp.FullName -Force

Write-Host ""
Write-Host "Done. Mount gs://$Bucket at /mnt/tri-back on tri-back."
Write-Host "  TRI_BACK_GLINER_MODEL_DIR=/mnt/tri-back/models/gliner"
Write-Host "  TRI_BACK_GRAPH_CSV=/mnt/tri-back/graph/v4/red_flags_edges_v4_2026.9.10.csv"
Write-Host "  TRI_BACK_GRAPH_FACTORS=/mnt/tri-back/graph/v4/red_flags_factors_v4_2026.9.10.csv"
Write-Host "  TRI_BACK_GRAPH_INVENTORY=/mnt/tri-back/graph/v4/red_flags_inventory_v4_2026.9.10.json"
Write-Host "  TRI_BACK_SESSION_STORE_DIR=/mnt/tri-back/sessions"
