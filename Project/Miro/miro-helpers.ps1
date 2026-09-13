function Load-MiroEnv {
    $envPath = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path $envPath)) {
        Write-Error "No .env file found at $envPath"
        return $false
    }
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), "Process")
        }
    }
    return $true
}

function Get-MiroHeaders {
    return @{
        "Authorization" = "Bearer $($env:MIRO_ACCESS_TOKEN)"
        "Content-Type"  = "application/json"
    }
}

function Test-MiroConnection {
    Load-MiroEnv | Out-Null
    $headers = Get-MiroHeaders
    try {
        $response = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards" -Headers $headers -Method Get
        Write-Host "Connected to Miro successfully!" -ForegroundColor Green
        Write-Host "You have access to $($response.data.Count) board(s)."
        return $true
    } catch {
        Write-Error "Failed to connect: $($_.Exception.Message)"
        return $false
    }
}

function New-MiroBoard {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string]$Description = ""
    )
    Load-MiroEnv | Out-Null
    $headers = Get-MiroHeaders
    $body = @{
        name        = $Name
        description = $Description
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards" -Headers $headers -Method Post -Body $body
    Write-Host "Board created: $($response.viewLink)" -ForegroundColor Green
    return $response
}

function New-MiroShape {
    param(
        [Parameter(Mandatory)][string]$BoardId,
        [Parameter(Mandatory)][string]$Content,
        [string]$Shape = "rectangle",
        [double]$X = 0,
        [double]$Y = 0,
        [double]$Width = 200,
        [double]$Height = 100,
        [string]$FillColor = "#ffffff",
        [string]$BorderColor = "#1a1a1a",
        [string]$FontSize = "14",
        [string]$TextAlign = "center"
    )
    Load-MiroEnv | Out-Null
    $headers = Get-MiroHeaders
    $body = @{
        data     = @{
            content = $Content
            shape   = $Shape
        }
        style    = @{
            fillColor   = $FillColor
            borderColor = $BorderColor
            fontSize    = $FontSize
            textAlign   = $TextAlign
        }
        position = @{
            x = $X
            y = $Y
        }
        geometry = @{
            width  = $Width
            height = $Height
        }
    } | ConvertTo-Json -Depth 5

    $response = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards/$BoardId/shapes" -Headers $headers -Method Post -Body $body
    return $response
}

function New-MiroConnector {
    param(
        [Parameter(Mandatory)][string]$BoardId,
        [Parameter(Mandatory)][string]$StartItemId,
        [Parameter(Mandatory)][string]$EndItemId,
        [string]$Label = "",
        [string]$StrokeColor = "#1a1a1a",
        [string]$StrokeWidth = "2",
        [string]$Shape = "curved"
    )
    Load-MiroEnv | Out-Null
    $headers = Get-MiroHeaders
    $body = @{
        startItem = @{ id = $StartItemId }
        endItem   = @{ id = $EndItemId }
        style     = @{
            strokeColor = $StrokeColor
            strokeWidth = $StrokeWidth
        }
        shape     = $Shape
    }
    if ($Label -ne "") {
        $body["captions"] = @(@{ content = $Label; position = "50%" })
    }
    $jsonBody = $body | ConvertTo-Json -Depth 5

    $response = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards/$BoardId/connectors" -Headers $headers -Method Post -Body $jsonBody
    return $response
}

function New-MiroStickyNote {
    param(
        [Parameter(Mandatory)][string]$BoardId,
        [Parameter(Mandatory)][string]$Content,
        [double]$X = 0,
        [double]$Y = 0,
        [string]$FillColor = "light_yellow"
    )
    Load-MiroEnv | Out-Null
    $headers = Get-MiroHeaders
    $body = @{
        data     = @{ content = $Content; shape = "square" }
        style    = @{ fillColor = $FillColor }
        position = @{ x = $X; y = $Y }
    } | ConvertTo-Json -Depth 5

    $response = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards/$BoardId/sticky_notes" -Headers $headers -Method Post -Body $body
    return $response
}

function New-MiroText {
    param(
        [Parameter(Mandatory)][string]$BoardId,
        [Parameter(Mandatory)][string]$Content,
        [double]$X = 0,
        [double]$Y = 0,
        [double]$Width = 300,
        [string]$FontSize = "14"
    )
    Load-MiroEnv | Out-Null
    $headers = Get-MiroHeaders
    $body = @{
        data     = @{ content = $Content }
        style    = @{ fontSize = $FontSize }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $Width }
    } | ConvertTo-Json -Depth 5

    $response = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards/$BoardId/texts" -Headers $headers -Method Post -Body $body
    return $response
}

function New-MiroFrame {
    param(
        [Parameter(Mandatory)][string]$BoardId,
        [Parameter(Mandatory)][string]$Title,
        [double]$X = 0,
        [double]$Y = 0,
        [double]$Width = 800,
        [double]$Height = 600
    )
    Load-MiroEnv | Out-Null
    $headers = Get-MiroHeaders
    $body = @{
        data     = @{ title = $Title; format = "custom" }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $Width; height = $Height }
    } | ConvertTo-Json -Depth 5

    $response = Invoke-RestMethod -Uri "https://api.miro.com/v2/boards/$BoardId/frames" -Headers $headers -Method Post -Body $body
    return $response
}

Write-Host "Miro helpers loaded. Available commands:" -ForegroundColor Cyan
Write-Host "  Test-MiroConnection    - Verify your API token works"
Write-Host "  New-MiroBoard          - Create a new board"
Write-Host "  New-MiroShape          - Add a shape (rectangle, circle, etc.)"
Write-Host "  New-MiroConnector      - Draw a line between two shapes"
Write-Host "  New-MiroStickyNote     - Add a sticky note"
Write-Host "  New-MiroText           - Add a text block"
Write-Host "  New-MiroFrame          - Add a frame to group items"
