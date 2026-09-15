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
    for ($try = 1; $try -le 6; $try++) {
        try {
            $p = @{ Uri = $Uri; Headers = $headers; Method = $Method; ContentType = "application/json"; UseBasicParsing = $true }
            if ($Body) { $p.Body = [System.Text.Encoding]::UTF8.GetBytes($Body) }
            $resp = Invoke-WebRequest @p
            $script:apiCalls++
            $rem = $resp.Headers["X-RateLimit-Remaining"]
            if ($rem -is [array]) { $rem = $rem[0] }
            if ($rem -and [int]$rem -lt 3) { Start-Sleep -Seconds 12 } else { Start-Sleep -Milliseconds 350 }
            if ($resp.Content) { return ($resp.Content | ConvertFrom-Json) }
            return $null
        } catch {
            $code = 0
            if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
            if ($code -eq 204) { return $null }
            $errBody = ""
            try {
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream) { $errBody = (New-Object System.IO.StreamReader($stream)).ReadToEnd() }
            } catch {}
            if ($code -eq 429) {
                Write-Host "    [429 waiting 60s]" -ForegroundColor Yellow
                Start-Sleep -Seconds 60
            } else {
                Write-Host "    [HTTP $code] $errBody $($_.Exception.Message)" -ForegroundColor Red
                if ($try -eq 6) { throw }
                Start-Sleep -Seconds 4
            }
        }
    }
}
function J([hashtable]$Object) { return ($Object | ConvertTo-Json -Depth 8) }

function Get-Item([string]$Id) {
    return Invoke-Miro -Method Get -Uri "$baseUri/boards/$boardId/items/$Id"
}

function Patch-Shape {
    param($Id, $Content, $X, $Y, $W, $H, $FontSize)
    $cur = Get-Item $Id
    $style = @{
        fillColor         = $cur.style.fillColor
        color             = $cur.style.color
        borderColor       = $cur.style.borderColor
        fontSize          = "$FontSize"
        textAlign         = $cur.style.textAlign
        textAlignVertical = $cur.style.textAlignVertical
        borderWidth       = "2"
        borderStyle       = $(if ($cur.style.borderStyle) { $cur.style.borderStyle } else { "normal" })
    }
    $body = @{
        data     = @{ content = $Content }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W; height = $H }
        style    = $style
    }
    Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/shapes/$Id" -Body (J $body) | Out-Null
}

function Patch-Sticky {
    param($Id, $Content, $X, $Y, $W)
    $body = @{
        data     = @{ content = $Content }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W }
    }
    Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/sticky_notes/$Id" -Body (J $body) | Out-Null
}

function Patch-Text {
    param($Id, $Content, $X, $Y, $W, $FontSize, $Align = "center")
    $cur = Get-Item $Id
    $body = @{
        data     = @{ content = $Content }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W }
        style    = @{
            fontSize  = "$FontSize"
            textAlign = $Align
            color     = $(if ($cur.style.color) { $cur.style.color } else { "#6C3483" })
        }
    }
    Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/texts/$Id" -Body (J $body) | Out-Null
}

function Patch-ConnectorCap {
    param($Id, $Content)
    Invoke-Miro -Method Patch -Uri "$baseUri/boards/$boardId/connectors/$Id" -Body (J @{
        captions = @(@{ content = $Content; position = "50%" })
        style    = @{ fontSize = "14"; textOrientation = "aligned" }
    }) | Out-Null
}

# ---- IDs ----
$hdr6 = "3458764683082620994"
$user = "3458764683533112723"
$envn = "3458764683533112737"
$prof = "3458764683082620998"
$plan = "3458764683082621002"
$repo = "3458764683082621013"
$ui   = "3458764683082621023"
$phiT = "3458764683533112756"
$stDU = "3458764683533112762"
$stDE = "3458764683533112772"
$stPhi = "3458764683533112782"
$stRepo = "3458764683533112795"
$stUi = "3458764683533112800"
$stFutD = "3458764683533112805"
$stFutP = "3458764683533112809"
$stFutR = "3458764683533112811"
$stFutU = "3458764683533112814"
$stPink6 = "3458764683533112815"

$hdr7 = "3458764683082621181"
$start = "3458764683533112818"
$intake = "3458764683533112824"
$screen = "3458764683533112835"
$escalate = "3458764683533112845"
$disp = "3458764683533112853"
$educate = "3458764683533112862"
$resources = "3458764683533112872"
$feedback = "3458764683533112886"
$qa = "3458764683533112895"
$loopIn = "3458764683533177110"
$loopSc = "3458764683533177118"
$stPink7 = "3458764683533177250"

Write-Host "=== Section 6: align, enlarge, symbol formulas ===" -ForegroundColor Cyan

# Frame 6 inner: x 0-3300, y 2997-4747. Grid columns at 430, 1240, 2060, 2880
$c1 = 430; $c2 = 1240; $c3 = 2060; $c4 = 2880

Patch-Shape $hdr6 "<b>6. BIT-Tech</b>   Mohr hybrid sense-plan-act. Planner: &#934;(A, D, W) = I = &#9001;E, C&#9002;" 1650 3075 3220 80 22
Patch-Shape $user "<b>User</b>" $c1 3195 320 88 22
Patch-Shape $envn "<b>Environment</b>" $c4 3195 320 88 22
Patch-Shape $prof "<b>Profiler</b><br/>Senses D(U) + D(E)<br/>Sensing: encoder / ChatState" $c1 3375 700 200 20
Patch-Shape $plan "<b>Intervention Planner</b><br/>&#934;(A, D, W) = I<sub>t</sub><br/>Planning: orchestrator" $c2 3375 700 200 20
Patch-Shape $repo "<b>Intervention Repository</b><br/>Stores E + C variants<br/>Graph, RAG, prompts" $c3 3375 700 200 20
Patch-Shape $ui "<b>User interface</b><br/>Delivers I = E + C<br/>Acting: study chat" $c4 3375 700 200 20

Patch-Text $phiT "<b>&#934;(A<sub>1..t</sub>, D<sub>1..t</sub>, W<sub>t</sub>) = I<sub>t</sub> = &#9001;E<sub>t</sub>, C<sub>t</sub>&#9002;</b><br/>Hybrid: reactive sense-act for RISK_CATALOG; deliberative sense-plan-act for intake + disposition; policy gate can still override after generation." 1650 3545 3000 18

# Larger stickies, column-aligned (keep yellow / blue / pink fills)
Patch-Sticky $stDU "D(U) current: utterance, clinical_checklist (age, sex, comorbidities, symptom slots), factor_states, coverage, questions_asked, risk_hits, session id, thumbs feedback." $c1 3780 420
Patch-Sticky $stDE "D(E) current: none. v1 has no environment sensors." $c1 4085 420
Patch-Sticky $stPhi "&#934; current: one session, one question/turn, max 20. RISK_CATALOG after encode -> canned escalation. Deliberative: enrich -> coverage -> ranker -> question or disposition. Tunnel CES/AAA/DVT first. Policy gate after generation." $c2 3780 420
Patch-Sticky $stFutP "Future planner: return-visit / 48h follow-up; post-disposition open Q&amp;A; case-based reasoning; nearby-clinic routing." $c2 4085 420
Patch-Sticky $stRepo "Repository current: red-flags graph/CSV v4, Chroma chunks, factor question specs / ontology, clinical-reasoning prompt, generator + disposition brief, canned escalation and insufficient-info copy." $c3 3780 420
Patch-Sticky $stFutR "Future repository: video/audio assets, body-map / diagram variants, clinic-directory, Pain BC / Arthritis resources." $c3 4085 420
Patch-Sticky $stUi "UI current: study chat website. Arms 1/2/3 only change how disposition is shown. Feedback buttons." $c4 3780 420
Patch-Sticky $stFutU "Future UI: body map, diagrams, audio/video, clinician / human-in-the-loop view." $c4 4085 420
Patch-Sticky $stFutD "D(E)/D(U) future: location for clinics near you; sensors / computer vision; persistent symptom-trajectory and activity memory." $c1 4390 420
Patch-Sticky $stPink6 "Keep Mohr's four components. TRI-BACK Encoder / Orchestrator / Generator implement sensing, &#934;, and acting. Do not rename Profiler to Encoder." 2060 4390 420

Write-Host "=== Connector captions (symbols) ===" -ForegroundColor Cyan
Patch-ConnectorCap "3458764683082621056" "I<sub>t</sub> spec"
Patch-ConnectorCap "3458764683082621062" "E + C"
Patch-ConnectorCap "3458764683533112739" "D(U)"
Patch-ConnectorCap "3458764683533112742" "D(E)"

Write-Host "=== Section 7: grid, larger E+C boxes ===" -ForegroundColor Cyan
# Frame 7 canvas top ~4867. Header stays on canvas just inside top.
Patch-Shape $hdr7 "<b>7. Session workflow</b>   Mohr: states = intervention steps &#9001;E, C&#9002;; edges = &#934; transitions. LangGraph nodes implement &#934;; they are not FSM states." 1650 4920 3220 80 20

# Parent-relative grid inside 3300 x 2100. Two columns, six rows.
$Lx = 780; $Rx = 2360; $boxW = 980; $boxH = 250; $fs = 16
Patch-Shape $start "<b>Element: open chat</b><br/>Characteristic: secure access; text dialogue (LLM)" $Lx 200 $boxW $boxH $fs
Patch-Shape $escalate "<b>Element: ED / urgent messaging</b><br/>Characteristic: interrupt path; no self-care or diagnostic language" $Rx 200 $boxW $boxH $fs
Patch-Shape $intake "<b>Element: conversational intake</b><br/>Characteristic: text dialogue (LLM); socially constrained; health-literacy targeted; no diagnostic language" $Lx 520 $boxW $boxH $fs
Patch-Shape $disp "<b>Element: grounded triage disposition</b><br/>Characteristic: text dialogue (LLM); socially constrained; retrieval / graph tailored to this presentation" $Rx 520 $boxW $boxH $fs
Patch-Shape $screen "<b>Element: red-flag factor questions</b><br/>Characteristic: text dialogue (LLM); socially constrained; health-literacy targeted; no diagnostic language" $Lx 840 $boxW $boxH $fs
Patch-Shape $educate "<b>Element: NSLBP self-care information</b><br/>Characteristic: text dialogue (LLM); socially constrained; health-literacy targeted" $Rx 840 $boxW $boxH $fs
Patch-Shape $resources "<b>Element: find clinics / resources</b><br/>Characteristic: text dialogue; location-tailored directory content" $Rx 1160 $boxW $boxH $fs
Patch-Shape $feedback "<b>Element: thumbs feedback</b><br/>Characteristic: user-defined; simple UI control" $Lx 1480 $boxW $boxH $fs
Patch-Shape $qa "<b>Element: user-defined Q and A</b><br/>Characteristic: user-defined sequence; text dialogue (LLM)" $Rx 1480 $boxW $boxH $fs
Patch-Shape $loopIn "<b>self-loop</b>" 160 520 140 140 16
Patch-Shape $loopSc "<b>self-loop</b>" 160 840 140 140 16
Patch-Sticky $stPink7 "LangGraph nodes in graph.py implement &#934;. They are not FSM states." $Lx 1820 420

Write-Host "=== Symbol legends to the right of frames 6 and 7 ===" -ForegroundColor Cyan
$navy = "#1B2A4A"; $white = "#FFFFFF"; $card = "#F0F4F8"

function New-Legend($Title, $X, $Y, $H) {
    $fr = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/frames" -Body (J @{
        data     = @{ title = $Title; format = "custom" }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = 620; height = $H }
    })
    $hdr = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (J @{
        data     = @{ content = "<b>Symbol legend</b>"; shape = "round_rectangle" }
        style    = @{
            fillColor = $navy; color = $white; borderColor = $navy
            fontSize = "20"; textAlign = "left"; textAlignVertical = "middle"; borderWidth = "2"
        }
        position = @{ x = 310; y = 45 }
        geometry = @{ width = 580; height = 70 }
        parent   = @{ id = $fr.id }
    })
    $body = @"
<b>&#934;</b> &nbsp; intervention-planner function<br/>
<b>A</b> &nbsp; aim(s)<br/>
<b>D</b> &nbsp; data<br/>
<b>D(U)</b> &nbsp; user data<br/>
<b>D(E)</b> &nbsp; environment data<br/>
<b>W</b> &nbsp; workflow<br/>
<b>I</b> &nbsp; intervention step<br/>
<b>I<sub>t</sub></b> &nbsp; intervention at time t<br/>
<b>E</b> &nbsp; BIT element (what the user interacts with)<br/>
<b>C</b> &nbsp; characteristic (medium, complexity, personalization, aesthetics)<br/>
<b>&#9001;E, C&#9002;</b> &nbsp; I = element + characteristics<br/>
<b>t</b> &nbsp; time step
"@
    Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (J @{
        data     = @{ content = $body; shape = "round_rectangle" }
        style    = @{
            fillColor = $card; color = $navy; borderColor = $navy
            fontSize = "16"; textAlign = "left"; textAlignVertical = "top"; borderWidth = "2"
        }
        position = @{ x = 310; y = ($H / 2 + 20) }
        geometry = @{ width = 580; height = ($H - 130) }
        parent   = @{ id = $fr.id }
    }) | Out-Null
    return $fr
}

# Right of frame 6 (right edge x=3300) and frame 7
$null = New-Legend "Symbol legend (BIT-Tech)" 3680 3872 1750
$null = New-Legend "Symbol legend (session workflow)" 3680 5917 2100

Write-Host "DONE apiCalls=$($script:apiCalls)" -ForegroundColor Green
