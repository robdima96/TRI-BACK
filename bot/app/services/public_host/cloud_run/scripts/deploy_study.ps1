# Deploy tri-back-study to Cloud Run (public UI) wired to tri-back.
# Prerequisites: study image in Artifact Registry; bot service healthy; GCS bucket exists.
#
# Usage (from repo root):
#   $env:TRI_BACK_BOT_API_KEY = "..."
#   $env:TRI_BACK_ADMIN_PASSWORD = "..."
#   .\bot\app\services\public_host\cloud_run\scripts\deploy_study.ps1

param(
  [string]$ProjectId = $(if ($env:TRI_BACK_GCP_PROJECT) { $env:TRI_BACK_GCP_PROJECT } else { "YOUR_GCP_PROJECT" }),
  [string]$Region = "us-central1",
  [string]$Service = "tri-back-study",
  [string]$BotService = "tri-back",
  [string]$Bucket = $(if ($env:TRI_BACK_GCS_BUCKET) { $env:TRI_BACK_GCS_BUCKET } else { "digimsk-cloudrun-$ProjectId" }),
  [string]$Image = "",
  [string]$Memory = "2Gi",
  [string]$Cpu = "2",
  [int]$MaxInstances = 1,
  [int]$MinInstances = 0,
  [string]$BotApiKey = $(if ($env:TRI_BACK_BOT_API_KEY) { $env:TRI_BACK_BOT_API_KEY } else { "" }),
  [string]$AdminPassword = $(if ($env:TRI_BACK_ADMIN_PASSWORD) { $env:TRI_BACK_ADMIN_PASSWORD } else { "" }),
  [string]$PublicBaseUrl = "",
  [string]$ChatbotBaseUrl = ""
)

$ErrorActionPreference = "Stop"

if (-not $Image) {
  $Image = "$Region-docker.pkg.dev/$ProjectId/tri-back/tri-back-study:latest"
}
if (-not $BotApiKey) { throw "Set TRI_BACK_BOT_API_KEY." }
if (-not $AdminPassword) { throw "Set TRI_BACK_ADMIN_PASSWORD." }

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
  "TRI_BACK_BOT_API_KEY=$BotApiKey",
  "TRI_BACK_ADMIN_PASSWORD=$AdminPassword",
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
  "--service-account=runtime-sa@$ProjectId.iam.gserviceaccount.com",
  "--add-volume=name=tri-back-gcs,type=cloud-storage,bucket=$Bucket",
  "--add-volume-mount=volume=tri-back-gcs,mount-path=/mnt/tri-back",
  "--set-env-vars=$envVars"
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

$studySa = "runtime-sa@$ProjectId.iam.gserviceaccount.com"
Write-Host "Granting roles/run.invoker on $BotService to $studySa"
gcloud run services add-iam-policy-binding $BotService `
  --project=$ProjectId `
  --region=$Region `
  --member="serviceAccount:$studySa" `
  --role="roles/run.invoker" `
  --quiet

Write-Host ""
Write-Host "Study UI: $studyUrl"
Write-Host "Admin login: username admin / TRI_BACK_ADMIN_PASSWORD"
Write-Host "If the login page loads but WebSocket fails, rebuild with PUBLIC_BASE_URL=$studyUrl"
