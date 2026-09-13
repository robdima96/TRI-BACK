$ErrorActionPreference = "Stop"
$startTime = Get-Date

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
            $rem = $resp.Headers["X-RateLimit-Remaining"]
            if ($rem -is [array]) { $rem = $rem[0] }
            if ($rem -and [int]$rem -lt 3) {
                Write-Host "    [Rate limit low ($rem remaining), pausing 15s]" -ForegroundColor Yellow
                Start-Sleep -Seconds 15
            } else {
                Start-Sleep -Milliseconds 400
            }
            if ($resp.Content) { return ($resp.Content | ConvertFrom-Json) }
            return $null
        } catch {
            $code = 0
            if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
            if ($code -eq 204 -or $code -eq 200) { return $null }
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

function ConvertTo-MiroJson([hashtable]$Object) {
    return ($Object | ConvertTo-Json -Depth 8)
}

function Remove-MiroItem([string]$Id, [string]$Kind = "items") {
    Write-Host "    DELETE $Kind/$Id"
    Invoke-Miro -Method Delete -Uri "$baseUri/boards/$boardId/$Kind/$Id" | Out-Null
}

# Palette
$navy     = "#1B2A4A"
$blue     = "#2D5F8A"
$green    = "#1E6F45"
$purple   = "#6C3483"
$red      = "#C0392B"
$white    = "#FFFFFF"
$dark     = "#1B2A4A"
$card     = "#F0F4F8"
$whyFill  = "#D4E6F1"
$howFill  = "#D5F5E3"
$whenFill = "#E8DAEF"
$techFill = "#E8DAEF"
$safety   = "#FADBD8"
$futureFill = "#D6EAF8"
$draft    = "light_yellow"
$empty    = "light_blue"
$question = "light_pink"
$safetySt = "orange"

$frame6 = "3458764683082620988"
$frame7 = "3458764683082621161"
$hdr6   = "3458764683082620994"
$hdr7   = "3458764683082621181"
$boxProf = "3458764683082620998"
$boxPlan = "3458764683082621002"
$boxRepo = "3458764683082621013"
$boxUi   = "3458764683082621023"

Write-Host "=== 1. Delete section 6 drafts and section 7 placeholder FSM ===" -ForegroundColor Cyan

$deleteStickies = @(
    "3458764683082621069",
    "3458764683082621078",
    "3458764683082621090",
    "3458764683082621100",
    "3458764683082621109",
    "3458764683082621120",
    "3458764683082621143"
)
foreach ($id in $deleteStickies) { Remove-MiroItem $id }

$deleteConnectors = @(
    "3458764683082621528",
    "3458764683082621530",
    "3458764683082621536",
    "3458764683082621541",
    "3458764683082621805"
)
foreach ($id in $deleteConnectors) { Remove-MiroItem $id "connectors" }

$deleteFsm = @(
    "3458764683082621189",
    "3458764683082621193",
    "3458764683082621460",
    "3458764683082621470",
    "3458764683082621499",
    "3458764683082621515"
)
foreach ($id in $deleteFsm) { Remove-MiroItem $id }

Write-Host "=== 2. Resize frames 6 and 7; update titles ===" -ForegroundColor Cyan

# Frame 6: keep top at 2997, height 1750 -> center y = 2997+875 = 3872
Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/frames/$frame6" -Body (ConvertTo-MiroJson @{
    data     = @{ title = "6. BIT-Tech - Profiler, Intervention Planner, Repository, User interface" }
    position = @{ x = 1650; y = 3872 }
    geometry = @{ width = 3300; height = 1750 }
}) | Out-Null

# Frame 7: top = 2997+1750+120 = 4867, height 2100 -> center y = 4867+1050 = 5917
Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/frames/$frame7" -Body (ConvertTo-MiroJson @{
    data     = @{ title = "7. Session workflow (finite state machine)" }
    position = @{ x = 1650; y = 5917 }
    geometry = @{ width = 3300; height = 2100 }
}) | Out-Null

# Existing header 7 is unparented at canvas y=3995; move it to the new frame top
Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/shapes/$hdr7" -Body (ConvertTo-MiroJson @{
    data     = @{ content = "<b>7. Session workflow</b>   Mohr: states = intervention steps (E+C); edges = Phi transitions. LangGraph nodes implement Phi; they are not FSM states." }
    position = @{ x = 1650; y = 4910 }
    geometry = @{ width = 3260; height = 50 }
    style    = @{
        fillColor         = $navy
        color             = $white
        borderColor       = $navy
        fontSize          = "15"
        textAlign         = "left"
        textAlignVertical = "middle"
        borderWidth       = "2"
    }
}) | Out-Null

Write-Host "=== 3. Update BIT-Tech header and four Mohr boxes ===" -ForegroundColor Cyan

Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/shapes/$hdr6" -Body (ConvertTo-MiroJson @{
    data     = @{ content = "<b>6. BIT-Tech</b>   Mohr hybrid sense-plan-act. Planner: Phi(A, D, W) = I = &lt;element, characteristics&gt;" }
    position = @{ x = 1650; y = 3050 }
    geometry = @{ width = 3260; height = 50 }
    style    = @{
        fillColor         = $purple
        color             = $white
        borderColor       = $purple
        fontSize          = "15"
        textAlign         = "left"
        textAlignVertical = "middle"
        borderWidth       = "2"
    }
}) | Out-Null

# User + Environment above the four boxes; four boxes stay named Mohr components, moved down
function Patch-Shape {
    param($Id, $Content, $X, $Y, $W, $H, $Fill, $Border, $FontSize = "14")
    Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/shapes/$Id" -Body (ConvertTo-MiroJson @{
        data     = @{ content = $Content }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W; height = $H }
        style    = @{
            fillColor         = $Fill
            color             = $dark
            borderColor       = $Border
            fontSize          = $FontSize
            textAlign         = "center"
            textAlignVertical = "middle"
            borderWidth       = "2"
        }
    }) | Out-Null
}

Patch-Shape -Id $boxProf -Content "<b>Profiler</b><br/>Senses D(U) + D(E)<br/>Sensing: encoder / ChatState" -X 450 -Y 3380 -W 300 -H 110 -Fill $techFill -Border $purple
Patch-Shape -Id $boxPlan -Content "<b>Intervention Planner</b><br/>Phi(A, D, W) = I_t<br/>Planning: orchestrator" -X 1250 -Y 3380 -W 300 -H 110 -Fill $techFill -Border $purple
Patch-Shape -Id $boxRepo -Content "<b>Intervention Repository</b><br/>Stores E + C variants<br/>Graph, RAG, prompts" -X 2050 -Y 3380 -W 300 -H 110 -Fill $techFill -Border $purple
Patch-Shape -Id $boxUi   -Content "<b>User interface</b><br/>Delivers I = E + C<br/>Acting: study chat" -X 2850 -Y 3380 -W 300 -H 110 -Fill $techFill -Border $purple

function New-Shape {
    param(
        [string]$Content, [double]$X, [double]$Y, [double]$W, [double]$H,
        [string]$Fill = "#F0F4F8", [string]$Border = "#2D5F8A", [string]$TextColor = "#1B2A4A",
        [string]$Shape = "round_rectangle", [string]$FontSize = "14",
        [string]$Align = "center", [string]$VAlign = "middle",
        [string]$BorderStyle = "normal", [string]$ParentId = $null
    )
    $obj = @{
        data     = @{ content = $Content; shape = $Shape }
        style    = @{
            fillColor         = $Fill
            color             = $TextColor
            borderColor       = $Border
            fontSize          = $FontSize
            textAlign         = $Align
            textAlignVertical = $VAlign
            borderWidth       = "2"
            borderStyle       = $BorderStyle
        }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W; height = $H }
    }
    if ($ParentId) { $obj["parent"] = @{ id = $ParentId } }
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (ConvertTo-MiroJson $obj)
}

function New-Sticky {
    param([string]$Content, [double]$X, [double]$Y, [string]$FillColor = "light_yellow", [string]$ParentId = $null)
    $obj = @{
        data     = @{ content = $Content; shape = "square" }
        style    = @{ fillColor = $FillColor }
        position = @{ x = $X; y = $Y }
    }
    if ($ParentId) { $obj["parent"] = @{ id = $ParentId } }
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/sticky_notes" -Body (ConvertTo-MiroJson $obj)
}

function New-Text {
    param([string]$Content, [double]$X, [double]$Y, [double]$W = 400, [string]$FontSize = "14", [string]$Align = "left", [string]$Color = "#1a1a1a")
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/texts" -Body (ConvertTo-MiroJson @{
        data     = @{ content = $Content }
        style    = @{ fontSize = $FontSize; textAlign = $Align; color = $Color }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W }
    })
}

function New-Connector {
    param(
        [string]$StartId, [string]$EndId, [string]$Label = "", [string]$Color = "#1B2A4A",
        [string]$StrokeStyle = "normal"
    )
    $body = @{
        startItem = @{ id = $StartId }
        endItem   = @{ id = $EndId }
        style     = @{
            strokeColor    = $Color
            strokeWidth    = "2"
            strokeStyle    = $StrokeStyle
            startStrokeCap = "none"
            endStrokeCap   = "arrow"
        }
        shape     = "elbowed"
    }
    if ($Label -ne "") {
        $body["captions"] = @(@{ content = $Label; position = "50%" })
    }
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/connectors" -Body (ConvertTo-MiroJson $body)
}

Write-Host "=== 4. User / Environment + Phi extras ===" -ForegroundColor Cyan

$user = New-Shape -Content "<b>User</b>" -X 700 -Y 3180 -W 220 -H 70 -Fill $whyFill -Border $blue
$envn = New-Shape -Content "<b>Environment</b>" -X 2600 -Y 3180 -W 220 -H 70 -Fill $whyFill -Border $blue
$null = New-Connector -StartId $user.id -EndId $boxProf -Label "D(U)" -Color $purple
$null = New-Connector -StartId $envn.id -EndId $boxProf -Label "D(E)" -Color $purple
$null = New-Connector -StartId $boxProf -EndId $boxUi -Label "reactive RISK_CATALOG" -Color $red -StrokeStyle "dashed"

$null = New-Text -Content "<b>Phi(A_1..t, D_1..t, W_t) = I_t = &lt;E_t, C_t&gt;</b><br/>Hybrid: reactive sense-act for RISK_CATALOG; deliberative sense-plan-act for intake + disposition; policy gate can still override after generation." -X 1650 -Y 3520 -W 2000 -FontSize "13" -Align "center" -Color $purple

Write-Host "=== 5. BIT-Tech current (yellow) and future (blue) stickies ===" -ForegroundColor Cyan

$null = New-Sticky -Content "D(U) current: utterance, clinical_checklist (age, sex, comorbidities, symptom slots), factor_states, coverage, questions_asked, risk_hits, session id, thumbs feedback." -X 450 -Y 3680 -FillColor $draft
$null = New-Sticky -Content "D(E) current: none. v1 has no environment sensors." -X 700 -Y 3680 -FillColor $draft
$null = New-Sticky -Content "Phi current: one session, one question/turn, max 20. RISK_CATALOG after encode -> canned escalation. Deliberative: enrich -> coverage -> ranker -> question or disposition. Tunnel CES/AAA/DVT first. Policy gate after generation." -X 1250 -Y 3680 -FillColor $draft
$null = New-Sticky -Content "Repository current: red-flags graph/CSV v4, Chroma chunks, factor question specs / ontology, clinical-reasoning prompt, generator + disposition brief, canned escalation and insufficient-info copy." -X 2050 -Y 3680 -FillColor $draft
$null = New-Sticky -Content "UI current: study chat website. Arms 1/2/3 only change how disposition is shown. Feedback buttons." -X 2850 -Y 3680 -FillColor $draft

$null = New-Sticky -Content "D(E)/D(U) future: location for clinics near you; sensors / computer vision; persistent symptom-trajectory and activity memory." -X 575 -Y 3920 -FillColor $empty
$null = New-Sticky -Content "Future planner: return-visit / 48h follow-up; post-disposition open Q&amp;A; case-based reasoning; nearby-clinic routing." -X 1250 -Y 3920 -FillColor $empty
$null = New-Sticky -Content "Future repository: video/audio assets, body-map / diagram variants, clinic-directory, Pain BC / Arthritis resources." -X 2050 -Y 3920 -FillColor $empty
$null = New-Sticky -Content "Future UI: body map, diagrams, audio/video, clinician / human-in-the-loop view." -X 2850 -Y 3920 -FillColor $empty

$null = New-Sticky -Content "Keep Mohr's four components. DigiMSK Encoder / Orchestrator / Generator implement sensing, Phi, and acting. Do not rename Profiler to Encoder." -X 1650 -Y 4160 -FillColor $question

Write-Host "=== 6. Draw Mohr E+C FSM in frame 7 ===" -ForegroundColor Cyan

# Positions relative to frame 7 top-left (3300 x 2100)
function New-EcBox {
    param([string]$Element, [string]$Characteristic, [double]$X, [double]$Y, [string]$Fill, [string]$Border, [string]$BorderStyle = "normal")
    $html = "<b>Element: $Element</b><br/>Characteristic: $Characteristic"
    return New-Shape -Content $html -X $X -Y $Y -W 440 -H 140 -Fill $Fill -Border $Border -FontSize "12" -ParentId $frame7 -BorderStyle $BorderStyle
}

$start = New-EcBox -Element "open chat" -Characteristic "secure access; text dialogue (LLM)" -X 500 -Y 280 -Fill $card -Border $navy
$intake = New-EcBox -Element "conversational intake" -Characteristic "text dialogue (LLM); socially constrained; health-literacy targeted; no diagnostic language" -X 500 -Y 620 -Fill $whyFill -Border $blue
$screen = New-EcBox -Element "red-flag factor questions" -Characteristic "text dialogue (LLM); socially constrained; health-literacy targeted; no diagnostic language" -X 500 -Y 980 -Fill $whyFill -Border $blue
$escalate = New-EcBox -Element "ED / urgent messaging" -Characteristic "interrupt path; no self-care or diagnostic language" -X 1650 -Y 280 -Fill $safety -Border $red
$disp = New-EcBox -Element "grounded triage disposition" -Characteristic "text dialogue (LLM); socially constrained; retrieval / graph tailored to this presentation" -X 1650 -Y 800 -Fill $howFill -Border $green
$educate = New-EcBox -Element "NSLBP self-care information" -Characteristic "text dialogue (LLM); socially constrained; health-literacy targeted" -X 900 -Y 1280 -Fill $howFill -Border $green
$resources = New-EcBox -Element "find clinics / resources" -Characteristic "text dialogue; location-tailored directory content" -X 2400 -Y 1280 -Fill $futureFill -Border $blue -BorderStyle "dashed"
$feedback = New-EcBox -Element "thumbs feedback" -Characteristic "user-defined; simple UI control" -X 1650 -Y 1620 -Fill $whyFill -Border $blue
$qa = New-EcBox -Element "user-defined Q and A" -Characteristic "user-defined sequence; text dialogue (LLM)" -X 1650 -Y 1960 -Fill $whenFill -Border $purple -BorderStyle "dashed"

function Cap([string]$Process, [string]$F1, [string]$F2 = "") {
    if ($F2) { return "$Process<br/>$F1<br/>$F2" }
    return "$Process<br/>$F1"
}

$null = New-Connector -StartId $start.id -EndId $intake.id -Label (Cap "open session" "graph.py" "main.py") -Color $navy
$null = New-Connector -StartId $intake.id -EndId $intake.id -Label (Cap "self-loop: missing slots" "question_planner.py" "graph.py") -Color $blue
$null = New-Connector -StartId $intake.id -EndId $escalate.id -Label (Cap "event: RISK_CATALOG" "policy.py" "graph.py") -Color $red
$null = New-Connector -StartId $intake.id -EndId $screen.id -Label (Cap "tunnel: graph neighbourhood" "relevance_ranker.py" "question_planner.py") -Color $purple
$null = New-Connector -StartId $screen.id -EndId $screen.id -Label (Cap "self-loop: unknown factor" "factor_answers.py" "question_planner.py") -Color $blue
$null = New-Connector -StartId $screen.id -EndId $escalate.id -Label (Cap "event: hard risk" "policy.py" "graph.py") -Color $red
$null = New-Connector -StartId $screen.id -EndId $disp.id -Label (Cap "task: coverage or max questions" "question_planner.py" "graph.py") -Color $green
$null = New-Connector -StartId $intake.id -EndId $disp.id -Label (Cap "task: coverage complete" "coverage.py" "question_planner.py") -Color $green
$null = New-Connector -StartId $disp.id -EndId $escalate.id -Label (Cap "policy override" "policy.py" "nodes.py") -Color $red
$null = New-Connector -StartId $disp.id -EndId $educate.id -Label (Cap "self-care cluster" "disposition_brief.py" "generator.py") -Color $green
$null = New-Connector -StartId $disp.id -EndId $resources.id -Label (Cap "future: nearby care" "not implemented") -Color $blue -StrokeStyle "dashed"
$null = New-Connector -StartId $educate.id -EndId $feedback.id -Color $navy
$null = New-Connector -StartId $resources.id -EndId $feedback.id -Color $blue -StrokeStyle "dashed"
$null = New-Connector -StartId $escalate.id -EndId $feedback.id -Color $red
$null = New-Connector -StartId $feedback.id -EndId $qa.id -Label (Cap "future: user-defined" "not implemented") -Color $purple -StrokeStyle "dashed"

$null = New-Sticky -Content "Pink note: LangGraph nodes in graph.py implement Phi. They are not FSM states." -X 2800 -Y 1960 -FillColor $question -ParentId $frame7

$elapsed = (Get-Date) - $startTime
Write-Host "`nCOMPLETE - BIT-Tech + FSM" -ForegroundColor Green
Write-Host "API calls: $($script:apiCalls)"
Write-Host "Time: $([Math]::Round($elapsed.TotalMinutes, 1)) minutes"
Write-Host "Board: https://miro.com/app/board/$boardId/"
