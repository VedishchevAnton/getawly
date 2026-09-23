# Starts a quick Cloudflare tunnel to local Getawly (nginx :8088).
# Copy the https://….trycloudflare.com URL into .env as BASE_URL, then:
#   docker compose up -d api

$ErrorActionPreference = "Stop"
$local = "http://localhost:8088"

$cf = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cf) {
    Write-Host "cloudflared not found."
    Write-Host "Install: winget install --id Cloudflare.cloudflared"
    Write-Host "Or download: https://github.com/cloudflare/cloudflared/releases"
    exit 1
}

Write-Host "Tunnel → $local"
Write-Host "When you see the https URL, put it in .env BASE_URL and restart api."
Write-Host ""
& cloudflared tunnel --url $local
