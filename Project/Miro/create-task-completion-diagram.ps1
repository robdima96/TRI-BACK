. "$PSScriptRoot\miro-helpers.ps1"
Load-MiroEnv | Out-Null

$headers = Get-MiroHeaders
$boardId = $env:MIRO_BOARD_ID

# List boards to find the Brainstorming board
$boards = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards" -Headers $headers -Method Get
foreach ($b in $boards.data) {
    Write-Host "Board: '$($b.name)' ID: $($b.id)"
    if ($b.name -like "*Brainstorm*") {
        $boardId = $b.id
        Write-Host "  -> Using this board" -ForegroundColor Green
    }
}

Write-Host "`nUsing board ID: $boardId" -ForegroundColor Cyan

# Get existing items to find empty space
$existingItems = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards/$boardId/items?limit=50" -Headers $headers -Method Get
$maxX = 0; $maxY = 0
foreach ($item in $existingItems.data) {
    if ($item.position.x -gt $maxX) { $maxX = $item.position.x }
    if ($item.position.y -gt $maxY) { $maxY = $item.position.y }
}
Write-Host "Existing items: $($existingItems.data.Count), max position: ($maxX, $maxY)"

# Offset to place diagram in empty space (well below/right of existing content)
$offsetX = $maxX + 2000
$offsetY = 0

# Color definitions
$blueBox = "#2D7DC4"
$dbBlue = "#3B7DB5"
$white = "#ffffff"
$gray = "#666666"
$darkGray = "#4a4a4a"

function Invoke-MiroAPI {
    param([string]$Endpoint, [hashtable]$Body)
    $json = $Body | ConvertTo-Json -Depth 10
    $uri = "https://api.miro.com/v2/boards/$boardId/$Endpoint"
    try {
        $result = Invoke-RestMethod -Uri $uri -Headers $headers -Method Post -Body $json
        Start-Sleep -Milliseconds 300
        return $result
    } catch {
        Write-Host "ERROR on $Endpoint : $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Body: $json"
        return $null
    }
}

Write-Host "`nCreating diagram elements..." -ForegroundColor Yellow

# ============================================================
# COLUMN HEADERS (Text items)
# ============================================================
$textualFormText = Invoke-MiroAPI "texts" @{
    data = @{ content = "<b>Textual form</b>" }
    style = @{ fontSize = "18"; textAlign = "center"; color = "#333333" }
    position = @{ x = $offsetX + 250; y = $offsetY - 80 }
    geometry = @{ width = 200 }
}
Write-Host "Created: Textual form header (id=$($textualFormText.id))"

$logicalFormText = Invoke-MiroAPI "texts" @{
    data = @{ content = "<b>Logical form</b>" }
    style = @{ fontSize = "18"; textAlign = "center"; color = "#333333" }
    position = @{ x = $offsetX + 500; y = $offsetY - 80 }
    geometry = @{ width = 200 }
}
Write-Host "Created: Logical form header (id=$($logicalFormText.id))"

$programText = Invoke-MiroAPI "texts" @{
    data = @{ content = "<b>Program</b>" }
    style = @{ fontSize = "18"; textAlign = "center"; color = "#333333" }
    position = @{ x = $offsetX + 750; y = $offsetY - 80 }
    geometry = @{ width = 200 }
}
Write-Host "Created: Program header (id=$($programText.id))"

# ============================================================
# "Speech input" label (left side, top)
# ============================================================
$speechInputLabel = Invoke-MiroAPI "texts" @{
    data = @{ content = "Speech<br>input" }
    style = @{ fontSize = "14"; textAlign = "center"; color = "#333333" }
    position = @{ x = $offsetX + 0; y = $offsetY + 30 }
    geometry = @{ width = 100 }
}
Write-Host "Created: Speech input label (id=$($speechInputLabel.id))"

# ============================================================
# BLUE BOXES - Top row
# ============================================================
$asrBox = Invoke-MiroAPI "shapes" @{
    data = @{ content = "<p style='color:white;'><b>Automatic<br>speech<br>recognize</b></p>"; shape = "round_rectangle" }
    style = @{ fillColor = $blueBox; borderColor = $blueBox; fontSize = "14"; textAlign = "center"; fontFamily = "arial"; color = "#ffffff" }
    position = @{ x = $offsetX + 180; y = $offsetY + 30 }
    geometry = @{ width = 150; height = 100 }
}
Write-Host "Created: ASR box (id=$($asrBox.id))"

$luBox = Invoke-MiroAPI "shapes" @{
    data = @{ content = "<p style='color:white;'><b>Language<br>understanding</b></p>"; shape = "round_rectangle" }
    style = @{ fillColor = $blueBox; borderColor = $blueBox; fontSize = "14"; textAlign = "center"; fontFamily = "arial"; color = "#ffffff" }
    position = @{ x = $offsetX + 400; y = $offsetY + 30 }
    geometry = @{ width = 160; height = 100 }
}
Write-Host "Created: Language understanding box (id=$($luBox.id))"

# ============================================================
# BLUE BOXES - Middle (Dialog manager)
# ============================================================
$dmBox = Invoke-MiroAPI "shapes" @{
    data = @{ content = "<p style='color:white;'><b>Dialog<br>manager</b></p>"; shape = "round_rectangle" }
    style = @{ fillColor = $blueBox; borderColor = $blueBox; fontSize = "14"; textAlign = "center"; fontFamily = "arial"; color = "#ffffff" }
    position = @{ x = $offsetX + 600; y = $offsetY + 100 }
    geometry = @{ width = 140; height = 100 }
}
Write-Host "Created: Dialog manager box (id=$($dmBox.id))"

# ============================================================
# DATABASE shape (right side)
# ============================================================
$dbBox = Invoke-MiroAPI "shapes" @{
    data = @{ content = "<p style='color:white;'><b>Data-<br>base</b></p>"; shape = "can" }
    style = @{ fillColor = $dbBlue; borderColor = $dbBlue; fontSize = "14"; textAlign = "center"; fontFamily = "arial"; color = "#ffffff" }
    position = @{ x = $offsetX + 800; y = $offsetY + 80 }
    geometry = @{ width = 120; height = 130 }
}
Write-Host "Created: Database (id=$($dbBox.id))"

# ============================================================
# BLUE BOXES - Bottom row
# ============================================================
$lgBox = Invoke-MiroAPI "shapes" @{
    data = @{ content = "<p style='color:white;'><b>Language<br>generator</b></p>"; shape = "round_rectangle" }
    style = @{ fillColor = $blueBox; borderColor = $blueBox; fontSize = "14"; textAlign = "center"; fontFamily = "arial"; color = "#ffffff" }
    position = @{ x = $offsetX + 400; y = $offsetY + 180 }
    geometry = @{ width = 160; height = 100 }
}
Write-Host "Created: Language generator box (id=$($lgBox.id))"

$ttsBox = Invoke-MiroAPI "shapes" @{
    data = @{ content = "<p style='color:white;'><b>Text-to-<br>speech</b></p>"; shape = "round_rectangle" }
    style = @{ fillColor = $blueBox; borderColor = $blueBox; fontSize = "14"; textAlign = "center"; fontFamily = "arial"; color = "#ffffff" }
    position = @{ x = $offsetX + 180; y = $offsetY + 180 }
    geometry = @{ width = 150; height = 100 }
}
Write-Host "Created: Text-to-speech box (id=$($ttsBox.id))"

# ============================================================
# "Speech response" label (left side, bottom)
# ============================================================
$speechResponseLabel = Invoke-MiroAPI "texts" @{
    data = @{ content = "Speech<br>response" }
    style = @{ fontSize = "14"; textAlign = "center"; color = "#333333" }
    position = @{ x = $offsetX + 0; y = $offsetY + 180 }
    geometry = @{ width = 100 }
}
Write-Host "Created: Speech response label (id=$($speechResponseLabel.id))"

# ============================================================
# CAPTION at the bottom
# ============================================================
$captionText = Invoke-MiroAPI "texts" @{
    data = @{ content = "<b>Fig. 2  Illustration of a task-completion system</b>" }
    style = @{ fontSize = "20"; textAlign = "center"; color = "#333333" }
    position = @{ x = $offsetX + 400; y = $offsetY + 310 }
    geometry = @{ width = 600 }
}
Write-Host "Created: Caption (id=$($captionText.id))"

# ============================================================
# CONNECTORS
# ============================================================
Write-Host "`nCreating connectors..." -ForegroundColor Yellow

$connectorStyle = @{ strokeColor = "#666666"; strokeWidth = "3" }

# Speech input -> ASR
if ($speechInputLabel -and $asrBox) {
    $c1 = Invoke-MiroAPI "connectors" @{
        startItem = @{ id = $speechInputLabel.id }
        endItem = @{ id = $asrBox.id }
        style = $connectorStyle
        shape = "straight"
    }
    Write-Host "Connector: Speech input -> ASR (id=$($c1.id))"
}

# ASR -> Language understanding
if ($asrBox -and $luBox) {
    $c2 = Invoke-MiroAPI "connectors" @{
        startItem = @{ id = $asrBox.id }
        endItem = @{ id = $luBox.id }
        style = $connectorStyle
        shape = "straight"
    }
    Write-Host "Connector: ASR -> LU (id=$($c2.id))"
}

# Language understanding -> Dialog manager
if ($luBox -and $dmBox) {
    $c3 = Invoke-MiroAPI "connectors" @{
        startItem = @{ id = $luBox.id }
        endItem = @{ id = $dmBox.id }
        style = $connectorStyle
        shape = "straight"
    }
    Write-Host "Connector: LU -> DM (id=$($c3.id))"
}

# Dialog manager <-> Database (bidirectional - two connectors)
if ($dmBox -and $dbBox) {
    $c4 = Invoke-MiroAPI "connectors" @{
        startItem = @{ id = $dmBox.id }
        endItem = @{ id = $dbBox.id }
        style = $connectorStyle
        shape = "straight"
    }
    Write-Host "Connector: DM -> DB (id=$($c4.id))"
    
    $c5 = Invoke-MiroAPI "connectors" @{
        startItem = @{ id = $dbBox.id }
        endItem = @{ id = $dmBox.id }
        style = $connectorStyle
        shape = "straight"
    }
    Write-Host "Connector: DB -> DM (id=$($c5.id))"
}

# Dialog manager -> Language generator
if ($dmBox -and $lgBox) {
    $c6 = Invoke-MiroAPI "connectors" @{
        startItem = @{ id = $dmBox.id }
        endItem = @{ id = $lgBox.id }
        style = $connectorStyle
        shape = "straight"
    }
    Write-Host "Connector: DM -> LG (id=$($c6.id))"
}

# Language generator -> Text-to-speech
if ($lgBox -and $ttsBox) {
    $c7 = Invoke-MiroAPI "connectors" @{
        startItem = @{ id = $lgBox.id }
        endItem = @{ id = $ttsBox.id }
        style = $connectorStyle
        shape = "straight"
    }
    Write-Host "Connector: LG -> TTS (id=$($c7.id))"
}

# Text-to-speech -> Speech response
if ($ttsBox -and $speechResponseLabel) {
    $c8 = Invoke-MiroAPI "connectors" @{
        startItem = @{ id = $ttsBox.id }
        endItem = @{ id = $speechResponseLabel.id }
        style = $connectorStyle
        shape = "straight"
    }
    Write-Host "Connector: TTS -> Speech response (id=$($c8.id))"
}

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "Diagram created on board: $boardId"
Write-Host "View link: https://miro.com/app/board/$boardId/"
