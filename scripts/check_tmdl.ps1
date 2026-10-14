<#
.SYNOPSIS
    Parse the generated TMDL with Power BI Desktop's own library and report what it finds.
.DESCRIPTION
    Week 12. Loads Microsoft.PowerBI.Tabular.dll from the installed Power BI Desktop and calls
    TmdlSerializer.DeserializeDatabaseFromFolder on each semantic model under powerbi/. A
    syntax or structure error in a table, measure, relationship or expression fails here, as
    it would when Power BI Desktop opens the project. DAX inside measures is not evaluated
    (that needs the engine): verify the numbers with docs/powerbi_reconciliation.md.
    Prints one JSON object per model. Windows with Power BI Desktop only.
#>
[CmdletBinding()]
param([string]$Root = '')
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = Join-Path (Split-Path -Parent $PSScriptRoot) 'powerbi' }

$package = Get-AppxPackage -Name Microsoft.MicrosoftPowerBIDesktop -ErrorAction SilentlyContinue
$bin = if ($package) { Join-Path $package.InstallLocation 'bin' } else { 'C:\Program Files\Microsoft Power BI Desktop\bin' }
$dll = Join-Path $bin 'Microsoft.PowerBI.Tabular.dll'
if (-not (Test-Path -LiteralPath $dll)) { throw "Power BI Desktop library not found: $dll" }
$assembly = [Reflection.Assembly]::LoadFrom($dll)
$serializer = $assembly.GetType('Microsoft.AnalysisServices.Tabular.TmdlSerializer')

$results = @()
foreach ($definition in Get-ChildItem -Path $Root -Recurse -Directory -Filter 'definition' | Where-Object { $_.Parent.Name -like '*.SemanticModel' }) {
    $entry = [ordered]@{ model = $definition.Parent.Name; ok = $false; version = $assembly.GetName().Version.ToString() }
    try {
        $database = $serializer::DeserializeDatabaseFromFolder($definition.FullName)
        $model = $database.Model
        $entry.ok = $true
        $entry.compatibility_level = $database.CompatibilityLevel
        $entry.tables = $model.Tables.Count
        $entry.columns = ($model.Tables | ForEach-Object { $_.Columns.Count } | Measure-Object -Sum).Sum
        $entry.measures = ($model.Tables | ForEach-Object { $_.Measures.Count } | Measure-Object -Sum).Sum
        $entry.relationships = $model.Relationships.Count
        $entry.expressions = $model.Expressions.Count
        $entry.measure_folders = @($model.Tables | ForEach-Object { $_.Measures } | ForEach-Object { $_.DisplayFolder } | Sort-Object -Unique)
        $entry.measures_without_description = @($model.Tables | ForEach-Object { $_.Measures } | Where-Object { -not $_.Description } | ForEach-Object { $_.Name })
        $entry.bidirectional = @($model.Relationships | Where-Object { $_.CrossFilteringBehavior -ne 'OneDirection' } | ForEach-Object { $_.Name })
    }
    catch {
        $inner = $_.Exception
        while ($inner.InnerException) { $inner = $inner.InnerException }
        $entry.error = $inner.Message
    }
    $results += $entry
}
$results | ConvertTo-Json -Depth 4
if ($results | Where-Object { -not $_.ok }) { exit 1 }
