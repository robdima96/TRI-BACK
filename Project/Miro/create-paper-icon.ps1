$ErrorActionPreference = "Stop"

# ===== Configuration =====
$token = (Get-Content (Join-Path $PSScriptRoot ".env") | Where-Object { $_ -match "^MIRO_ACCESS_TOKEN=" }) -replace "^MIRO_ACCESS_TOKEN=", ""
$baseUri = "https://api.miro.com/v2"
$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}
$boardId = "uXjVGiAx8aE="

# ===== API Helper with rate-limit handling =====
function Invoke-Miro {
    param([string]$Method, [string]$Uri, [string]$Body = $null)
    for ($try = 1; $try -le 5; $try++) {
        try {
            $p = @{ Uri=$Uri; Headers=$headers; Method=$Method; ContentType="application/json"; UseBasicParsing=$true }
            if ($Body) { $p.Body = [System.Text.Encoding]::UTF8.GetBytes($Body) }
            $resp = Invoke-WebRequest @p
            $rem = $resp.Headers["X-RateLimit-Remaining"]
            if ($rem -is [array]) { $rem = $rem[0] }
            if ($rem -and [int]$rem -lt 3) {
                Write-Host "    [Rate limit low ($rem remaining), pausing 15s]" -ForegroundColor Yellow
                Start-Sleep -Seconds 15
            } else {
                Start-Sleep -Milliseconds 450
            }
            return ($resp.Content | ConvertFrom-Json)
        } catch {
            $code = 0
            if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
            if ($code -eq 429) {
                Write-Host "    [429 Rate limited - waiting 60s] (attempt $try)" -ForegroundColor Red
                Start-Sleep -Seconds 60
            } else {
                if ($try -eq 5) { throw }
                Write-Host "    [Error: $($_.Exception.Message) - retrying in 5s] (attempt $try)" -ForegroundColor Red
                Start-Sleep -Seconds 5
            }
        }
    }
}

# ===== Find empty space on the board =====
Write-Host "=== Scanning board for existing items ===" -ForegroundColor Cyan
$allItems = @()
$cursor = ""
do {
    $uri = "$baseUri/boards/$boardId/items?limit=50"
    if ($cursor) { $uri += "&cursor=$cursor" }
    $page = Invoke-Miro -Method Get -Uri $uri
    $allItems += $page.data
    $cursor = if ($page.cursor) { $page.cursor } else { "" }
} while ($cursor)

Write-Host "Found $($allItems.Count) existing items on board"

$maxX = -99999; $maxY = -99999
$minX = 99999;  $minY = 99999
foreach ($item in $allItems) {
    if ($null -ne $item.position) {
        $ix = [double]$item.position.x
        $iy = [double]$item.position.y
        $iw = 0; $ih = 0
        if ($null -ne $item.geometry) {
            if ($null -ne $item.geometry.width)  { $iw = [double]$item.geometry.width }
            if ($null -ne $item.geometry.height) { $ih = [double]$item.geometry.height }
        }
        $right  = $ix + $iw / 2
        $bottom = $iy + $ih / 2
        $left   = $ix - $iw / 2
        $top    = $iy - $ih / 2
        if ($right  -gt $maxX) { $maxX = $right }
        if ($bottom -gt $maxY) { $maxY = $bottom }
        if ($left   -lt $minX) { $minX = $left }
        if ($top    -lt $minY) { $minY = $top }
    }
}

if ($allItems.Count -eq 0) {
    $cx = 0; $cy = 0
} else {
    $cx = $maxX + 400
    $cy = ($minY + $maxY) / 2
}

Write-Host "Placing icon at ($cx, $cy) - clear of existing content" -ForegroundColor Green

# ===== Build Research Paper Icon =====
Write-Host "`n=== Creating research paper icon ===" -ForegroundColor Yellow

$paperW = 140
$paperH = 180
$foldSize = 30
$lineW = 80
$lineH = 8
$lineGap = 16

# 1. Paper body (main white rectangle with shadow effect)
$shadow = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
    data     = @{ content = ""; shape = "rectangle" }
    style    = @{ fillColor = "#D5D8DC"; borderColor = "#D5D8DC"; borderWidth = "1" }
    position = @{ x = $cx + 4; y = $cy + 4 }
    geometry = @{ width = $paperW; height = $paperH }
} | ConvertTo-Json -Depth 5)
Write-Host "  Shadow layer created"

$paperBody = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
    data     = @{ content = ""; shape = "rectangle" }
    style    = @{ fillColor = "#FFFFFF"; borderColor = "#ABB2B9"; borderWidth = "2" }
    position = @{ x = $cx; y = $cy }
    geometry = @{ width = $paperW; height = $paperH }
} | ConvertTo-Json -Depth 5)
Write-Host "  Paper body created"

# 2. Fold triangle (top-right corner)
$foldX = $cx + $paperW / 2 - $foldSize / 2
$foldY = $cy - $paperH / 2 + $foldSize / 2
$fold = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
    data     = @{ content = ""; shape = "triangle" }
    style    = @{ fillColor = "#E8E8E8"; borderColor = "#ABB2B9"; borderWidth = "2" }
    position = @{ x = $foldX; y = $foldY }
    geometry = @{ width = $foldSize; height = $foldSize }
} | ConvertTo-Json -Depth 5)
Write-Host "  Corner fold created"

# 3. Title bar (blue header at top of paper)
$titleBarY = $cy - $paperH / 2 + 30
$titleBar = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
    data     = @{ content = ""; shape = "rectangle" }
    style    = @{ fillColor = "#2D5F8A"; borderColor = "#2D5F8A"; borderWidth = "1" }
    position = @{ x = $cx; y = $titleBarY }
    geometry = @{ width = ($paperW - 30); height = 12 }
} | ConvertTo-Json -Depth 5)
Write-Host "  Title bar created"

# 4. Subtitle line
$subtitleY = $titleBarY + 16
$subtitle = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
    data     = @{ content = ""; shape = "rectangle" }
    style    = @{ fillColor = "#85C1E9"; borderColor = "#85C1E9"; borderWidth = "1" }
    position = @{ x = $cx; y = $subtitleY }
    geometry = @{ width = ($paperW - 50); height = 8 }
} | ConvertTo-Json -Depth 5)
Write-Host "  Subtitle line created"

# 5. Text lines (body text representation)
$firstLineY = $subtitleY + 28
for ($i = 0; $i -lt 6; $i++) {
    $ly = $firstLineY + $i * $lineGap
    $lw = if ($i -eq 5) { $lineW - 25 } else { $lineW + (Get-Random -Minimum -10 -Maximum 15) }
    $null = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
        data     = @{ content = ""; shape = "rectangle" }
        style    = @{ fillColor = "#D5D8DC"; borderColor = "#D5D8DC"; borderWidth = "1" }
        position = @{ x = $cx - 5; y = $ly }
        geometry = @{ width = $lw; height = $lineH }
    } | ConvertTo-Json -Depth 5)
}
Write-Host "  Text lines created (6 lines)"

# 6. Label underneath
$labelY = $cy + $paperH / 2 + 30
$label = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/texts" -Body (@{
    data     = @{ content = "<b>Research Paper</b>" }
    style    = @{ fontSize = "14"; textAlign = "center"; color = "#1B2A4A" }
    position = @{ x = $cx; y = $labelY }
    geometry = @{ width = 200 }
} | ConvertTo-Json -Depth 5)
Write-Host "  Label created"

# ===== Done =====
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "COMPLETE! Research paper icon created." -ForegroundColor Green
Write-Host "Position: ($cx, $cy)"
Write-Host "Board URL: https://miro.com/app/board/$boardId/" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
