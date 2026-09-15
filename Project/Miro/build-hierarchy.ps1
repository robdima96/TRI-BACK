$ErrorActionPreference = "Stop"
$startTime = Get-Date

# ===== Configuration =====
$token = (Get-Content (Join-Path $PSScriptRoot ".env") | Where-Object { $_ -match "^MIRO_ACCESS_TOKEN=" }) -replace "^MIRO_ACCESS_TOKEN=", ""
$baseUri = "https://api.miro.com/v2"
$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
}

# Shape dimensions
$qW = 200; $qH = 100
$l3W = 220; $l3H = 70
$l2W = 260; $l2H = 80
$l1W = 320; $l1H = 90

# Spacing
$qGap  = 14
$l3Gap = 50
$l2Gap = 90
$l1Gap = 140

# Vertical positions (pyramid top to bottom)
$yL1 = 0
$yL2 = 350
$yL3 = 700
$yQ  = 1100

# Color families keyed by L1 name
$colorMap = @{
    "Design and Operational Effectiveness" = @{
        L1f="#1B4F72"; L1c="#FFFFFF"; L1b="#1B4F72"
        L2f="#2980B9"; L2c="#FFFFFF"; L2b="#2980B9"
        L3f="#7FB3D8"; L3c="#1B4F72"; L3b="#5DADE2"
        Qf="#D4E6F1";  Qc="#1B4F72";  Qb="#AED6F1"
        line="#2980B9"
    }
    "Trustworthiness and usefulness" = @{
        L1f="#1E6F45"; L1c="#FFFFFF"; L1b="#1E6F45"
        L2f="#27AE60"; L2c="#FFFFFF"; L2b="#27AE60"
        L3f="#82E0AA"; L3c="#1E6F45"; L3b="#58D68D"
        Qf="#D5F5E3";  Qc="#1E6F45";  Qb="#ABEBC6"
        line="#27AE60"
    }
    "Safety, privacy, and fairness" = @{
        L1f="#6C3483"; L1c="#FFFFFF"; L1b="#6C3483"
        L2f="#8E44AD"; L2c="#FFFFFF"; L2b="#8E44AD"
        L3f="#C39BD3"; L3c="#6C3483"; L3b="#AF7AC5"
        Qf="#E8DAEF";  Qc="#6C3483";  Qb="#D2B4DE"
        line="#8E44AD"
    }
}

# ===== API Helper =====
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

function Escape-Html([string]$t) {
    return $t.Replace("&","&amp;").Replace("<","&lt;").Replace(">","&gt;")
}

# ===== Parse CSV =====
Write-Host "=== Parsing CSV ===" -ForegroundColor Cyan
$csv = Import-Csv -Path "c:\ROBS STUFF\UBC Postdoctoral Fellowship\TRI-BACK\Project\Brainstorming\HAICEF_271.csv"

$l1Order = [System.Collections.ArrayList]@()
$hierarchy = [ordered]@{}

foreach ($row in $csv) {
    $r1 = $row."Level 1 construct".Trim()
    $r2 = $row."Level 2 construct".Trim()
    $r3 = $row."Level 3 construct".Trim()
    $rq = $row."Yes/No Question (Rephrased from Original Questions)".Trim()

    if (-not $rq -or -not $r1) { continue }
    if ($r2 -eq "Assessibility") { $r2 = "Accessibility" }

    if (-not $hierarchy.Contains($r1)) {
        $hierarchy[$r1] = [ordered]@{}
        [void]$l1Order.Add($r1)
    }
    if (-not $hierarchy[$r1].Contains($r2)) {
        $hierarchy[$r1][$r2] = [ordered]@{}
    }
    if (-not $hierarchy[$r1][$r2].Contains($r3)) {
        $hierarchy[$r1][$r2][$r3] = [System.Collections.ArrayList]@()
    }
    [void]$hierarchy[$r1][$r2][$r3].Add($rq)
}

$nL1 = $l1Order.Count
$nL2 = 0; $nL3 = 0; $nQ = 0
foreach ($a in $l1Order) {
    foreach ($b in $hierarchy[$a].Keys) {
        $nL2++
        foreach ($c in $hierarchy[$a][$b].Keys) {
            $nL3++
            $nQ += $hierarchy[$a][$b][$c].Count
        }
    }
}
$totalShapes = $nL1 + $nL2 + $nL3 + $nQ
$totalConns  = $nL2 + $nL3 + $nQ
$totalOps    = $totalShapes + $totalConns
Write-Host "Hierarchy: $nL1 L1 > $nL2 L2 > $nL3 L3 > $nQ Questions"
Write-Host "Total API calls: $totalOps (shapes: $totalShapes, connectors: $totalConns)"
Write-Host "Estimated time: ~$([Math]::Ceiling($totalOps * 0.55 / 60)) minutes"

# ===== Calculate Positions (bottom-up widths, top-down placement) =====
Write-Host "`n=== Calculating layout ===" -ForegroundColor Cyan

$l3Widths = @{}
$l2Widths = @{}
$l1Widths = @{}

foreach ($a in $l1Order) {
    $l2Total = 0
    $l2Keys = @($hierarchy[$a].Keys)
    foreach ($b in $l2Keys) {
        $l3Total = 0
        $l3Keys = @($hierarchy[$a][$b].Keys)
        foreach ($c in $l3Keys) {
            $n = $hierarchy[$a][$b][$c].Count
            $w = [Math]::Max($l3W, $n * ($qW + $qGap) - $qGap)
            $l3Widths["$a|$b|$c"] = $w
            $l3Total += $w
        }
        if ($l3Keys.Count -gt 1) { $l3Total += ($l3Keys.Count - 1) * $l3Gap }
        $l2Widths["$a|$b"] = [Math]::Max($l2W, $l3Total)
        $l2Total += $l2Widths["$a|$b"]
    }
    if ($l2Keys.Count -gt 1) { $l2Total += ($l2Keys.Count - 1) * $l2Gap }
    $l1Widths[$a] = [Math]::Max($l1W, $l2Total)
}

$totalWidth = ($l1Widths.Values | Measure-Object -Sum).Sum + ($nL1 - 1) * $l1Gap
Write-Host "Board width: $totalWidth px"

# Top-down placement
$pos = @{}
$curX = -$totalWidth / 2.0

foreach ($a in $l1Order) {
    $aW = $l1Widths[$a]
    $aCX = $curX + $aW / 2.0
    $pos["L1|$a"] = @{ X=$aCX; Y=$yL1 }

    $l2Keys = @($hierarchy[$a].Keys)
    $l2TotalW = 0
    foreach ($b in $l2Keys) { $l2TotalW += $l2Widths["$a|$b"] }
    if ($l2Keys.Count -gt 1) { $l2TotalW += ($l2Keys.Count - 1) * $l2Gap }
    $l2X = $aCX - $l2TotalW / 2.0

    foreach ($b in $l2Keys) {
        $bW = $l2Widths["$a|$b"]
        $bCX = $l2X + $bW / 2.0
        $pos["L2|$a|$b"] = @{ X=$bCX; Y=$yL2 }

        $l3Keys = @($hierarchy[$a][$b].Keys)
        $l3TotalW = 0
        foreach ($c in $l3Keys) { $l3TotalW += $l3Widths["$a|$b|$c"] }
        if ($l3Keys.Count -gt 1) { $l3TotalW += ($l3Keys.Count - 1) * $l3Gap }
        $l3X = $bCX - $l3TotalW / 2.0

        foreach ($c in $l3Keys) {
            $cW = $l3Widths["$a|$b|$c"]
            $cCX = $l3X + $cW / 2.0
            $pos["L3|$a|$b|$c"] = @{ X=$cCX; Y=$yL3 }

            $qs = $hierarchy[$a][$b][$c]
            $qTotalW = $qs.Count * ($qW + $qGap) - $qGap
            $qX = $cCX - $qTotalW / 2.0
            for ($i = 0; $i -lt $qs.Count; $i++) {
                $pos["Q|$a|$b|$c|$i"] = @{ X = ($qX + $qW / 2.0); Y = $yQ }
                $qX += $qW + $qGap
            }
            $l3X += $cW + $l3Gap
        }
        $l2X += $bW + $l2Gap
    }
    $curX += $aW + $l1Gap
}
Write-Host "Layout calculated for $($pos.Count) items"

# ===== Create Board =====
Write-Host "`n=== Creating Miro board ===" -ForegroundColor Cyan
$boardBody = @{ name = "HAICEF 271 - Hierarchical Diagram"; description = "Pyramid hierarchy: $nL1 L1 > $nL2 L2 > $nL3 L3 > $nQ questions" } | ConvertTo-Json
$board = Invoke-Miro -Method Post -Uri "$baseUri/boards" -Body $boardBody
$boardId = $board.id
Write-Host "Board created: $($board.viewLink)" -ForegroundColor Green

# ===== Create Shapes =====
Write-Host "`n=== Creating shapes ($totalShapes total) ===" -ForegroundColor Cyan
$ids = @{}
$n = 0

function New-Shape {
    param($Key, $Content, $X, $Y, $W, $H, $Fill, $Color, $Border, $FontSize, $Bold)
    $script:n++
    $preview = if ($Content.Length -gt 50) { $Content.Substring(0,47) + "..." } else { $Content }
    $pct = [Math]::Round($script:n / $totalOps * 100, 1)
    Write-Host "[$script:n/$totalOps ${pct}%] Shape: $preview"

    $text = if ($Bold) { "<b>$(Escape-Html $Content)</b>" } else { Escape-Html $Content }
    $body = @{
        data = @{ content = $text; shape = "round_rectangle" }
        style = @{ fillColor = $Fill; color = $Color; borderColor = $Border; fontSize = $FontSize; textAlign = "center"; textAlignVertical = "middle"; borderWidth = "2" }
        position = @{ x = $X; y = $Y }
        geometry = @{ width = $W; height = $H }
    } | ConvertTo-Json -Depth 5
    $item = Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/shapes" -Body $body
    $script:ids[$Key] = $item.id
}

foreach ($a in $l1Order) {
    $cm = $colorMap[$a]
    $p = $pos["L1|$a"]
    New-Shape -Key "L1|$a" -Content $a -X $p.X -Y $p.Y -W $l1W -H $l1H -Fill $cm.L1f -Color $cm.L1c -Border $cm.L1b -FontSize "24" -Bold $true
}

foreach ($a in $l1Order) {
    $cm = $colorMap[$a]
    foreach ($b in @($hierarchy[$a].Keys)) {
        $p = $pos["L2|$a|$b"]
        New-Shape -Key "L2|$a|$b" -Content $b -X $p.X -Y $p.Y -W $l2W -H $l2H -Fill $cm.L2f -Color $cm.L2c -Border $cm.L2b -FontSize "14" -Bold $true
    }
}

foreach ($a in $l1Order) {
    $cm = $colorMap[$a]
    foreach ($b in @($hierarchy[$a].Keys)) {
        foreach ($c in @($hierarchy[$a][$b].Keys)) {
            $p = $pos["L3|$a|$b|$c"]
            New-Shape -Key "L3|$a|$b|$c" -Content $c -X $p.X -Y $p.Y -W $l3W -H $l3H -Fill $cm.L3f -Color $cm.L3c -Border $cm.L3b -FontSize "14" -Bold $false
        }
    }
}

foreach ($a in $l1Order) {
    $cm = $colorMap[$a]
    foreach ($b in @($hierarchy[$a].Keys)) {
        foreach ($c in @($hierarchy[$a][$b].Keys)) {
            $qs = $hierarchy[$a][$b][$c]
            for ($i = 0; $i -lt $qs.Count; $i++) {
                $p = $pos["Q|$a|$b|$c|$i"]
                New-Shape -Key "Q|$a|$b|$c|$i" -Content $qs[$i] -X $p.X -Y $p.Y -W $qW -H $qH -Fill $cm.Qf -Color $cm.Qc -Border $cm.Qb -FontSize "10" -Bold $false
            }
        }
    }
}

Write-Host "`nAll $totalShapes shapes created!" -ForegroundColor Green

# ===== Create Connectors =====
Write-Host "`n=== Creating connectors ($totalConns total) ===" -ForegroundColor Cyan

function New-Conn {
    param($StartKey, $EndKey, $StrokeColor, $Width)
    $script:n++
    $pct = [Math]::Round($script:n / $totalOps * 100, 1)
    if ($script:n % 10 -eq 0 -or $pct -ge 99) {
        Write-Host "[$script:n/$totalOps ${pct}%] Connectors..."
    }
    $body = @{
        startItem = @{ id = $script:ids[$StartKey] }
        endItem   = @{ id = $script:ids[$EndKey] }
        style     = @{ strokeColor = $StrokeColor; strokeWidth = $Width }
        shape     = "straight"
    } | ConvertTo-Json -Depth 5
    Invoke-Miro -Method Post -Uri "$baseUri/boards/$boardId/connectors" -Body $body | Out-Null
}

foreach ($a in $l1Order) {
    $cm = $colorMap[$a]
    foreach ($b in @($hierarchy[$a].Keys)) {
        New-Conn -StartKey "L1|$a" -EndKey "L2|$a|$b" -StrokeColor $cm.line -Width "3"
    }
}

foreach ($a in $l1Order) {
    $cm = $colorMap[$a]
    foreach ($b in @($hierarchy[$a].Keys)) {
        foreach ($c in @($hierarchy[$a][$b].Keys)) {
            New-Conn -StartKey "L2|$a|$b" -EndKey "L3|$a|$b|$c" -StrokeColor $cm.line -Width "2"
        }
    }
}

foreach ($a in $l1Order) {
    $cm = $colorMap[$a]
    foreach ($b in @($hierarchy[$a].Keys)) {
        foreach ($c in @($hierarchy[$a][$b].Keys)) {
            $qs = $hierarchy[$a][$b][$c]
            for ($i = 0; $i -lt $qs.Count; $i++) {
                New-Conn -StartKey "L3|$a|$b|$c" -EndKey "Q|$a|$b|$c|$i" -StrokeColor $cm.line -Width "1"
            }
        }
    }
}

# ===== Done =====
$elapsed = (Get-Date) - $startTime
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "COMPLETE!" -ForegroundColor Green
Write-Host "Shapes:     $totalShapes"
Write-Host "Connectors: $totalConns"
Write-Host "API calls:  $($script:apiCalls)"
Write-Host "Time:       $([Math]::Round($elapsed.TotalMinutes, 1)) minutes"
Write-Host "Board URL:  $($board.viewLink)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Green
