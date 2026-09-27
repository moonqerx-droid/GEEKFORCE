$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    docker compose up -d --build

    $healthy = $false
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing
            if ($response.StatusCode -eq 200) {
                $healthy = $true
                break
            }
        } catch {
            if ($attempt -eq 40) { throw }
        }
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) {
        throw "API did not become healthy after 40 attempts"
    }

    $conversation = Invoke-RestMethod `
        -Method Post `
        -Uri "http://localhost:8000/api/conversations" `
        -ContentType "application/json"
    $body = @{ content = "Привет, не работает VPN" } | ConvertTo-Json -Compress
    $state = Invoke-RestMethod `
        -Method Post `
        -Uri "http://localhost:8000/api/conversations/$($conversation.id)/messages" `
        -ContentType "application/json" `
        -Body $body
    $assistantMessage = $state.messages | Where-Object {
        $_.role -eq "assistant" -and -not [string]::IsNullOrWhiteSpace($_.content)
    } | Select-Object -Last 1
    if ($null -eq $assistantMessage) {
        throw "Assistant response is empty"
    }

    Write-Host "P0 smoke passed for conversation $($conversation.id)"
    Write-Host "Frontend: http://localhost:5173/ (run: Set-Location apps/web; npm run dev)"
    Write-Host "Operator: http://localhost:5173/operator"
    Write-Host "Backend debug: http://localhost:8000/debug"
    Write-Host "Backend operator: http://localhost:8000/debug/operator"
} finally {
    Pop-Location
}
