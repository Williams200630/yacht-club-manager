param([string]$OutputPath = "backups\yacht_club_manager_$(Get-Date -Format 'yyyyMMdd_HHmmss').dump")
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $OutputPath
if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
docker compose exec -T db pg_dump -U yacht_admin -d yacht_club_manager -Fc -f /tmp/yacht_club_manager.dump
docker compose cp db:/tmp/yacht_club_manager.dump $OutputPath
Write-Host "Backup written to $OutputPath"
