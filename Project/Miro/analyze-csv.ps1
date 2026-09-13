$csv = Import-Csv -Path "c:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot\Project\Brainstorming\HAICEF_271.csv"
$data = $csv | ForEach-Object {
    [PSCustomObject]@{
        L1 = $_."Level 1 construct".Trim()
        L2 = $_."Level 2 construct".Trim()
        L3 = $_."Level 3 construct".Trim()
        Q  = $_."Yes/No Question (Rephrased from Original Questions)".Trim()
    }
} | Where-Object { $_.Q -ne "" -and $_.L1 -ne "" }

$data | ForEach-Object { if ($_.L2 -eq "Assessibility") { $_.L2 = "Accessibility" } }

Write-Host "Total questions: $($data.Count)"

$l1s = $data | Select-Object -Property L1 -Unique
Write-Host "`nLevel 1 constructs: $($l1s.Count)"
$l1s | ForEach-Object { Write-Host "  - $($_.L1)" }

$l2s = $data | Select-Object -Property L1,L2 -Unique
Write-Host "`nLevel 2 constructs: $($l2s.Count)"
$l2s | ForEach-Object { Write-Host "  - [$($_.L1)] > $($_.L2)" }

$l3s = $data | Select-Object -Property L1,L2,L3 -Unique
Write-Host "`nLevel 3 constructs: $($l3s.Count)"

Write-Host "`nLargest L3 groups (by question count):"
$data | Group-Object -Property L3 | Sort-Object Count -Descending | Select-Object -First 10 | ForEach-Object {
    Write-Host ("  {0}: {1} questions" -f $_.Name, $_.Count)
}
