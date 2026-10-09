<#
.SYNOPSIS
    Windows equivalent of the Makefile targets.
.EXAMPLE
    .\scripts\dev.ps1 test
    .\scripts\dev.ps1 build
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'lint', 'test', 'intake', 'todo', 'parse', 'load', 'build', 'dbt-build', 'dbt-docs', 'app')]
    [string]$Task = 'help'
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$Py = Join-Path $Venv 'Scripts\python.exe'
$Dbt = Join-Path $Venv 'Scripts\dbt.exe'
$DbtDir = Join-Path $Root 'dbt'
# dbt staging views read the Parquet/CSV files at query time, so give dbt an ABSOLUTE data path;
# a relative one would only resolve when the warehouse is queried from dbt/.
if (-not $env:ESG_DATA_DIR) { $env:ESG_DATA_DIR = (Join-Path $Root 'data') -replace '\\', '/' }

function Invoke-Step {
    param([string]$Exe, [string[]]$Arguments)
    Write-Host "> $Exe $($Arguments -join ' ')" -ForegroundColor Cyan
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}

function Assert-Venv {
    if (-not (Test-Path $Py)) { throw "No .venv found. Run: .\scripts\dev.ps1 setup" }
}

Push-Location $Root
try {
    switch ($Task) {
        'help' {
            Write-Host 'Usage: .\scripts\dev.ps1 <setup|lint|test|intake|todo|parse|load|dbt-build|dbt-docs|app>'
        }
        'setup' {
            if (-not (Test-Path $Py)) { Invoke-Step 'py' @('-3.12', '-m', 'venv', $Venv) }
            Invoke-Step $Py @('-m', 'pip', 'install', '--upgrade', 'pip')
            Invoke-Step $Py @('-m', 'pip', 'install', '-r', 'requirements-dev.txt')
            Invoke-Step $Py @('-m', 'pre_commit', 'install')
            if (-not (Test-Path (Join-Path $Root '.env'))) { Copy-Item '.env.example' '.env' }
            Push-Location $DbtDir
            try { Invoke-Step $Dbt @('deps', '--profiles-dir', '.') } finally { Pop-Location }
        }
        'lint' {
            Assert-Venv
            Invoke-Step $Py @('-m', 'ruff', 'check', '.')
            Invoke-Step $Py @('-m', 'ruff', 'format', '--check', '.')
            Invoke-Step $Py @('-m', 'sqlfluff', 'lint', 'dbt/models', 'dbt/tests', 'dbt/analyses', 'dbt/macros')
        }
        'test' {
            Assert-Venv
            Invoke-Step $Py @('-m', 'pytest', '-q')
        }
        'intake' {
            # Files are downloaded from NSE by hand (docs/how_to_add_filings.md); nothing here fetches data.
            Assert-Venv
            Invoke-Step $Py @('-m', 'ingestion.discover')
            Invoke-Step $Py @('-m', 'ingestion.taxonomy')
            Invoke-Step $Py @('-m', 'ingestion.intake')
        }
        'todo' {
            Assert-Venv
            Invoke-Step $Py @('-m', 'ingestion.todo')
        }
        'parse' {
            Assert-Venv
            Invoke-Step $Py @('-m', 'ingestion.parse_xbrl')
        }
        'load' {
            Assert-Venv
            Invoke-Step $Py @('-m', 'ingestion.load_raw')
        }
        { $_ -in 'build', 'dbt-build' } {
            Assert-Venv
            Push-Location $DbtDir
            try {
                Invoke-Step $Dbt @('deps', '--profiles-dir', '.')
                Invoke-Step $Dbt @('build', '--profiles-dir', '.')
            } finally { Pop-Location }
        }
        'dbt-docs' {
            Assert-Venv
            Push-Location $DbtDir
            try {
                Invoke-Step $Dbt @('docs', 'generate', '--profiles-dir', '.')
                Invoke-Step $Dbt @('docs', 'serve', '--profiles-dir', '.')
            } finally { Pop-Location }
        }
        'app' {
            Assert-Venv
            Invoke-Step $Py @('-m', 'streamlit', 'run', 'app/streamlit_app.py')
        }
    }
}
finally {
    Pop-Location
}
