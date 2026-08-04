# Deploy digimsk-bot to Cloud Run with GCS volume at /mnt/digimsk.
# Prerequisites: image in Artifact Registry; bucket populated via upload_gcs_assets.ps1
#
# Usage:
#   .\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1
#   .\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1 -Image "us-central1-docker.pkg.dev/.../digimsk-bot:latest"

param(
  [string]$ProjectId = $(if ($env:DIGIMSK_GCP_PROJECT) { $env:DIGIMSK_GCP_PROJECT } else { "YOUR_GCP_PROJECT" }),
  [string]$Region = "us-central1",
  [string]$Service = "digimsk-bot",
  [string]$Bucket = $(if ($env:DIGIMSK_GCS_BUCKET) { $env:DIGIMSK_GCS_BUCKET } else { "digimsk-cloudrun-$ProjectId" }),
  [string]$Image = "",
  [string]$Memory = "8Gi",
  [string]$Cpu = "4",
  [int]$MaxInstances = 1,
  [int]$MinInstances = 0,
  [string]$BotApiKey = $(if ($env:DIGIMSK_BOT_API_KEY) { $env:DIGIMSK_BOT_API_KEY } else { "" })
)

$ErrorActionPreference = "Stop"

if (-not $Image) {
  $Image = "$Region-docker.pkg.dev/$ProjectId/digimsk/digimsk-bot:latest"
}

Write-Host "Deploying $Service"
Write-Host "  image:  $Image"
Write-Host "  bucket: gs://$Bucket -> /mnt/digimsk"
Write-Host "  max-instances: $MaxInstances  min-instances: $MinInstances"

$envVars = @(
  "DIGIMSK_RAG=0",
  "DIGIMSK_GRAPH_RAG=1",
  "DIGIMSK_LOAD_RAG=0",
  "DIGIMSK_GENERATOR_BACKEND=vertex",
  "DIGIMSK_VERTEX_PROJECT_ID=$ProjectId",
  "DIGIMSK_VERTEX_LOCATION=$Region",
  "DIGIMSK_GLINER_MODEL_DIR=/mnt/digimsk/models/gliner",
  "DIGIMSK_GRAPH_CSV=/mnt/digimsk/graph/v2/red_flags_manual_v2.csv",
  "DIGIMSK_GRAPH_INVENTORY=/mnt/digimsk/graph/v2/inventory.json",
  "DIGIMSK_SESSION_STORE_DIR=/mnt/digimsk/sessions",
  "DIGIMSK_CHECKPOINT_SQLITE=/tmp/langgraph_checkpoints.sqlite",
  "DIGIMSK_LOAD_GLINER=1",
  "DIGIMSK_LOAD_NER=1"
) -join ","

if ($BotApiKey) {
  $envVars = "$envVars,DIGIMSK_BOT_API_KEY=$BotApiKey"
}

# Single-container shorthand: mount-path on --add-volume
# https://cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts
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
  "--add-volume=name=digimsk-gcs,type=cloud-storage,bucket=$Bucket",
  "--add-volume-mount=volume=digimsk-gcs,mount-path=/mnt/digimsk",
  "--set-env-vars=$envVars"
)

& gcloud @deployArgs
if ($LASTEXITCODE -ne 0) { throw "gcloud run deploy failed" }

Write-Host "Deployed. Grant the service runtime SA Storage Object User on gs://$Bucket if mounts fail."
Write-Host "Session JSON will appear under gs://$Bucket/sessions/"
