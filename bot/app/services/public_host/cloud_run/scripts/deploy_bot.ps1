# Deploy tri-back to Cloud Run with GCS volume at /mnt/tri-back.
# Prerequisites: image in Artifact Registry; bucket populated via upload_gcs_assets.ps1
# Required env: TRI_BACK_GCP_PROJECT, TRI_BACK_GCS_BUCKET, TRI_BACK_RUNTIME_SA,
#               TRI_BACK_BOT_API_KEY (Secret Manager secret of the same name must exist).
#
# Usage:
#   .\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1
#   .\bot\app\services\public_host\cloud_run\scripts\deploy_bot.ps1 -Image "REGION-docker.pkg.dev/PROJECT/tri-back/tri-back-bot:latest"

param(
  [string]$ProjectId = $(if ($env:TRI_BACK_GCP_PROJECT) { $env:TRI_BACK_GCP_PROJECT } else { "" }),
  [string]$Region = "us-central1",
  [string]$VertexLocation = $(if ($env:TRI_BACK_VERTEX_LOCATION) { $env:TRI_BACK_VERTEX_LOCATION } else { "us" }),
  [string]$GeneratorModel = $(if ($env:TRI_BACK_GENERATOR_MODEL) { $env:TRI_BACK_GENERATOR_MODEL } else { "gemini-3.5-flash-lite" }),
  [string]$Service = "tri-back",
  [string]$Bucket = $(if ($env:TRI_BACK_GCS_BUCKET) { $env:TRI_BACK_GCS_BUCKET } else { "" }),
  [string]$Image = "",
  [string]$Memory = "8Gi",
  [string]$Cpu = "4",
  [int]$MaxInstances = 1,
  [int]$MinInstances = 0,
  [string]$BotApiKeySecret = $(if ($env:TRI_BACK_BOT_API_KEY_SECRET) { $env:TRI_BACK_BOT_API_KEY_SECRET } else { "TRI_BACK_BOT_API_KEY" }),
  [string]$ServiceAccount = $(if ($env:TRI_BACK_RUNTIME_SA) { $env:TRI_BACK_RUNTIME_SA } else { "" })
)

$ErrorActionPreference = "Stop"

if (-not $ProjectId) { throw "Set TRI_BACK_GCP_PROJECT." }
if (-not $Bucket) { throw "Set TRI_BACK_GCS_BUCKET." }
if (-not $ServiceAccount) { throw "Set TRI_BACK_RUNTIME_SA (runtime service account email)." }
if (-not $env:TRI_BACK_BOT_API_KEY -and -not $env:TRI_BACK_BOT_API_KEY_SECRET) {
  throw "Set TRI_BACK_BOT_API_KEY (or TRI_BACK_BOT_API_KEY_SECRET naming an existing Secret Manager secret)."
}

if (-not $Image) {
  $Image = "$Region-docker.pkg.dev/$ProjectId/tri-back/tri-back-bot:latest"
}

Write-Host "Deploying $Service"
Write-Host "  image:  $Image"
Write-Host "  bucket: gs://$Bucket -> /mnt/tri-back"
Write-Host "  vertex: $GeneratorModel @ $VertexLocation"
Write-Host "  max-instances: $MaxInstances  min-instances: $MinInstances"

$envVars = @(
  "TRI_BACK_RAG=0",
  "TRI_BACK_GRAPH_RAG=1",
  "TRI_BACK_LOAD_RAG=0",
  "TRI_BACK_GENERATOR_BACKEND=vertex",
  "TRI_BACK_GENERATOR_MODEL=$GeneratorModel",
  "TRI_BACK_VERTEX_PROJECT_ID=$ProjectId",
  "TRI_BACK_VERTEX_LOCATION=$VertexLocation",
  "TRI_BACK_GLINER_MODEL_DIR=/mnt/tri-back/models/gliner",
  "TRI_BACK_QUERY_CLASSIFIER_DIR=/mnt/tri-back/models/query_classifier",
  "TRI_BACK_SAT_SPLITTER_DIR=/mnt/tri-back/models/sat_splitter",
  "TRI_BACK_GRAPH_CSV=/mnt/tri-back/graph/v4/red_flags_edges_v4_2026.9.10.csv",
  "TRI_BACK_GRAPH_FACTORS=/mnt/tri-back/graph/v4/red_flags_factors_v4_2026.9.10.csv",
  "TRI_BACK_GRAPH_INVENTORY=/mnt/tri-back/graph/v4/red_flags_inventory_v4_2026.9.10.json",
  "TRI_BACK_SESSION_STORE_DIR=/mnt/tri-back/sessions",
  "TRI_BACK_CHECKPOINT_SQLITE=/tmp/langgraph_checkpoints.sqlite",
  "TRI_BACK_LOAD_GLINER=1",
  "TRI_BACK_LOAD_NER=1",
  "TRI_BACK_LOAD_QUERY_CLASSIFIER=1",
  "TRI_BACK_LOAD_SAT_SPLITTER=1"
) -join ","

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
  "--set-env-vars=$envVars",
  "--set-secrets=TRI_BACK_BOT_API_KEY=${BotApiKeySecret}:latest"
)

& gcloud @deployArgs
if ($LASTEXITCODE -ne 0) { throw "gcloud run deploy failed" }

Write-Host "Deployed. Grant the service runtime SA Storage Object User on gs://$Bucket if mounts fail."
Write-Host "Grant roles/secretmanager.secretAccessor on $BotApiKeySecret to $ServiceAccount if the container lacks the key."
Write-Host "Session JSON will appear under gs://$Bucket/sessions/"
