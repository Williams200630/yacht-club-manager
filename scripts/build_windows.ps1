param(
    [string]$BasePython,
    [switch]$UseLocalSettings
)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$venv = Join-Path $project '.venv-build'
$python = Join-Path $venv 'Scripts\python.exe'
$runId = '{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
$work = Join-Path $project "build\windows\$runId"
$output = Join-Path $project "dist\$runId"
$bundle = Join-Path $output 'YachtClubManager'
$archive = Join-Path $output 'YachtClubManager-windows.zip'

Push-Location -LiteralPath $project
try {
    if (-not (Test-Path -LiteralPath $python)) {
        if ($BasePython) {
            & $BasePython -m venv $venv
        } else {
            & py -3.11 -m venv $venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create the build environment.' }
    }

    & $python -m pip install --disable-pip-version-check -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install build dependencies.' }

    New-Item -ItemType Directory -Path $work, $output -Force | Out-Null
    & $python -m PyInstaller --name YachtClubManager --onedir --windowed --noupx `
        --specpath $work --workpath $work --distpath $output `
        --collect-all psycopg_binary --copy-metadata psycopg `
        main.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed to build YachtClubManager.exe.' }

    # Qt uses the ICU supplied by Windows. A DLL found on the build machine's PATH can shadow it.
    $bundledIcu = Join-Path $bundle '_internal\icuuc.dll'
    if (Test-Path -LiteralPath $bundledIcu -PathType Leaf) {
        Remove-Item -LiteralPath $bundledIcu
    }

    $bundleAssets = Join-Path $bundle 'assets'
    New-Item -ItemType Directory -Path $bundleAssets | Out-Null
    Copy-Item -LiteralPath 'assets\hero-yacht.png' -Destination $bundleAssets
    Copy-Item -LiteralPath 'assets\boats' -Destination $bundleAssets -Recurse
    Copy-Item -LiteralPath 'sql' -Destination $bundle -Recurse
    Copy-Item -LiteralPath '.env.example', 'docker-compose.yml' -Destination $bundle

    @'
Yacht Club Manager for Windows

1. Extract the entire ZIP into a folder you can write to.
2. Start Docker Desktop and wait for the engine to be ready.
3. Run YachtClubManager.exe from the extracted folder.

Python and Qt are included. PostgreSQL runs in Docker.
At first startup the app creates a local .env from the example.
The app uses the local Docker volume for PostgreSQL data.
'@ | Set-Content -LiteralPath (Join-Path $bundle 'START.txt') -Encoding UTF8

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $bundle, $archive, [System.IO.Compression.CompressionLevel]::Optimal, $true
    )
    if ($UseLocalSettings -and (Test-Path -LiteralPath '.env' -PathType Leaf)) {
        Copy-Item -LiteralPath '.env' -Destination $bundle
        Write-Host 'The unpacked build uses your existing local database settings. The ZIP uses the example only.'
    }
    Write-Host "Executable: $(Join-Path $bundle 'YachtClubManager.exe')"
    Write-Host "Release ZIP: $archive"
} finally {
    Pop-Location
}
