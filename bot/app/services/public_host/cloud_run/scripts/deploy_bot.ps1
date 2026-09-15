# Deploy tri-back to Cloud Run with GCS volume at /mnt/tri-back.
# Prerequisites: image in Artifact Registry; bucket populated via upload_gcs_assets.ps1
#
# Usage:
#   .\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1
#   .\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1 -Image "us-central1-docker.pkg.dev/.../tri-back-bot:latest"

param(
  [string]$ProjectId = $(if ($env:TRI_BACK_GCP_PROJECT) { $env:TRI_BACK_GCP_PROJECT } else { "YOUR_GCP_PROJECT" }),
  [string]$Region = "us-central1",
  [string]$Service = "tri-back",
  [string]$Bucket = $(if ($env:TRI_BACK_GCS_BUCKET) { $env:TRI_BACK_GCS_BUCKET } else { "digimsk-cloudrun-$ProjectId" }),
  [string]$Image = "",
  [string]$Memory = "8Gi",
  [string]$Cpu = "4",
  [int]$MaxInstances = 1,
  [int]$MinInstances = 0,
  [string]$BotApiKey = $(if ($env:TRI_BACK_BOT_API_KEY) { $env:TRI_BACK_BOT_API_KEY } else { "" }),
  [string]$ServiceAccount = "runtime-sa@$ProjectId.iam.gserviceaccount.com"
)

$ErrorActionPreference = "Stop"

if (-not $Image) {
  $Image = "$Region-docker.pkg.dev/$ProjectId/tri-back/tri-back-bot:latest"
}

Write-Host "Deploying $Service"
Write-Host "  image:  $Image"
Write-Host "  bucket: gs://$Bucket -> /mnt/tri-back"
Write-Host "  max-instances: $MaxInstances  min-instances: $MinInstances"

$envVars = @(
  "TRI_BACK_RAG=0",
  "TRI_BACK_GRAPH_RAG=1",
  "TRI_BACK_LOAD_RAG=0",
  "TRI_BACK_GENERATOR_BACKEND=vertex",
  "TRI_BACK_VERTEX_PROJECT_ID=$ProjectId",
  "TRI_BACK_VERTEX_LOCATION=$Region",
  "TRI_BACK_GLINER_MODEL_DIR=/mnt/tri-back/models/gliner",
  "TRI_BACK_GRAPH_CSV=/mnt/tri-back/graph/v4/red_flags_edges_v4_2026.9.10.csv",
  "TRI_BACK_GRAPH_FACTORS=/mnt/tri-back/graph/v4/red_flags_factors_v4_2026.9.10.csv",
  "TRI_BACK_GRAPH_INVENTORY=/mnt/tri-back/graph/v4/red_flags_inventory_v4_2026.9.10.json",
  "TRI_BACK_SESSION_STORE_DIR=/mnt/tri-back/sessions",
  "TRI_BACK_CHECKPOINT_SQLITE=/tmp/langgraph_checkpoints.sqlite",
  "TRI_BACK_LOAD_GLINER=1",
  "TRI_BACK_LOAD_NER=1"
) -join ","

if ($BotApiKey) {
  $envVars = "$envVars,TRI_BACK_BOT_API_KEY=$BotApiKey"
}

$deployArgs = @(
  "run", "deploy", $Service,
  "--project=$ProjectId",
  "--region=$Region",
  "--image=$Image",
  "--memory=$Memory",
  "--cpu=$Cpu",
  "--max-instances=$MaxInstances",
  "--min-instances=$MinInstances",
  "--timeout=3600",
  "--no-allow-unauthenticated",
  "--service-account=$ServiceAccount",
  "--add-volume=name=tri-back-gcs,type=cloud-storage,bucket=$Bucket",
  "--add-volume-mount=volume=tri-back-gcs,mount-path=/mnt/tri-back",
  "--set-env-vars=$envVars"
)

& gcloud @deployArgs
if ($LASTEXITCODE -ne 0) { throw "gcloud run deploy failed" }

Write-Host "Deployed. Grant the service runtime SA Storage Object User on gs://$Bucket if mounts fail."
Write-Host "Session JSON will appear under gs://$Bucket/sessions/"
