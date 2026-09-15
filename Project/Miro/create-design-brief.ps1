$ErrorActionPreference = "Stop"
$startTime = Get-Date

# ===== Configuration =====
$token = (Get-Content (Join-Path $PSScriptRoot ".env") | Where-Object { $_ -match "^MIRO_ACCESS_TOKEN=" }) -replace "^MIRO_ACCESS_TOKEN=", ""
$baseUri = "https://api.miro.com/v2"
$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}

# ===== API Helper with rate-limit handling =====
$script:apiCalls = 0
function Invoke-Miro {
    param([string]$Method, [string]$Uri, [string]$Body = $null)
    for ($try = 1; $try -le 5; $try++) {
        try {
            $p = @{ Uri=$Uri; Headers=$headers; Method=$Method; ContentType="application/json"; UseBasicParsing=$true }
            if ($Body) { $p.Body = [System.Text.Encoding]::UTF8.GetBytes($Body) }
            $resp = Invoke-WebRequest @p
            $script:apiCalls++

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

# ===== Color Palette =====
$colors = @{
    HeaderBg     = "#1B2A4A"
    HeaderText   = "#FFFFFF"
    SectionBg    = "#2D5F8A"
    SectionText  = "#FFFFFF"
    CardBg       = "#F0F4F8"
    CardBorder   = "#2D5F8A"
    CardText     = "#1B2A4A"
    AccentGreen  = "#1E6F45"
    AccentPurple = "#6C3483"
    AccentOrange = "#E67E22"
    AccentRed    = "#C0392B"
    AccentTeal   = "#17A589"
    StickyBlue   = "light_blue"
    StickyYellow = "light_yellow"
    StickyGreen  = "light_green"
    StickyPink   = "light_pink"
    StickyOrange = "orange"
    StickyGray   = "gray"
    White        = "#FFFFFF"
    LightGray    = "#F5F5F5"
    DarkText     = "#1a1a1a"
}

# ===== Layout Constants =====
$frameW = 900
$frameH = 550
$frameGapX = 100
$frameGapY = 100
$cols = 4
$startX = 0
$startY = 300

# ===== Delete old board if exists, create fresh =====
Write-Host "=== Setting up TRI-BACK Design Plan board ===" -ForegroundColor Cyan
$boardsList = Invoke-Miro -Method Get -Uri "$baseUri/boards"
foreach ($b in $boardsList.data) {
    if ($b.name -eq "TRI-BACK Design Plan") {
        Write-Host "Deleting old board: $($b.id)" -ForegroundColor Yellow
        try { Invoke-Miro -Method Delete -Uri "$baseUri/boards/$($b.id)" | Out-Null } catch {}
    }
}

$boardBody = @{
    name        = "TRI-BACK Design Plan"
    description = "Design brief and planning board for the TRI-BACK chatbot project."
} | ConvertTo-Json
$board = Invoke-Miro -Method Post -Uri "$baseUri/boards" -Body $boardBody
$boardId = $board.id
$boardViewLink = $board.viewLink
Write-Host "Board created: $boardViewLink" -ForegroundColor Green

# ===== Helper: calculate frame position from grid index =====
function Get-FramePos {
    param([int]$Index)
    $col = $Index % $cols
    $row = [Math]::Floor($Index / $cols)
    return @{
        X = $startX + $col * ($frameW + $frameGapX) + $frameW / 2
        Y = $startY + $row * ($frameH + $frameGapY) + $frameH / 2
    }
}

# ===== BOARD TITLE (above the grid) =====
Write-Host "`nCreating board title..." -ForegroundColor Yellow
$titleShape = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
    data     = @{ content = "<b>TRI-BACK Design Plan</b>"; shape = "round_rectangle" }
    style    = @{ fillColor = $colors.HeaderBg; color = $colors.HeaderText; borderColor = $colors.HeaderBg; fontSize = "36"; textAlign = "center"; textAlignVertical = "middle"; borderWidth = "2" }
    position = @{ x = $startX + (($cols - 1) * ($frameW + $frameGapX)) / 2 + $frameW / 2; y = $startY - 120 }
    geometry = @{ width = 1200; height = 100 }
} | ConvertTo-Json -Depth 5)
Write-Host "  Title created" -ForegroundColor Green

$subtitleText = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/texts" -Body (@{
    data     = @{ content = "AI-Powered Musculoskeletal Health Chatbot for Low Back Pain Education, Triage, and Shared Decision-Making" }
    style    = @{ fontSize = "18"; textAlign = "center"; color = "#666666" }
    position = @{ x = $startX + (($cols - 1) * ($frameW + $frameGapX)) / 2 + $frameW / 2; y = $startY - 50 }
    geometry = @{ width = 1200 }
} | ConvertTo-Json -Depth 5)

# ===== SECTION DEFINITIONS =====
$sections = @(
    # --- Row 1 ---
    @{
        Title = "1. Project Overview"
        Color = $colors.SectionBg
        Items = @(
            @{ Type="text"; Content="<b>Project Name:</b> TRI-BACK (Digital Musculoskeletal Bot)"; X=-300; Y=-150; W=800 }
            @{ Type="text"; Content="<b>Domain:</b> Musculoskeletal Health / Low Back Pain (LBP)"; X=-300; Y=-110; W=800 }
            @{ Type="text"; Content="<b>Institution:</b> UBC Postdoctoral Fellowship"; X=-300; Y=-70; W=800 }
            @{ Type="sticky"; Content="Principal Investigator / Lead"; FillColor="light_yellow"; X=-300; Y=50 }
            @{ Type="sticky"; Content="Clinical Advisors"; FillColor="light_yellow"; X=-70; Y=50 }
            @{ Type="sticky"; Content="Technical Team"; FillColor="light_yellow"; X=160; Y=50 }
            @{ Type="sticky"; Content="Key Stakeholders"; FillColor="light_yellow"; X=300; Y=50 }
            @{ Type="text"; Content="<b>Start Date:</b> [TBD]  |  <b>Target Launch:</b> [TBD]"; X=-300; Y=170; W=800 }
        )
    },
    @{
        Title = "2. Problem Statement"
        Color = $colors.AccentRed
        Items = @(
            @{ Type="text"; Content="<b>The Challenge</b>"; X=0; Y=-180; W=800 }
            @{ Type="text"; Content="Low back pain (LBP) is the leading cause of disability worldwide. Patients often lack accessible, evidence-based education and guidance for self-management. Current digital health tools for MSK conditions lack standardized evaluation frameworks and rarely link clinical outcomes to chatbot design."; X=0; Y=-100; W=800 }
            @{ Type="sticky"; Content="Gap: Most chatbot research is outside MSK/LBP domains"; FillColor="light_pink"; X=-250; Y=60 }
            @{ Type="sticky"; Content="Gap: No standardized evaluation metrics across chatbot studies"; FillColor="light_pink"; X=0; Y=60 }
            @{ Type="sticky"; Content="Gap: Clinical outcomes rarely linked to chatbot development techniques"; FillColor="light_pink"; X=250; Y=60 }
            @{ Type="text"; Content="<i>Evidence: Pattern matching and fixed-output generation still dominate medical chatbots, lagging behind LLM-based dialogue advances (Safi et al. 2020)</i>"; X=0; Y=180; W=800 }
        )
    },
    @{
        Title = "3. Goals and Objectives"
        Color = $colors.AccentGreen
        Items = @(
            @{ Type="shape"; Content="<b>Primary Goal</b><br><br>Build an AI-powered MSK health chatbot for LBP patient education, triage, and shared decision-making"; Fill="#D5F5E3"; Border="#1E6F45"; X=0; Y=-140; W=760; H=100 }
            @{ Type="sticky"; Content="Obj 1: Develop domain-specific LLM dialogue system for LBP"; FillColor="light_green"; X=-280; Y=20 }
            @{ Type="sticky"; Content="Obj 2: Integrate RAG with MSK clinical knowledge base"; FillColor="light_green"; X=-50; Y=20 }
            @{ Type="sticky"; Content="Obj 3: Validate using HAICEF framework (271 evaluation questions)"; FillColor="light_green"; X=180; Y=20 }
            @{ Type="sticky"; Content="Obj 4: Achieve evidence-based, patient-centered outcomes"; FillColor="light_green"; X=-280; Y=150 }
            @{ Type="sticky"; Content="Obj 5: Ensure safety, privacy, and fairness compliance"; FillColor="light_green"; X=-50; Y=150 }
            @{ Type="sticky"; Content="Obj 6: Publish findings and open-source components"; FillColor="light_green"; X=180; Y=150 }
        )
    },
    @{
        Title = "4. Target Audience"
        Color = $colors.AccentPurple
        Items = @(
            @{ Type="shape"; Content="<b>Primary Users</b><br>Patients with LBP seeking education and self-management guidance"; Fill="#E8DAEF"; Border="#6C3483"; X=-200; Y=-120; W=350; H=100 }
            @{ Type="shape"; Content="<b>Secondary Users</b><br>Clinicians using chatbot for patient triage and shared decision-making"; Fill="#E8DAEF"; Border="#6C3483"; X=200; Y=-120; W=350; H=100 }
            @{ Type="sticky"; Content="User Persona: Patient seeking to understand their diagnosis"; FillColor="light_blue"; X=-250; Y=50 }
            @{ Type="sticky"; Content="User Persona: Patient exploring treatment options"; FillColor="light_blue"; X=0; Y=50 }
            @{ Type="sticky"; Content="User Persona: Clinician screening patient intake"; FillColor="orange"; X=250; Y=50 }
            @{ Type="text"; Content="<b>Health Literacy Consideration:</b> Readability targets must be met - oversimplified prompts reduce clinical completeness (Basharat et al. 2025)"; X=0; Y=170; W=800 }
        )
    },
    # --- Row 2 ---
    @{
        Title = "5. Scope and Deliverables"
        Color = $colors.SectionBg
        Items = @(
            @{ Type="text"; Content="<b>In Scope</b>"; X=-250; Y=-170; W=350 }
            @{ Type="sticky"; Content="LBP patient education chatbot"; FillColor="light_green"; X=-300; Y=-80 }
            @{ Type="sticky"; Content="Triage and risk stratification"; FillColor="light_green"; X=-300; Y=20 }
            @{ Type="sticky"; Content="Shared decision-making support"; FillColor="light_green"; X=-300; Y=120 }
            @{ Type="sticky"; Content="Multi-turn conversational dialogue"; FillColor="light_green"; X=-100; Y=-80 }
            @{ Type="sticky"; Content="Clinical knowledge integration (RAG)"; FillColor="light_green"; X=-100; Y=20 }
            @{ Type="sticky"; Content="HAICEF-based evaluation"; FillColor="light_green"; X=-100; Y=120 }
            @{ Type="text"; Content="<b>Out of Scope</b>"; X=200; Y=-170; W=350 }
            @{ Type="sticky"; Content="Diagnosis or prescribing"; FillColor="light_pink"; X=200; Y=-80 }
            @{ Type="sticky"; Content="Emergency / red flag management"; FillColor="light_pink"; X=200; Y=20 }
            @{ Type="sticky"; Content="Non-MSK conditions"; FillColor="light_pink"; X=200; Y=120 }
        )
    },
    @{
        Title = "6. System Architecture"
        Color = $colors.AccentTeal
        Items = @(
            @{ Type="text"; Content="<b>Core Components (McTear 2002)</b>"; X=0; Y=-180; W=800 }
            @{ Type="shape"; Content="<b>Speech / Text Input</b>"; Fill="#D4EFDF"; Border="#1E6F45"; X=-300; Y=-100; W=180; H=60 }
            @{ Type="shape"; Content="<b>Language Understanding</b><br>(NLU / Intent Recognition)"; Fill="#D4EFDF"; Border="#1E6F45"; X=-100; Y=-100; W=180; H=60 }
            @{ Type="shape"; Content="<b>Dialogue Manager</b>"; Fill="#AED6F1"; Border="#2D5F8A"; X=100; Y=-100; W=180; H=60 }
            @{ Type="shape"; Content="<b>Knowledge Base</b><br>(RAG + Clinical Data)"; Fill="#AED6F1"; Border="#2D5F8A"; X=300; Y=-100; W=180; H=60 }
            @{ Type="shape"; Content="<b>Language Generator</b><br>(LLM Response)"; Fill="#D4EFDF"; Border="#1E6F45"; X=100; Y=0; W=180; H=60 }
            @{ Type="shape"; Content="<b>Text / Speech Output</b>"; Fill="#D4EFDF"; Border="#1E6F45"; X=-100; Y=0; W=180; H=60 }
            @{ Type="sticky"; Content="Multi-agent framework with DPO alignment (Cheng et al. 2025)"; FillColor="light_blue"; X=-200; Y=120 }
            @{ Type="sticky"; Content="RAG with intention recognition for contextual accuracy"; FillColor="light_blue"; X=50; Y=120 }
            @{ Type="sticky"; Content="Open-source toolkits (e.g. Rasa) for rapid bootstrapping"; FillColor="light_blue"; X=280; Y=120 }
        )
    },
    @{
        Title = "7. Technical Requirements"
        Color = $colors.SectionBg
        Items = @(
            @{ Type="sticky"; Content="LLM: Domain-specific fine-tuned model for MSK/LBP"; FillColor="light_blue"; X=-250; Y=-100 }
            @{ Type="sticky"; Content="RAG Pipeline: Clinical guideline retrieval and grounding"; FillColor="light_blue"; X=0; Y=-100 }
            @{ Type="sticky"; Content="DPO: Direct preference optimization for expert alignment"; FillColor="light_blue"; X=250; Y=-100 }
            @{ Type="sticky"; Content="NLU: Intent recognition and entity extraction"; FillColor="light_yellow"; X=-250; Y=20 }
            @{ Type="sticky"; Content="Database: Patient data, clinical guidelines, conversation logs"; FillColor="light_yellow"; X=0; Y=20 }
            @{ Type="sticky"; Content="API: RESTful endpoints for frontend integration"; FillColor="light_yellow"; X=250; Y=20 }
            @{ Type="sticky"; Content="Security: HIPAA/PIPEDA compliance, encryption at rest and transit"; FillColor="orange"; X=-250; Y=140 }
            @{ Type="sticky"; Content="Hosting: Cloud infrastructure with scalability"; FillColor="orange"; X=0; Y=140 }
            @{ Type="sticky"; Content="Monitoring: Conversation logging and analytics dashboard"; FillColor="orange"; X=250; Y=140 }
        )
    },
    @{
        Title = "8. Evaluation Framework"
        Color = $colors.AccentOrange
        Items = @(
            @{ Type="shape"; Content="<b>HAICEF Framework</b><br>(Hua et al. 2025)<br>271 evaluation questions"; Fill="#FDEBD0"; Border="#E67E22"; X=0; Y=-150; W=400; H=80 }
            @{ Type="shape"; Content="<b>Safety, Privacy &amp; Fairness</b><br>21% of questions"; Fill="#FADBD8"; Border="#C0392B"; X=-280; Y=-30; W=220; H=70 }
            @{ Type="shape"; Content="<b>Trustworthiness &amp; Usefulness</b><br>39% of questions"; Fill="#D5F5E3"; Border="#1E6F45"; X=0; Y=-30; W=220; H=70 }
            @{ Type="shape"; Content="<b>Design &amp; Operational Effectiveness</b><br>40% of questions"; Fill="#D4E6F1"; Border="#2D5F8A"; X=280; Y=-30; W=220; H=70 }
            @{ Type="text"; Content="18 second-level constructs  |  60 third-level constructs"; X=0; Y=50; W=700 }
            @{ Type="sticky"; Content="3-Bot AI evaluator system for rapid testing (Choo et al. 2025)"; FillColor="light_yellow"; X=-200; Y=150 }
            @{ Type="sticky"; Content="Conversation-log-derived metrics as complement to surveys"; FillColor="light_yellow"; X=50; Y=150 }
            @{ Type="sticky"; Content="Prospective validation and Delphi consensus (planned)"; FillColor="light_yellow"; X=280; Y=150 }
        )
    },
    # --- Row 3 ---
    @{
        Title = "9. Data Sources"
        Color = $colors.AccentTeal
        Items = @(
            @{ Type="text"; Content="<b>Available Datasets for Development</b>"; X=0; Y=-180; W=800 }
            @{ Type="sticky"; Content="Open-LBP-RF: Clinical notes annotated for LBP imaging risk factors (HuggingFace)"; FillColor="light_blue"; X=-250; Y=-80 }
            @{ Type="sticky"; Content="Italian LBP Dataset: MRI reports, X-ray reports, consultation notes"; FillColor="light_blue"; X=0; Y=-80 }
            @{ Type="sticky"; Content="PMR-Q&A: PMR-themed Q&A from scientific texts (filterable for LBP)"; FillColor="light_blue"; X=250; Y=-80 }
            @{ Type="sticky"; Content="One in a Million: 327 primary care consultations with verbatim transcripts"; FillColor="light_green"; X=-250; Y=50 }
            @{ Type="sticky"; Content="MedDialog: 0.26M conversations, 96 specialties (HuggingFace)"; FillColor="light_green"; X=0; Y=50 }
            @{ Type="sticky"; Content="i2b2/n2c2: ClinicalSTS and Medical Concept Normalization corpora"; FillColor="light_green"; X=250; Y=50 }
            @{ Type="sticky"; Content="Reddit r/backpain and HealthUnlocked forums (scraping potential)"; FillColor="orange"; X=0; Y=170 }
        )
    },
    @{
        Title = "10. Design Constraints"
        Color = $colors.AccentRed
        Items = @(
            @{ Type="sticky"; Content="Must meet health literacy readability targets for patient-facing content"; FillColor="light_pink"; X=-250; Y=-100 }
            @{ Type="sticky"; Content="Cannot provide diagnosis, prescriptions, or emergency medical advice"; FillColor="light_pink"; X=0; Y=-100 }
            @{ Type="sticky"; Content="Must comply with privacy regulations (HIPAA / PIPEDA / institutional ethics)"; FillColor="light_pink"; X=250; Y=-100 }
            @{ Type="sticky"; Content="Hallucination minimization is critical for medical safety"; FillColor="orange"; X=-250; Y=30 }
            @{ Type="sticky"; Content="Response accuracy > response length (length is unreliable proxy for correctness)"; FillColor="orange"; X=0; Y=30 }
            @{ Type="sticky"; Content="Must handle red flags with appropriate escalation pathways"; FillColor="orange"; X=250; Y=30 }
            @{ Type="sticky"; Content="Budget and compute constraints for model training and hosting"; FillColor="light_yellow"; X=-130; Y=150 }
            @{ Type="sticky"; Content="Must be accessible across devices and user demographics"; FillColor="light_yellow"; X=130; Y=150 }
        )
    },
    @{
        Title = "11. Success Metrics and KPIs"
        Color = $colors.AccentGreen
        Items = @(
            @{ Type="text"; Content="<b>Technical Metrics</b>"; X=-250; Y=-170; W=350 }
            @{ Type="sticky"; Content="Response accuracy vs. clinical guidelines (target: >90%)"; FillColor="light_green"; X=-250; Y=-80 }
            @{ Type="sticky"; Content="Hallucination rate (target: <5%)"; FillColor="light_green"; X=-250; Y=20 }
            @{ Type="sticky"; Content="Conversation-turns per session (CPS)"; FillColor="light_green"; X=-250; Y=120 }
            @{ Type="text"; Content="<b>User and Clinical Metrics</b>"; X=150; Y=-170; W=350 }
            @{ Type="sticky"; Content="Usability score (SUS target: >68)"; FillColor="light_blue"; X=150; Y=-80 }
            @{ Type="sticky"; Content="Informed decision-making rate improvement"; FillColor="light_blue"; X=150; Y=20 }
            @{ Type="sticky"; Content="Patient satisfaction and comprehension scores"; FillColor="light_blue"; X=150; Y=120 }
        )
    },
    @{
        Title = "12. Risks and Mitigations"
        Color = $colors.AccentRed
        Items = @(
            @{ Type="text"; Content="<b>Risk</b>"; X=-250; Y=-170; W=300 }
            @{ Type="text"; Content="<b>Mitigation</b>"; X=150; Y=-170; W=300 }
            @{ Type="sticky"; Content="LLM hallucination producing harmful medical advice"; FillColor="light_pink"; X=-250; Y=-70 }
            @{ Type="sticky"; Content="RAG grounding + DPO alignment + human-in-the-loop review"; FillColor="light_green"; X=150; Y=-70 }
            @{ Type="sticky"; Content="Privacy breach of patient health data"; FillColor="light_pink"; X=-250; Y=50 }
            @{ Type="sticky"; Content="End-to-end encryption + de-identification + ethics board approval"; FillColor="light_green"; X=150; Y=50 }
            @{ Type="sticky"; Content="Bias in training data leading to unfair outcomes"; FillColor="light_pink"; X=-250; Y=160 }
            @{ Type="sticky"; Content="Diverse dataset curation + fairness auditing + HAICEF safety domain"; FillColor="light_green"; X=150; Y=160 }
        )
    },
    # --- Row 4 (single wide frame) ---
    @{
        Title = "13. Timeline and Milestones"
        Color = $colors.HeaderBg
        Wide  = $true
        Items = @(
            @{ Type="shape"; Content="<b>Phase 1</b><br>Literature Review &amp; Framework Selection"; Fill="#D4E6F1"; Border="#2D5F8A"; X=-700; Y=-50; W=200; H=100 }
            @{ Type="shape"; Content="<b>Phase 2</b><br>Data Collection &amp; Curation"; Fill="#D4E6F1"; Border="#2D5F8A"; X=-440; Y=-50; W=200; H=100 }
            @{ Type="shape"; Content="<b>Phase 3</b><br>System Architecture &amp; Prototyping"; Fill="#AED6F1"; Border="#2D5F8A"; X=-180; Y=-50; W=200; H=100 }
            @{ Type="shape"; Content="<b>Phase 4</b><br>LLM Fine-Tuning &amp; RAG Integration"; Fill="#AED6F1"; Border="#2D5F8A"; X=80; Y=-50; W=200; H=100 }
            @{ Type="shape"; Content="<b>Phase 5</b><br>HAICEF Evaluation &amp; Testing"; Fill="#D5F5E3"; Border="#1E6F45"; X=340; Y=-50; W=200; H=100 }
            @{ Type="shape"; Content="<b>Phase 6</b><br>Clinical Validation &amp; Publication"; Fill="#D5F5E3"; Border="#1E6F45"; X=600; Y=-50; W=200; H=100 }
            @{ Type="text"; Content="[Add dates and milestones for each phase]"; X=0; Y=100; W=600 }
        )
    }
)

# ===== Build the Board =====
$totalItems = 0
foreach ($s in $sections) { $totalItems += $s.Items.Count + 2 }
Write-Host "`n=== Building design brief ($($sections.Count) sections, ~$totalItems items) ===" -ForegroundColor Cyan
Write-Host "Estimated time: ~$([Math]::Ceiling($totalItems * 0.55 / 60)) minutes`n"

$sectionIndex = 0
foreach ($section in $sections) {
    $pos = Get-FramePos -Index $sectionIndex
    $isWide = $section.Wide -eq $true
    $actualW = if ($isWide) { $cols * $frameW + ($cols - 1) * $frameGapX } else { $frameW }

    if ($isWide) {
        $pos.X = $startX + $actualW / 2
    }

    Write-Host "--- Section: $($section.Title) ---" -ForegroundColor Yellow

    # Create frame
    $frame = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/frames" -Body (@{
        data     = @{ title = $section.Title; format = "custom" }
        position = @{ x = $pos.X; y = $pos.Y }
        geometry = @{ width = $actualW; height = $frameH }
    } | ConvertTo-Json -Depth 5)
    Write-Host "  Frame created (id=$($frame.id))"

    # Section header bar inside frame
    $headerBar = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
        data     = @{ content = "<b>$($section.Title)</b>"; shape = "rectangle" }
        style    = @{ fillColor = $section.Color; color = $colors.White; borderColor = $section.Color; fontSize = "18"; textAlign = "left"; textAlignVertical = "middle"; borderWidth = "2" }
        position = @{ x = $pos.X; y = $pos.Y - $frameH / 2 + 25 }
        geometry = @{ width = $actualW - 20; height = 40 }
    } | ConvertTo-Json -Depth 5)
    Write-Host "  Header bar created"

    # Create items
    foreach ($item in $section.Items) {
        $itemX = $pos.X + $item.X
        $itemY = $pos.Y + $item.Y

        switch ($item.Type) {
            "text" {
                $null = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/texts" -Body (@{
                    data     = @{ content = $item.Content }
                    style    = @{ fontSize = "14"; textAlign = "left"; color = $colors.DarkText }
                    position = @{ x = $itemX; y = $itemY }
                    geometry = @{ width = $item.W }
                } | ConvertTo-Json -Depth 5)
                $preview = if ($item.Content.Length -gt 60) { $item.Content.Substring(0,57) + "..." } else { $item.Content }
                Write-Host "  Text: $preview"
            }
            "sticky" {
                $null = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/sticky_notes" -Body (@{
                    data     = @{ content = $item.Content; shape = "square" }
                    style    = @{ fillColor = $item.FillColor }
                    position = @{ x = $itemX; y = $itemY }
                } | ConvertTo-Json -Depth 5)
                $preview = if ($item.Content.Length -gt 60) { $item.Content.Substring(0,57) + "..." } else { $item.Content }
                Write-Host "  Sticky: $preview"
            }
            "shape" {
                $null = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body (@{
                    data     = @{ content = $item.Content; shape = "round_rectangle" }
                    style    = @{ fillColor = $item.Fill; color = $colors.DarkText; borderColor = $item.Border; fontSize = "12"; textAlign = "center"; textAlignVertical = "middle"; borderWidth = "2" }
                    position = @{ x = $itemX; y = $itemY }
                    geometry = @{ width = $item.W; height = $item.H }
                } | ConvertTo-Json -Depth 5)
                $preview = if ($item.Content.Length -gt 60) { $item.Content.Substring(0,57) + "..." } else { $item.Content }
                Write-Host "  Shape: $preview"
            }
        }
    }

    $sectionIndex++
    Write-Host ""
}

# ===== Done =====
$elapsed = (Get-Date) - $startTime
Write-Host "========================================" -ForegroundColor Green
Write-Host "COMPLETE!" -ForegroundColor Green
Write-Host "Sections:   $($sections.Count)"
Write-Host "API calls:  $($script:apiCalls)"
Write-Host "Time:       $([Math]::Round($elapsed.TotalMinutes, 1)) minutes"
Write-Host "Board URL:  $boardViewLink" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
