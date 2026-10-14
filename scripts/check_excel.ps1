<#
.SYNOPSIS
    Open a workbook in Excel, recalculate every formula, and report errors and chosen outputs.
.DESCRIPTION
    Week 12. openpyxl writes formulas without results; only Excel (or LibreOffice) computes
    them. This script opens a COPY of the workbook in a hidden Excel, runs a full
    recalculation, counts formula cells and error cells on every sheet, and then plays the
    test cases of -CasesJson through the Peer Benchmark sheet and every year through the
    Sector Summary and DQS view sheets. The result is JSON (stdout, or -Out), read by
    tests/test_bi.py, which compares the numbers with the warehouse. Windows with Excel only.
.EXAMPLE
    .\scripts\check_excel.ps1 -Path exports\public\esg_lens_public.xlsx -Out excel_check.json
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Path,
    [string]$CasesJson = '',
    [string]$Out = ''
)
$ErrorActionPreference = 'Stop'

$source = (Resolve-Path $Path).Path
$copy = Join-Path ([IO.Path]::GetTempPath()) ("esg_check_" + [guid]::NewGuid().ToString('N') + '.xlsx')
Copy-Item $source $copy

function Read-Cell($sheet, [string]$address) {
    $cell = $sheet.Range($address)
    return @{ value = $cell.Value2; text = $cell.Text }
}

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$result = [ordered]@{ path = $source; sheets = @(); peer_cases = @(); summary = @(); dqs = @() }
try {
    $wb = $excel.Workbooks.Open($copy)
    $excel.CalculateFull()

    foreach ($ws in $wb.Worksheets) {
        $formulas = 0; $errors = 0; $errorCells = @()
        try { $formulas = $ws.UsedRange.SpecialCells(-4123).Count } catch { $formulas = 0 }  # xlCellTypeFormulas
        try {
            $bad = $ws.UsedRange.SpecialCells(-4123, 16)  # formulas that return an error
            $errors = $bad.Count
            foreach ($c in $bad.Cells) { if ($errorCells.Count -lt 20) { $errorCells += ($c.Address(0, 0) + ' ' + $c.Text + ' ' + $c.Formula) } }
        } catch { $errors = 0 }
        $result.sheets += [ordered]@{ name = $ws.Name; formulas = $formulas; errors = $errors; error_cells = $errorCells }
    }

    $peer = $wb.Worksheets.Item('Peer Benchmark')
    if ($CasesJson) {
        $cases = Get-Content $CasesJson -Raw | ConvertFrom-Json
        foreach ($case in $cases) {
            $peer.Range('B4').Value2 = $case.company
            $peer.Range('B5').Value2 = $case.kpi
            $peer.Range('B6').Value2 = $case.year
            $excel.Calculate()
            $row = [ordered]@{ company = $case.company; kpi = $case.kpi; year = $case.year }
            foreach ($pair in @(@('ranking_group', 'B9'), @('value', 'B10'), @('n', 'B12'), @('ranked', 'B13'),
                                @('rank', 'B14'), @('percentile', 'B15'), @('median', 'B16'), @('median_n', 'B17'))) {
                $row[$pair[0]] = $peer.Range($pair[1]).Value2
            }
            $result.peer_cases += $row
        }
    }

    $years = @()
    $lists = $wb.Worksheets.Item('Lists')
    $r = 2
    while ($lists.Range("I$r").Value2) { $years += $lists.Range("I$r").Value2; $r++ }

    $summary = $wb.Worksheets.Item('Sector Summary')
    $dqs = $wb.Worksheets.Item('DQS view')
    $lastSummaryRow = $summary.Cells($summary.Rows.Count, 2).End(-4162).Row  # xlUp
    $lastSummaryCol = $summary.Cells(5, $summary.Columns.Count).End(-4159).Column  # xlToLeft
    $lastDqsRow = $dqs.Cells($dqs.Rows.Count, 1).End(-4162).Row
    foreach ($year in $years) {
        $summary.Range('B3').Value2 = $year
        $dqs.Range('B3').Value2 = $year
        $excel.Calculate()
        for ($row = 6; $row -le $lastSummaryRow; $row++) {
            $type = $summary.Cells($row, 1).Value2
            if (-not $type) { continue }
            for ($col = 3; $col -le $lastSummaryCol; $col++) {
                $result.summary += [ordered]@{
                    year = $year; group_type = $type; group_value = $summary.Cells($row, 2).Value2
                    header = $summary.Cells(5, $col).Value2; value = $summary.Cells($row, $col).Value2
                }
            }
        }
        for ($row = 7; $row -le $lastDqsRow; $row++) {
            $company = $dqs.Cells($row, 1).Value2
            if (-not $company -or $company -like 'Rank and*') { continue }
            $result.dqs += [ordered]@{
                year = $year; company = $company; dqs = $dqs.Cells($row, 2).Value2
                grade = $dqs.Cells($row, 3).Value2; rank = $dqs.Cells($row, 4).Value2
            }
        }
    }
    $wb.Close($false)
}
finally {
    $excel.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($excel)
    Remove-Item $copy -ErrorAction SilentlyContinue
}

$json = $result | ConvertTo-Json -Depth 6
if ($Out) { $json | Out-File -FilePath $Out -Encoding utf8 } else { $json }
