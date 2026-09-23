# Deploy tri-back-study to Cloud Run (public UI) wired to tri-back.
# Prerequisites: study image in Artifact Registry; bot service healthy; GCS bucket exists.
# Required env: TRI_BACK_GCP_PROJECT, TRI_BACK_GCS_BUCKET, TRI_BACK_RUNTIME_SA.
# Secret Manager secrets TRI_BACK_BOT_API_KEY and TRI_BACK_ADMIN_PASSWORD must exist.
#
# Usage (from repo root):
#   $env:TRI_BACK_GCP_PROJECT = "..."
#   $env:TRI_BACK_GCS_BUCKET = "..."
#   $env:TRI_BACK_RUNTIME_SA = "runtime-sa@PROJECT.iam.gserviceaccount.com"
#   .\bot\app\services\public_host\cloud_run\scripts\deploy_study.ps1

param(
  [string]$ProjectId = $(if ($env:TRI_BACK_GCP_PROJECT) { $env:TRI_BACK_GCP_PROJECT } else { "" }),
  [string]$Region = "us-central1",
  [string]$Service = "tri-back-study",
  [string]$BotService = "tri-back",
  [string]$Bucket = $(if ($env:TRI_BACK_GCS_BUCKET) { $env:TRI_BACK_GCS_BUCKET } else { "" }),
  [string]$Image = "",
  [string]$Memory = "2Gi",
  [string]$Cpu = "2",
  [int]$MaxInstances = 1,
  [int]$MinInstances = 0,
  [string]$BotApiKeySecret = $(if ($env:TRI_BACK_BOT_API_KEY_SECRET) { $env:TRI_BACK_BOT_API_KEY_SECRET } else { "TRI_BACK_BOT_API_KEY" }),
  [string]$AdminPasswordSecret = $(if ($env:TRI_BACK_ADMIN_PASSWORD_SECRET) { $env:TRI_BACK_ADMIN_PASSWORD_SECRET } else { "TRI_BACK_ADMIN_PASSWORD" }),
  [string]$ServiceAccount = $(if ($env:TRI_BACK_RUNTIME_SA) { $env:TRI_BACK_RUNTIME_SA } else { "" }),
  [string]$PublicBaseUrl = "",
  [string]$ChatbotBaseUrl = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProjectId) { throw "Set TRI_BACK_GCP_PROJECT." }
if (-not $Bucket) { throw "Set TRI_BACK_GCS_BUCKET." }
if (-not $ServiceAccount) { throw "Set TRI_BACK_RUNTIME_SA (runtime service account email)." }

if (-not $Image) {
  $Image = "$Region-docker.pkg.dev/$ProjectId/tri-back/tri-back-study:latest"
}

if (-not $ChatbotBaseUrl) {
  $ChatbotBaseUrl = (gcloud run services describe $BotService --project=$ProjectId --region=$Region --format="value(status.url)").Trim()
  if (-not $ChatbotBaseUrl) { throw "Could not resolve bot URL for service $BotService" }
}

Write-Host "Deploying $Service"
Write-Host "  image:  $Image"
Write-Host "  bot:    $ChatbotBaseUrl"
Write-Host "  bucket: gs://$Bucket -> /mnt/tri-back"

$envVars = @(
  "TRI_BACK_PUBLIC_ACCESS=1",
  "CHATBOT_BASE_URL=$ChatbotBaseUrl",
  "TRI_BACK_STUDY_DB=/mnt/tri-back/study/tri_back.db",
  "TRI_BACK_SESSIONS_DIR=/mnt/tri-back/sessions",
  "REFLEX_REDIS_URL=redis://127.0.0.1:6379"
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
  "--session-affinity",
  "--allow-unauthenticated",
  "--port=8080",
  "--service-account=$ServiceAccount",
  "--add-volume=name=tri-back-gcs,type=cloud-storage,bucket=$Bucket",
  "--add-volume-mount=volume=tri-back-gcs,mount-path=/mnt/tri-back",
  "--set-env-vars=$envVars",
  "--set-secrets=TRI_BACK_BOT_API_KEY=${BotApiKeySecret}:latest,TRI_BACK_ADMIN_PASSWORD=${AdminPasswordSecret}:latest"
)

& gcloud @deployArgs
if ($LASTEXITCODE -ne 0) { throw "gcloud run deploy failed" }

$studyUrl = (gcloud run services describe $Service --project=$ProjectId --region=$Region --format="value(status.url)").Trim()
if ($PublicBaseUrl) {
  $studyUrl = $PublicBaseUrl.TrimEnd("/")
} else {
  $preferred = (gcloud run services describe $Service --project=$ProjectId --region=$Region --format="yaml(status)" 2>$null) |
    Select-String -Pattern "https://$Service-[0-9]+\.us-central1\.run\.app" |
    ForEach-Object { $_.Matches.Value } |
    Select-Object -First 1
  if ($preferred) { $studyUrl = $preferred }
}

Write-Host "Setting public base URL env to $studyUrl"
gcloud run services update $Service --project=$ProjectId --region=$Region `
  --update-env-vars="TRI_BACK_PUBLIC_BASE_URL=$studyUrl,API_URL=$studyUrl,DEPLOY_URL=$studyUrl,REFLEX_API_URL=$studyUrl"
if ($LASTEXITCODE -ne 0) { throw "gcloud run services update failed" }

Write-Host "Granting roles/run.invoker on $BotService to $ServiceAccount"
gcloud run services add-iam-policy-binding $BotService `
  --project=$ProjectId `
  --region=$Region `
  --member="serviceAccount:$ServiceAccount" `
  --role="roles/run.invoker" `
  --quiet

Write-Host ""
Write-Host "Study UI: $studyUrl"
Write-Host "Admin login: username admin / TRI_BACK_ADMIN_PASSWORD"
Write-Host "Grant roles/secretmanager.secretAccessor on the API key and admin password secrets to $ServiceAccount."
Write-Host "If the login page loads but WebSocket fails, rebuild with PUBLIC_BASE_URL=$studyUrl"
