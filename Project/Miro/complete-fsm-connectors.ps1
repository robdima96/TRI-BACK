$ErrorActionPreference = "Stop"
$boardId = "uXjVHpBbaIg="
$token = (Get-Content (Join-Path $PSScriptRoot ".env") | Where-Object { $_ -match "^MIRO_ACCESS_TOKEN=" }) -replace "^MIRO_ACCESS_TOKEN=", ""
$baseUri = "https://api.miro.com/v2"
$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}

$script:apiCalls = 0
function Invoke-Miro {
    param([string]$Method, [string]$Uri, [string]$Body = $null)
    for ($try = 1; $try -le 5; $try++) {
        try {
            $p = @{ Uri = $Uri; Headers = $headers; Method = $Method; ContentType = "application/json"; UseBasicParsing = $true }
            if ($Body) { $p.Body = [System.Text.Encoding]::UTF8.GetBytes($Body) }
            $resp = Invoke-WebRequest @p
            $script:apiCalls++
            Start-Sleep -Milliseconds 400
            if ($resp.Content) { return ($resp.Content | ConvertFrom-Json) }
            return $null
        } catch {
            $code = 0
            if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
            if ($code -eq 429) {
                Write-Host "    [429 waiting 60s]" -ForegroundColor Red
                Start-Sleep -Seconds 60
            } else {
                $errBody = ""
                try {
                    $stream = $_.Exception.Response.GetResponseStream()
                    $reader = New-Object System.IO.StreamReader($stream)
                    $errBody = $reader.ReadToEnd()
                } catch {}
                Write-Host "    [Error $($_.Exception.Message)] $errBody" -ForegroundColor Red
                if ($try -eq 5) { throw }
                Start-Sleep -Seconds 5
            }
        }
    }
}
function ConvertTo-MiroJson([hashtable]$Object) { return ($Object | ConvertTo-Json -Depth 8) }

$frame7 = "3458764683082621161"
$navy = "#1B2A4A"; $blue = "#2D5F8A"; $green = "#1E6F45"; $purple = "#6C3483"; $red = "#C0392B"

$start     = "3458764683533112818"
$intake    = "3458764683533112824"
$screen    = "3458764683533112835"
$escalate  = "3458764683533112845"
$disp      = "3458764683533112853"
$educate   = "3458764683533112862"
$resources = "3458764683533112872"
$feedback  = "3458764683533112886"
$qa        = "3458764683533112895"

function New-Shape($Content, $X, $Y, $W, $H, $Fill, $Border, $Shape = "circle") {
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (ConvertTo-MiroJson @{
        data     = @{ content = $Content; shape = $Shape }
        style    = @{
            fillColor = $Fill; color = $navy; borderColor = $Border
            fontSize = "11"; textAlign = "center"; textAlignVertical = "middle"
            borderWidth = "2"; borderStyle = "normal"
        }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W; height = $H }
        parent   = @{ id = $frame7 }
    })
}

function New-Connector($StartId, $EndId, $Label, $Color, $StrokeStyle = "normal") {
    $body = @{
        startItem = @{ id = $StartId }
        endItem   = @{ id = $EndId }
        style     = @{
            strokeColor = $Color; strokeWidth = "2"; strokeStyle = $StrokeStyle
            startStrokeCap = "none"; endStrokeCap = "arrow"
        }
        shape = "elbowed"
    }
    if ($Label) { $body["captions"] = @(@{ content = $Label; position = "50%" }) }
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/connectors" -Body (ConvertTo-MiroJson $body)
}

Write-Host "Creating self-loop nodes (Miro forbids same-item connectors)..."
$loopIn = New-Shape "loop" 120 620 90 90 "#D4E6F1" $blue
$loopSc = New-Shape "loop" 120 980 90 90 "#D4E6F1" $blue

function Cap($Process, $F1, $F2 = "") {
    if ($F2) { return "$Process<br/>$F1<br/>$F2" }
    return "$Process<br/>$F1"
}

Write-Host "Creating remaining FSM connectors..."
# Self-loops via helper nodes
$null = New-Connector $intake $loopIn.id (Cap "self-loop: missing slots" "question_planner.py" "graph.py") $blue
$null = New-Connector $loopIn.id $intake $null $blue
$null = New-Connector $screen $loopSc.id (Cap "self-loop: unknown factor" "factor_answers.py" "question_planner.py") $blue
$null = New-Connector $loopSc.id $screen $null $blue

$null = New-Connector $intake $escalate (Cap "event: RISK_CATALOG" "policy.py" "graph.py") $red
$null = New-Connector $intake $screen (Cap "tunnel: graph neighbourhood" "relevance_ranker.py" "question_planner.py") $purple
$null = New-Connector $screen $escalate (Cap "event: hard risk" "policy.py" "graph.py") $red
$null = New-Connector $screen $disp (Cap "task: coverage or max questions" "question_planner.py" "graph.py") $green
$null = New-Connector $intake $disp (Cap "task: coverage complete" "coverage.py" "question_planner.py") $green
$null = New-Connector $disp $escalate (Cap "policy override" "policy.py" "nodes.py") $red
$null = New-Connector $disp $educate (Cap "self-care cluster" "disposition_brief.py" "generator.py") $green
$null = New-Connector $disp $resources (Cap "future: nearby care" "not implemented") $blue "dashed"
$null = New-Connector $educate $feedback $null $navy
$null = New-Connector $resources $feedback $null $blue "dashed"
$null = New-Connector $escalate $feedback $null $red
$null = New-Connector $feedback $qa (Cap "future: user-defined" "not implemented") $purple "dashed"

Write-Host "Pink Phi note..."
$null = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/sticky_notes" -Body (ConvertTo-MiroJson @{
    data     = @{ content = "Pink note: LangGraph nodes in graph.py implement Phi. They are not FSM states."; shape = "square" }
    style    = @{ fillColor = "light_pink" }
    position = @{ x = 2800; y = 1960 }
    parent   = @{ id = $frame7 }
})

Write-Host "FSM connectors complete. API calls: $($script:apiCalls)" -ForegroundColor Green
