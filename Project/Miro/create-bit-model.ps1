$ErrorActionPreference = "Stop"
$startTime = Get-Date

# ===== Configuration =====
# Target board: https://miro.com/app/board/uXjVHpBbaIg=/
$boardId = "uXjVHpBbaIg="
$token = (Get-Content (Join-Path $PSScriptRoot ".env") | Where-Object { $_ -match "^MIRO_ACCESS_TOKEN=" }) -replace "^MIRO_ACCESS_TOKEN=", ""
$baseUri = "https://api.miro.com/v2"
$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}

# ===== API helper with rate-limit handling =====
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

function ConvertTo-MiroJson([hashtable]$Object) {
    return ($Object | ConvertTo-Json -Depth 8)
}

function New-Frame {
    param([string]$Title, [double]$X, [double]$Y, [double]$W, [double]$H)
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/frames" -Body (ConvertTo-MiroJson @{
        data     = @{ title = $Title; format = "custom" }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W; height = $H }
    })
}

function New-Shape {
    param(
        [string]$Content, [double]$X, [double]$Y, [double]$W, [double]$H,
        [string]$Fill = "#F0F4F8", [string]$Border = "#2D5F8A", [string]$TextColor = "#1B2A4A",
        [string]$Shape = "round_rectangle", [string]$FontSize = "14",
        [string]$Align = "center", [string]$VAlign = "middle",
        [string]$BorderStyle = "normal"
    )
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (ConvertTo-MiroJson @{
        data     = @{ content = $Content; shape = $Shape }
        style    = @{
            fillColor          = $Fill
            color              = $TextColor
            borderColor        = $Border
            fontSize           = $FontSize
            textAlign          = $Align
            textAlignVertical  = $VAlign
            borderWidth        = "2"
            borderStyle        = $BorderStyle
        }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W; height = $H }
    })
}

function New-Sticky {
    param([string]$Content, [double]$X, [double]$Y, [string]$FillColor = "light_yellow")
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/sticky_notes" -Body (ConvertTo-MiroJson @{
        data     = @{ content = $Content; shape = "square" }
        style    = @{ fillColor = $FillColor }
        position = @{ x = $X; y = $Y }
    })
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
    param([string]$StartId, [string]$EndId, [string]$Label = "", [string]$Color = "#1B2A4A")
    $body = @{
        startItem = @{ id = $StartId }
        endItem   = @{ id = $EndId }
        style     = @{ strokeColor = $Color; strokeWidth = "2"; startStrokeCap = "none"; endStrokeCap = "arrow" }
        shape     = "elbowed"
    }
    if ($Label -ne "") {
        $body["captions"] = @(@{ content = $Label; position = "50%" })
    }
    return Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/connectors" -Body (ConvertTo-MiroJson $body)
}

# ===== Palette =====
$navy     = "#1B2A4A"
$blue     = "#2D5F8A"
$teal     = "#17A589"
$green    = "#1E6F45"
$purple   = "#6C3483"
$orange   = "#E67E22"
$red      = "#C0392B"
$white    = "#FFFFFF"
$dark     = "#1B2A4A"
$card     = "#F0F4F8"
$whyFill  = "#D4E6F1"
$howFill  = "#D5F5E3"
$whatFill = "#D5F5E3"
$techFill = "#FDEBD0"
$whenFill = "#E8DAEF"
$draft    = "light_yellow"
$empty    = "light_blue"
$question = "light_pink"
$safety   = "orange"
$locked   = "light_green"

Write-Host "=== Building DigiMSKbot BIT model board ===" -ForegroundColor Cyan
Write-Host "Board: $boardId"
Write-Host "Empty starter layout after Mohr et al. 2014 (JMIR). Seed stickies are DRAFT." -ForegroundColor Gray

# Guard: do not wipe a non-empty board
$existing = Invoke-Miro -Method Get -Uri "$baseUri/boards/$boardId/items?limit=10"
if ($existing.data.Count -gt 0) {
    throw "Board already has $($existing.data.Count)+ items. Refusing to add a second layout. Clear the board first if you want a rebuild."
}

# Layout: theoretical pair 1600+100+1600 = 3300 wide; instantiation three columns match that width.
$gap = 100
$whyW = 1600; $whyH = 1150
$instW = 1033; $instH = 1050
$wideW = 3300
$cx = 1650   # horizontal centre of the whole composition

# ============================================================
# 0. Title, citation, legend
# ============================================================
Write-Host "`n--- Title and legend ---" -ForegroundColor Yellow

$null = New-Shape -Content "<b>DigiMSKbot BIT model</b>" -X $cx -Y -80 -W 1600 -H 90 -Fill $navy -Border $navy -TextColor $white -FontSize "32"
$null = New-Text -Content "A behavioural intervention technology (BIT) to reduce unnecessary ED visits for non-specific mechanical back pain.<br/>Starter board: yellow = DRAFT seed to rewrite; blue = empty slot; pink = open question; orange = safety-critical." -X $cx -Y 20 -W 1600 -FontSize "16" -Align "center" -Color "#444444"
$null = New-Text -Content "Framework: Mohr DC, Schueller SM, Montague E, Burns MN, Rashidi P. The Behavioral Intervention Technology Model. J Med Internet Res. 2014;16(6):e146. https://www.jmir.org/2014/6/e146/" -X $cx -Y 80 -W 1600 -FontSize "12" -Align "center" -Color "#666666"

# Legend frame (left of title, slightly down)
$legX = -200; $legY = 320; $legW = 520; $legH = 520
$null = New-Frame -Title "How to use this board" -X $legX -Y $legY -W $legW -H $legH
$null = New-Shape -Content "<b>How to use this board</b>" -X $legX -Y ($legY - $legH / 2 + 22) -W ($legW - 20) -H 40 -Fill $navy -Border $navy -TextColor $white -FontSize "16" -Align "left"
$null = New-Text -Content "Work left to right, matching Mohr Table 1:<br/>Why -> conceptual How -> What -> technical How -> When.<br/><br/>Then fill a full <b>trace</b> (one aim + one strategy + one element + characteristics + workflow). That is the unit Mohr calls an intervention." -X $legX -Y ($legY - 80) -W 460 -FontSize "13"
$null = New-Sticky -Content "YELLOW = DRAFT seed. Rewrite, split, or discard." -X ($legX - 120) -Y ($legY + 80) -FillColor $draft
$null = New-Sticky -Content "BLUE = empty slot. Drop a new idea here." -X ($legX + 90) -Y ($legY + 80) -FillColor $empty
$null = New-Sticky -Content "PINK = unresolved design question." -X ($legX - 120) -Y ($legY + 220) -FillColor $question
$null = New-Sticky -Content "ORANGE = safety / red-flag path. Do not bury these." -X ($legX + 90) -Y ($legY + 220) -FillColor $safety

# ============================================================
# 1. Theoretical level banner + WHY + conceptual HOW
# ============================================================
$theoryY = 1050
$whyX = 800
$howX = 2500

Write-Host "`n--- Theoretical level ---" -ForegroundColor Yellow
$null = New-Shape -Content "<b>THEORETICAL LEVEL</b>  -  developer intentions  -  Why the BIT exists, and conceptually how it will change behaviour" -X $cx -Y 560 -W $wideW -H 50 -Fill $blue -Border $blue -TextColor $white -FontSize "16" -Align "left"

# WHY frame
$null = New-Frame -Title "1. WHY - Intervention aims" -X $whyX -Y $theoryY -W $whyW -H $whyH
$null = New-Shape -Content "<b>1. WHY - Intervention aims</b>   (clinical aims + usage aims + sub-aim hierarchy)" -X $whyX -Y ($theoryY - $whyH / 2 + 22) -W ($whyW - 20) -H 44 -Fill $blue -Border $blue -TextColor $white -FontSize "16" -Align "left"
$null = New-Shape -Content "<b>Treatment goal (distal)</b><br/>Reduce unnecessary emergency-department visits for non-specific mechanical low back pain" -X $whyX -Y ($theoryY - 430) -W 1480 -H 80 -Fill $whyFill -Border $blue -FontSize "16"
$null = New-Text -Content "<b>Clinical sub-aims</b> (proximal - rewrite these; keep them specific enough to design against)" -X ($whyX - 350) -Y ($theoryY - 350) -W 700 -FontSize "13"
$null = New-Text -Content "<b>Usage aims</b> (engagement with the BIT - distinct from clinical outcomes)" -X ($whyX + 430) -Y ($theoryY - 350) -W 700 -FontSize "13"

# Clinical sub-aim seeds
$null = New-Sticky -Content "[DRAFT] Increase knowledge that most NS mechanical LBP is not an emergency" -X ($whyX - 560) -Y ($theoryY - 200) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Increase self-efficacy for home self-management (activity, pacing, analgesia as appropriate)" -X ($whyX - 340) -Y ($theoryY - 200) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Reduce fear-avoidance / catastrophizing that drives ED care-seeking" -X ($whyX - 560) -Y ($theoryY - 20) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Increase appropriate non-ED care-seeking (PCP, physio, pharmacist) when self-care is not enough" -X ($whyX - 340) -Y ($theoryY - 20) -FillColor $draft
$null = New-Sticky -Content "[Add clinical sub-aim]" -X ($whyX - 560) -Y ($theoryY + 170) -FillColor $empty
$null = New-Sticky -Content "[Add clinical sub-aim]" -X ($whyX - 340) -Y ($theoryY + 170) -FillColor $empty

# Usage aim seeds
$null = New-Sticky -Content "[DRAFT] Complete red-flag screening before self-management advice is given" -X ($whyX + 280) -Y ($theoryY - 200) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Stay in the conversation long enough to leave with reassurance + a plan" -X ($whyX + 500) -Y ($theoryY - 200) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Return / re-open if symptoms change (usage for monitoring over time)" -X ($whyX + 280) -Y ($theoryY - 20) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Perceive usefulness and ease of use without over-trusting the bot as a diagnosis" -X ($whyX + 500) -Y ($theoryY - 20) -FillColor $draft
$null = New-Sticky -Content "[Add usage aim]" -X ($whyX + 280) -Y ($theoryY + 170) -FillColor $empty
$null = New-Sticky -Content "[Add usage aim]" -X ($whyX + 500) -Y ($theoryY + 170) -FillColor $empty

# Safety + questions in WHY
$null = New-Sticky -Content "SAFETY AIM: Identify and escalate possible serious pathology / red flags. Is this a clinical aim, or a constraint that sits outside the ED-reduction goal?" -X ($whyX - 120) -Y ($theoryY + 360) -FillColor $safety
$null = New-Sticky -Content "Q: Is 'fewer ED visits' the treatment goal, or a system outcome we hope follows from knowledge / self-efficacy / care-seeking?" -X ($whyX + 100) -Y ($theoryY + 360) -FillColor $question
$null = New-Sticky -Content "Q: Who is the user at the moment of possible ED use - home at night, ED waiting room, after-hours, primary-care portal?" -X ($whyX + 320) -Y ($theoryY + 360) -FillColor $question
$null = New-Text -Content "Drop more aims in the blue slots. Keep a hierarchy: one distal goal, then specific proximal aims." -X $whyX -Y ($theoryY + 510) -W 1400 -FontSize "12" -Align "center" -Color "#666666"

# HOW conceptual frame
$null = New-Frame -Title "2. HOW (conceptual) - Behaviour change strategies" -X $howX -Y $theoryY -W $whyW -H $whyH
$null = New-Shape -Content "<b>2. HOW (conceptual) - Behaviour change strategies</b>   (Michie / Mohr examples - not exhaustive)" -X $howX -Y ($theoryY - $whyH / 2 + 22) -W ($whyW - 20) -H 44 -Fill $green -Border $green -TextColor $white -FontSize "16" -Align "left"
$null = New-Text -Content "Each strategy should name how a proximal aim is produced. Map later into a trace." -X $howX -Y ($theoryY - 470) -W 1480 -FontSize "13" -Align "center"

$null = New-Shape -Content "<b>Education</b>" -X ($howX - 600) -Y ($theoryY - 400) -W 220 -H 44 -Fill $howFill -Border $green -FontSize "14"
$null = New-Shape -Content "<b>Goal setting</b>" -X ($howX - 300) -Y ($theoryY - 400) -W 220 -H 44 -Fill $howFill -Border $green -FontSize "14"
$null = New-Shape -Content "<b>Monitoring</b>" -X $howX -Y ($theoryY - 400) -W 220 -H 44 -Fill $howFill -Border $green -FontSize "14"
$null = New-Shape -Content "<b>Feedback</b>" -X ($howX + 300) -Y ($theoryY - 400) -W 220 -H 44 -Fill $howFill -Border $green -FontSize "14"
$null = New-Shape -Content "<b>Motivation</b>" -X ($howX + 600) -Y ($theoryY - 400) -W 220 -H 44 -Fill $howFill -Border $green -FontSize "14"

$null = New-Sticky -Content "[DRAFT] Natural history of NSLBP; when ED is / is not indicated; first-line self-care" -X ($howX - 600) -Y ($theoryY - 230) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Activity pacing / return-to-function plan the person can state back" -X ($howX - 300) -Y ($theoryY - 230) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Red-flag check + optional symptom trajectory if they return" -X $howX -Y ($theoryY - 230) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] 'Based on what you described, this looks like mechanical LBP because...'" -X ($howX + 300) -Y ($theoryY - 230) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Reassurance; social norms; self-efficacy ('people with this often recover')" -X ($howX + 600) -Y ($theoryY - 230) -FillColor $draft

$null = New-Sticky -Content "[Add education tactic]" -X ($howX - 600) -Y ($theoryY - 40) -FillColor $empty
$null = New-Sticky -Content "[Add goal-setting tactic]" -X ($howX - 300) -Y ($theoryY - 40) -FillColor $empty
$null = New-Sticky -Content "[Add monitoring tactic]" -X $howX -Y ($theoryY - 40) -FillColor $empty
$null = New-Sticky -Content "[Add feedback tactic]" -X ($howX + 300) -Y ($theoryY - 40) -FillColor $empty
$null = New-Sticky -Content "[Add motivation tactic]" -X ($howX + 600) -Y ($theoryY - 40) -FillColor $empty

$null = New-Sticky -Content "[Add another strategy - e.g. problem solving, social support, identity/habit]" -X ($howX - 200) -Y ($theoryY + 180) -FillColor $empty
$null = New-Sticky -Content "Q: Which strategies are load-bearing for ED avoidance vs nice-to-have for a good consult?" -X ($howX + 80) -Y ($theoryY + 180) -FillColor $question
$null = New-Sticky -Content "Q: Fogg (tiny habits / triggers) vs education-heavy chatbot - where do we actually change the ED decision?" -X ($howX + 320) -Y ($theoryY + 180) -FillColor $question
$null = New-Text -Content "Prompt for each sticky: this strategy supports WHICH aim, for WHICH user state (past / current / desired future)?" -X $howX -Y ($theoryY + 360) -W 1480 -FontSize "12" -Align "center" -Color "#666666"
$null = New-Sticky -Content "Mohr Fig 1: BIT moves the user from current state -> future state. Name both states on each strategy." -X $howX -Y ($theoryY + 470) -FillColor $draft

# ============================================================
# 2. Instantiation level: WHAT / technical HOW / WHEN
# ============================================================
$instY = 2280
$whatX = 516.5
$techX = 1650
$whenX = 2783.5

Write-Host "`n--- Instantiation level ---" -ForegroundColor Yellow
$null = New-Shape -Content "<b>INSTANTIATION LEVEL</b>  -  what the user actually interacts with, how it is rendered, and when it is delivered" -X $cx -Y 1690 -W $wideW -H 50 -Fill $teal -Border $teal -TextColor $white -FontSize "16" -Align "left"

# WHAT
$null = New-Frame -Title "3. WHAT - BIT elements" -X $whatX -Y $instY -W $instW -H $instH
$null = New-Shape -Content "<b>3. WHAT - BIT elements</b>" -X $whatX -Y ($instY - $instH / 2 + 22) -W ($instW - 20) -H 44 -Fill $teal -Border $teal -TextColor $white -FontSize "16" -Align "left"
$null = New-Text -Content "Objects the user interacts with. One strategy can use several elements." -X $whatX -Y ($instY - 430) -W 960 -FontSize "13" -Align "center"

$null = New-Sticky -Content "[DRAFT] Information delivery: grounded chat turns (GraphRAG / guidelines)" -X ($whatX - 330) -Y ($instY - 280) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Logs: structured screening / checklist questions" -X ($whatX - 110) -Y ($instY - 280) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Reports: end-of-session summary + next steps" -X ($whatX + 110) -Y ($instY - 280) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Messaging / escalation: 'seek emergency care now' pathway" -X ($whatX + 330) -Y ($instY - 280) -FillColor $safety

$null = New-Sticky -Content "[PLACEHOLDER] Notifications (push / SMS / email) - not in current bot?" -X ($whatX - 220) -Y ($instY - 90) -FillColor $empty
$null = New-Sticky -Content "[PLACEHOLDER] Passive data (sensors, EHR, location) - out of scope?" -X ($whatX + 20) -Y ($instY - 90) -FillColor $empty
$null = New-Sticky -Content "[PLACEHOLDER] Peer / clinician messaging" -X ($whatX + 260) -Y ($instY - 90) -FillColor $empty

$null = New-Sticky -Content "[Add element]" -X ($whatX - 220) -Y ($instY + 100) -FillColor $empty
$null = New-Sticky -Content "[Add element]" -X ($whatX + 20) -Y ($instY + 100) -FillColor $empty
$null = New-Sticky -Content "Q: Is the whole chatbot one element (dialogue) or many nested elements (screen, teach, summarise)?" -X ($whatX + 260) -Y ($instY + 100) -FillColor $question
$null = New-Text -Content "Drop zone - additional elements" -X $whatX -Y ($instY + 280) -W 800 -FontSize "12" -Align "center" -Color "#666666"

# HOW technical
$null = New-Frame -Title "4. HOW (technical) - Characteristics" -X $techX -Y $instY -W $instW -H $instH
$null = New-Shape -Content "<b>4. HOW (technical) - Characteristics</b>" -X $techX -Y ($instY - $instH / 2 + 22) -W ($instW - 20) -H 44 -Fill $orange -Border $orange -TextColor $white -FontSize "16" -Align "left"
$null = New-Text -Content "Attributes of elements: medium, complexity, aesthetics, personalization (Mohr). Treat as design levers." -X $techX -Y ($instY - 430) -W 960 -FontSize "13" -Align "center"

$null = New-Sticky -Content "[DRAFT] Medium: text dialogue (LLM). Not video/audio - yet?" -X ($techX - 330) -Y ($instY - 280) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Complexity: protocol-constrained; health-literacy targeted; not diagnostic language" -X ($techX - 110) -Y ($instY - 280) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Personalization: retrieval / graph tailored to this presentation" -X ($techX + 110) -Y ($instY - 280) -FillColor $draft
$null = New-Sticky -Content "[PLACEHOLDER] Aesthetics / tone: DigiMSK voice - how human, how clinical?" -X ($techX + 330) -Y ($instY - 280) -FillColor $empty

$null = New-Sticky -Content "[Add medium variant]" -X ($techX - 220) -Y ($instY - 90) -FillColor $empty
$null = New-Sticky -Content "[Add complexity rule]" -X ($techX + 20) -Y ($instY - 90) -FillColor $empty
$null = New-Sticky -Content "[Add personalization rule]" -X ($techX + 260) -Y ($instY - 90) -FillColor $empty

$null = New-Sticky -Content "Q: Media richness - is plain text enough for reassurance, or do we need diagrams / body maps?" -X ($techX - 110) -Y ($instY + 100) -FillColor $question
$null = New-Sticky -Content "Q: How much should GraphRAG change content vs only citations?" -X ($techX + 130) -Y ($instY + 100) -FillColor $question
$null = New-Text -Content "Drop zone - characteristics as attributes of elements, not as new aims" -X $techX -Y ($instY + 280) -W 800 -FontSize "12" -Align "center" -Color "#666666"

# WHEN
$null = New-Frame -Title "5. WHEN - Workflow" -X $whenX -Y $instY -W $instW -H $instH
$null = New-Shape -Content "<b>5. WHEN - Workflow</b>" -X $whenX -Y ($instY - $instH / 2 + 22) -W ($instW - 20) -H 44 -Fill $purple -Border $purple -TextColor $white -FontSize "16" -Align "left"
$null = New-Text -Content "When an element is delivered: user-defined, frequency, time / task / event rules, tunneling." -X $whenX -Y ($instY - 430) -W 960 -FontSize "13" -Align "center"

$null = New-Sticky -Content "[DRAFT] Task-completion: screening finished -> unlock self-management education" -X ($whenX - 330) -Y ($instY - 280) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] Event-based: red flag detected -> interrupt and escalate (no self-care tunnel)" -X ($whenX - 110) -Y ($instY - 280) -FillColor $safety
$null = New-Sticky -Content "[DRAFT] Tunneling: mechanical NSLBP path vs concerning-features path" -X ($whenX + 110) -Y ($instY - 280) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] User-defined: free questions after the protocol gate" -X ($whenX + 330) -Y ($instY - 280) -FillColor $draft

$null = New-Sticky -Content "[PLACEHOLDER] Time-based: delayed follow-up ('if worse in 48h...')" -X ($whenX - 220) -Y ($instY - 90) -FillColor $empty
$null = New-Sticky -Content "[PLACEHOLDER] Frequency: one session vs expected return visits" -X ($whenX + 20) -Y ($instY - 90) -FillColor $empty
$null = New-Sticky -Content "[Add workflow rule]" -X ($whenX + 260) -Y ($instY - 90) -FillColor $empty

$null = New-Sticky -Content "Q: How much of the session is tunneled (orchestrator) vs user-defined (chat)?" -X ($whenX - 110) -Y ($instY + 100) -FillColor $question
$null = New-Sticky -Content "Q: Self-transitions - if they ignore escalation, do we repeat, escalate tone, or stop?" -X ($whenX + 130) -Y ($instY + 100) -FillColor $question
$null = New-Text -Content "Drop zone - conditions that fire an intervention step" -X $whenX -Y ($instY + 280) -W 800 -FontSize "12" -Align "center" -Color "#666666"

# ============================================================
# 3. Traceability - the unit of an intervention
# ============================================================
$traceY = 3480
$traceH = 980
Write-Host "`n--- Intervention traces ---" -ForegroundColor Yellow
$null = New-Frame -Title "6. Intervention traces - Aim to Strategy to Element to Characteristics to Workflow" -X $cx -Y $traceY -W $wideW -H $traceH
$null = New-Shape -Content "<b>6. Intervention traces</b>   Fill one complete chain per card. Mohr: an intervention is I = element + characteristics; treatment is those interventions over a workflow." -X $cx -Y ($traceY - $traceH / 2 + 22) -W ($wideW - 20) -H 44 -Fill $navy -Border $navy -TextColor $white -FontSize "15" -Align "left"

# Worked DRAFT example (MyFitnessPal analogue)
$exX = -200
$null = New-Shape -Content "<b>TRACE A - DRAFT worked example</b><br/>Rewrite until this is a claim you would defend" -X ($cx - 1100) -Y ($traceY - 360) -W 1000 -H 56 -Fill $whyFill -Border $blue -FontSize "14"
$null = New-Sticky -Content "AIM: Increase knowledge that this episode is likely mechanical NSLBP, not an emergency" -X ($cx - 1450) -Y ($traceY - 200) -FillColor $draft
$null = New-Sticky -Content "STRATEGY: Education + feedback" -X ($cx - 1230) -Y ($traceY - 200) -FillColor $draft
$null = New-Sticky -Content "ELEMENT: Information delivery (grounded chat) after a negative screen" -X ($cx - 1010) -Y ($traceY - 200) -FillColor $draft
$null = New-Sticky -Content "CHARACTERISTICS: Plain-language text; personalized to their descriptors; cites guideline" -X ($cx - 1340) -Y ($traceY - 20) -FillColor $draft
$null = New-Sticky -Content "WORKFLOW: Task-completion (screen done) AND event = no red flag. User-defined Q&amp;A after." -X ($cx - 1120) -Y ($traceY - 20) -FillColor $draft

$ex2X = 1100
$null = New-Shape -Content "<b>TRACE B - DRAFT safety example</b>" -X ($cx + 1100) -Y ($traceY - 360) -W 1000 -H 56 -Fill "#FADBD8" -Border $red -FontSize "14"
$null = New-Sticky -Content "AIM: User with possible cauda equina / serious pathology seeks emergency care now" -X ($cx + 750) -Y ($traceY - 200) -FillColor $safety
$null = New-Sticky -Content "STRATEGY: Monitoring (detect) + education (what to do)" -X ($cx + 970) -Y ($traceY - 200) -FillColor $safety
$null = New-Sticky -Content "ELEMENT: Screening log + escalation message" -X ($cx + 1190) -Y ($traceY - 200) -FillColor $safety
$null = New-Sticky -Content "CHARACTERISTICS: Low complexity; directive; no soft self-care language" -X ($cx + 860) -Y ($traceY - 20) -FillColor $safety
$null = New-Sticky -Content "WORKFLOW: Event-based interrupt. Tunnel away from self-management. Self-loop if unanswered?" -X ($cx + 1080) -Y ($traceY - 20) -FillColor $safety

# Empty traces
$null = New-Shape -Content "<b>TRACE C - empty</b><br/>Aim -> strategy -> element -> characteristics -> workflow" -X ($cx - 1100) -Y ($traceY + 220) -W 1000 -H 70 -Fill $white -Border "#94a3b8" -FontSize "14" -BorderStyle "dashed"
$null = New-Sticky -Content "[Drop AIM]" -X ($cx - 1450) -Y ($traceY + 370) -FillColor $empty
$null = New-Sticky -Content "[Drop STRATEGY]" -X ($cx - 1230) -Y ($traceY + 370) -FillColor $empty
$null = New-Sticky -Content "[Drop ELEMENT]" -X ($cx - 1010) -Y ($traceY + 370) -FillColor $empty
$null = New-Sticky -Content "[Drop CHARACTERISTICS]" -X ($cx - 1340) -Y ($traceY + 550) -FillColor $empty
$null = New-Sticky -Content "[Drop WORKFLOW]" -X ($cx - 1120) -Y ($traceY + 550) -FillColor $empty

$null = New-Shape -Content "<b>TRACE D - empty</b><br/>Suggested: self-efficacy / activity plan that substitutes for an ED visit" -X ($cx + 1100) -Y ($traceY + 220) -W 1000 -H 70 -Fill $white -Border "#94a3b8" -FontSize "14" -BorderStyle "dashed"
$null = New-Sticky -Content "[Drop AIM]" -X ($cx + 750) -Y ($traceY + 370) -FillColor $empty
$null = New-Sticky -Content "[Drop STRATEGY]" -X ($cx + 970) -Y ($traceY + 370) -FillColor $empty
$null = New-Sticky -Content "[Drop ELEMENT]" -X ($cx + 1190) -Y ($traceY + 370) -FillColor $empty
$null = New-Sticky -Content "[Drop CHARACTERISTICS]" -X ($cx + 860) -Y ($traceY + 550) -FillColor $empty
$null = New-Sticky -Content "[Drop WORKFLOW]" -X ($cx + 1080) -Y ($traceY + 550) -FillColor $empty

# ============================================================
# 4. BIT-Tech
# ============================================================
$techY = 4620
$techH = 780
Write-Host "`n--- BIT-Tech ---" -ForegroundColor Yellow
$null = New-Frame -Title "7. BIT-Tech - Profiler, Intervention Planner, Repository, User interface" -X $cx -Y $techY -W $wideW -H $techH
$null = New-Shape -Content "<b>7. BIT-Tech</b>   Mohr hybrid sense-plan-act. Planner function: Phi(aims, data, workflow) = intervention I = &lt;element, characteristics&gt;" -X $cx -Y ($techY - $techH / 2 + 22) -W ($wideW - 20) -H 44 -Fill $purple -Border $purple -TextColor $white -FontSize "15" -Align "left"

$p1 = New-Shape -Content "<b>Profiler</b><br/>Senses user + environment data D" -X ($cx - 1200) -Y ($techY - 220) -W 280 -H 90 -Fill "#E8DAEF" -Border $purple -FontSize "14"
$p2 = New-Shape -Content "<b>Intervention Planner</b><br/>Chooses I_t from A, D, W" -X ($cx - 400) -Y ($techY - 220) -W 280 -H 90 -Fill "#E8DAEF" -Border $purple -FontSize "14"
$p3 = New-Shape -Content "<b>Intervention Repository</b><br/>Stores elements + variants" -X ($cx + 400) -Y ($techY - 220) -W 280 -H 90 -Fill "#E8DAEF" -Border $purple -FontSize "14"
$p4 = New-Shape -Content "<b>User interface</b><br/>Delivers I = E + C" -X ($cx + 1200) -Y ($techY - 220) -W 280 -H 90 -Fill "#E8DAEF" -Border $purple -FontSize "14"

$null = New-Connector -StartId $p1.id -EndId $p2.id -Label "D" -Color $purple
$null = New-Connector -StartId $p2.id -EndId $p3.id -Label "I_t spec" -Color $purple
$null = New-Connector -StartId $p3.id -EndId $p4.id -Label "E + C" -Color $purple

$null = New-Sticky -Content "[DRAFT Profiler] Session state, utterance, checklist answers. Map to DigiMSK encoder / state." -X ($cx - 1200) -Y ($techY + 20) -FillColor $draft
$null = New-Sticky -Content "[DRAFT Planner] Orchestrator / LangGraph as Phi. Predefined now; adaptive later?" -X ($cx - 400) -Y ($techY + 20) -FillColor $draft
$null = New-Sticky -Content "[DRAFT Repository] Guidelines, graph, prompts, canned escalation copy" -X ($cx + 400) -Y ($techY + 20) -FillColor $draft
$null = New-Sticky -Content "[DRAFT UI] Chat surface. Future: body map, summary card, clinician view?" -X ($cx + 1200) -Y ($techY + 20) -FillColor $draft

$null = New-Sticky -Content "[Add D(U) user data we will actually have]" -X ($cx - 900) -Y ($techY + 210) -FillColor $empty
$null = New-Sticky -Content "[Add D(E) environment data - likely none at v1]" -X ($cx - 680) -Y ($techY + 210) -FillColor $empty
$null = New-Sticky -Content "Q: Keep BIT-Tech mapped 1:1 to current modules, or keep it conceptual so the model survives refactors?" -X ($cx - 200) -Y ($techY + 210) -FillColor $question
$null = New-Sticky -Content "[Add planner rule that is NOT already in the orchestrator]" -X ($cx + 200) -Y ($techY + 210) -FillColor $empty

# ============================================================
# 5. Session workflow FSM
# ============================================================
$fsmY = 5560
$fsmH = 720
Write-Host "`n--- Session workflow FSM ---" -ForegroundColor Yellow
$null = New-Frame -Title "8. Session workflow (finite state machine placeholder)" -X $cx -Y $fsmY -W $wideW -H $fsmH
$null = New-Shape -Content "<b>8. Session workflow</b>   Mohr: workflow as FSM - states = intervention steps; edges = Phi transitions. Rewrite nodes until they match the real protocol." -X $cx -Y ($fsmY - $fsmH / 2 + 22) -W ($wideW - 20) -H 44 -Fill $navy -Border $navy -TextColor $white -FontSize "15" -Align "left"

$s0 = New-Shape -Content "<b>Start</b><br/>Open chat" -X ($cx - 1400) -Y ($fsmY - 80) -W 180 -H 80 -Fill $card -Border $navy -FontSize "13"
$s1 = New-Shape -Content "<b>Screen</b><br/>Red-flag log" -X ($cx - 840) -Y ($fsmY - 80) -W 180 -H 80 -Fill $whyFill -Border $blue -FontSize "13"
$s2 = New-Shape -Content "<b>Escalate</b><br/>ED / urgent" -X ($cx - 280) -Y ($fsmY - 260) -W 180 -H 80 -Fill "#FADBD8" -Border $red -FontSize "13"
$s3 = New-Shape -Content "<b>Educate</b><br/>NS mechanical" -X ($cx - 280) -Y ($fsmY + 80) -W 180 -H 80 -Fill $howFill -Border $green -FontSize "13"
$s4 = New-Shape -Content "<b>Plan</b><br/>Self-care / follow-up" -X ($cx + 280) -Y ($fsmY + 80) -W 180 -H 80 -Fill $howFill -Border $green -FontSize "13"
$s5 = New-Shape -Content "<b>Open Q&amp;A</b><br/>User-defined" -X ($cx + 840) -Y ($fsmY + 80) -W 180 -H 80 -Fill $whenFill -Border $purple -FontSize "13"
$s6 = New-Shape -Content "<b>[Add state]</b>" -X ($cx + 1400) -Y ($fsmY - 80) -W 180 -H 80 -Fill $white -Border "#94a3b8" -FontSize "13" -BorderStyle "dashed"

$null = New-Connector -StartId $s0.id -EndId $s1.id -Color $navy
$null = New-Connector -StartId $s1.id -EndId $s2.id -Label "event: red flag" -Color $red
$null = New-Connector -StartId $s1.id -EndId $s3.id -Label "task done, no flag" -Color $green
$null = New-Connector -StartId $s3.id -EndId $s4.id -Color $green
$null = New-Connector -StartId $s4.id -EndId $s5.id -Color $purple

$null = New-Sticky -Content "Q: Are Encoder / Orchestrator / Generator states, or only implementation of Phi?" -X ($cx - 1100) -Y ($fsmY + 220) -FillColor $question
$null = New-Sticky -Content "[Add transition] e.g. user abandons screen" -X ($cx - 400) -Y ($fsmY + 220) -FillColor $empty
$null = New-Sticky -Content "[Add transition] e.g. return visit / worse at 48h" -X ($cx + 200) -Y ($fsmY + 220) -FillColor $empty
$null = New-Sticky -Content "Self-loop: Mohr notes unanswered notifications can repeat. What is our analogue in chat?" -X ($cx + 800) -Y ($fsmY + 220) -FillColor $question

# ============================================================
# 6. Hypotheses + parking lot
# ============================================================
$bottomY = 6380
$halfW = 1600
$halfH = 720
Write-Host "`n--- Hypotheses and parking lot ---" -ForegroundColor Yellow

$null = New-Frame -Title "9. Testable hypotheses and evaluation" -X 800 -Y $bottomY -W $halfW -H $halfH
$null = New-Shape -Content "<b>9. Testable hypotheses</b>   Mohr: formalize aims/elements/workflow so they can be tested. Distal ED visits != proximal knowledge." -X 800 -Y ($bottomY - $halfH / 2 + 22) -W ($halfW - 20) -H 44 -Fill $orange -Border $orange -TextColor $white -FontSize "15" -Align "left"
$null = New-Sticky -Content "[DRAFT] H1: After a negative screen, users will report lower intent to attend ED for this episode" -X 250 -Y ($bottomY - 180) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] H2: Completing screening (usage) is necessary but not sufficient for reduced ED intent" -X 480 -Y ($bottomY - 180) -FillColor $draft
$null = New-Sticky -Content "[DRAFT] H3: Escalation pathway will be used when red-flag items are endorsed (safety, not ED-reduction)" -X 710 -Y ($bottomY - 180) -FillColor $safety
$null = New-Sticky -Content "[Add proximal measure] knowledge / self-efficacy / fear-avoidance / care-seeking intent" -X 250 -Y ($bottomY + 10) -FillColor $empty
$null = New-Sticky -Content "[Add usage measure] turns, screen completion, return visits - not a proxy for clinical success" -X 480 -Y ($bottomY + 10) -FillColor $empty
$null = New-Sticky -Content "[Add distal measure] actual ED visits - likely later / harder; do not wait for this to iterate design" -X 710 -Y ($bottomY + 10) -FillColor $empty
$null = New-Sticky -Content "Q: What is 'unnecessary' ED - we need a working definition or this BIT cannot be evaluated." -X 940 -Y ($bottomY + 10) -FillColor $question
$null = New-Sticky -Content "[HCI / software metrics] usability, safety of advice, groundedness, hallucination rate" -X 480 -Y ($bottomY + 200) -FillColor $empty
$null = New-Text -Content "Drop zone - one hypothesis per sticky, naming the BIT component it tests" -X 800 -Y ($bottomY + 300) -W 1400 -FontSize "12" -Align "center" -Color "#666666"

$null = New-Frame -Title "10. Parking lot and open questions" -X 2500 -Y $bottomY -W $halfW -H $halfH
$null = New-Shape -Content "<b>10. Parking lot</b>   Ideas that do not yet belong in a trace" -X 2500 -Y ($bottomY - $halfH / 2 + 22) -W ($halfW - 20) -H 44 -Fill "#5D6D7E" -Border "#5D6D7E" -TextColor $white -FontSize "16" -Align "left"
$null = New-Sticky -Content "Q: Patient-only BIT, or also clinician-facing shared decision-making?" -X 1950 -Y ($bottomY - 180) -FillColor $question
$null = New-Sticky -Content "Q: Setting and timing - prevent the trip, or divert people already heading to ED?" -X 2180 -Y ($bottomY - 180) -FillColor $question
$null = New-Sticky -Content "Q: Equity / health literacy - who is most at risk of both unnecessary ED and missed red flags?" -X 2410 -Y ($bottomY - 180) -FillColor $question
$null = New-Sticky -Content "[Add theory] e.g. Common Sense Model, fear-avoidance, TAM - if we need more than Mohr+Michie" -X 2640 -Y ($bottomY - 180) -FillColor $empty
$null = New-Sticky -Content "[Add stakeholder] patients, ED, primary care, physio, health system" -X 1950 -Y ($bottomY + 10) -FillColor $empty
$null = New-Sticky -Content "[Add out of scope] diagnosis, imaging decisions, opioid advice, non-LBP" -X 2180 -Y ($bottomY + 10) -FillColor $empty
$null = New-Sticky -Content "[Add idea]" -X 2410 -Y ($bottomY + 10) -FillColor $empty
$null = New-Sticky -Content "[Add idea]" -X 2640 -Y ($bottomY + 10) -FillColor $empty
$null = New-Sticky -Content "[Add idea]" -X 2180 -Y ($bottomY + 200) -FillColor $empty
$null = New-Sticky -Content "[Add idea]" -X 2410 -Y ($bottomY + 200) -FillColor $empty
$null = New-Text -Content "If a sticky here earns a full Aim->Workflow chain, promote it to a new Trace card." -X 2500 -Y ($bottomY + 300) -W 1400 -FontSize "12" -Align "center" -Color "#666666"

# ============================================================
# Done
# ============================================================
$elapsed = (Get-Date) - $startTime
$view = "https://miro.com/app/board/$boardId/"
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "COMPLETE - DigiMSKbot BIT model starter board" -ForegroundColor Green
Write-Host "API calls:  $($script:apiCalls)"
Write-Host "Time:       $([Math]::Round($elapsed.TotalMinutes, 1)) minutes"
Write-Host "Board URL:  $view" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
