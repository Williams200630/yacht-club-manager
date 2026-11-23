param([Parameter(Mandatory=$true)][string]$InputPath)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) { throw "Backup file not found: $InputPath" }
$containerPath='/tmp/yacht_club_restore.dump'
docker compose cp $InputPath "db:$containerPath"
docker compose exec -T db pg_restore --clean --if-exists --no-owner -U yacht_admin -d yacht_club_manager $containerPath
Write-Host "Restore completed from $InputPath"
