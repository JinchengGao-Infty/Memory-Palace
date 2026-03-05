param(
    [ValidateSet('a', 'b', 'c', 'd', 'A', 'B', 'C', 'D')]
    [string]$Profile = 'b',

    [int]$FrontendPort = 0,

    [int]$BackendPort = 0,

    [switch]$NoAutoPort,

    [switch]$NoBuild,

    [switch]$AllowRuntimeEnvInjection
)

$ErrorActionPreference = 'Stop'
$script:PortProbeFallbackWarned = $false

function Test-PortInUse {
    param([int]$Port)

    if ($Port -lt 1 -or $Port -gt 65535) {
        throw "Invalid port: $Port"
    }

    try {
        $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
        return ($listeners.Count -gt 0)
    }
    catch {
        if (-not $script:PortProbeFallbackWarned) {
            Write-Warning "Port probe fallback engaged: Get-NetTCPConnection unavailable; fail-closed probing is enabled. detail=$($_.Exception.Message)"
            $script:PortProbeFallbackWarned = $true
        }
        # Fail-closed to avoid selecting potentially occupied ports when probe is unavailable.
        return $true
    }
}

function Resolve-FreePort {
    param(
        [int]$StartPort,
        [int]$MaxScan = 200
    )

    for ($i = 0; $i -le $MaxScan; $i++) {
        $candidate = $StartPort + $i
        if ($candidate -gt 65535) {
            break
        }
        if (-not (Test-PortInUse -Port $candidate)) {
            return $candidate
        }
    }

    throw "Failed to find free port near $StartPort"
}

function Assert-ValidPort {
    param(
        [int]$Port,
        [string]$Name
    )

    if ($Port -lt 1 -or $Port -gt 65535) {
        throw "$Name must be in range [1, 65535], got $Port"
    }
}

function Resolve-DataVolume {
    if ($env:MEMORY_PALACE_DATA_VOLUME) {
        return $env:MEMORY_PALACE_DATA_VOLUME
    }
    if ($env:NOCTURNE_DATA_VOLUME) {
        return $env:NOCTURNE_DATA_VOLUME
    }

    $newVolume = 'memory_palace_data'
    $projectSlug = (Split-Path -Leaf $projectRoot).ToLower() -replace '[^a-z0-9]', '_'
    $legacyCandidates = @(
        "${projectSlug}_nocturne_data",
        "${projectSlug}_nocturne_memory_data",
        'nocturne_data',
        'nocturne_memory_data'
    )

    docker volume inspect $newVolume 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        return $newVolume
    }

    foreach ($legacyVolume in $legacyCandidates) {
        docker volume inspect $legacyVolume 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            continue
        }

        if ($legacyVolume.StartsWith("${projectSlug}_")) {
            Write-Host "[compat] detected project-scoped legacy docker volume '$legacyVolume'; reusing it for data continuity."
            return $legacyVolume
        }

        $ownerLabel = docker volume inspect $legacyVolume --format '{{ index .Labels "com.docker.compose.project" }}' 2>$null
        if ($LASTEXITCODE -eq 0 -and $ownerLabel -eq $projectSlug) {
            Write-Host "[compat] detected legacy docker volume '$legacyVolume' owned by compose project '$ownerLabel'; reusing it for data continuity."
            return $legacyVolume
        }

        Write-Host "[compat] found legacy-like volume '$legacyVolume' but skipped auto-reuse (owner label mismatch). Set MEMORY_PALACE_DATA_VOLUME explicitly if this is the expected volume."
    }

    return $newVolume
}

function Get-EnvValueFromFile {
    param(
        [string]$FilePath,
        [string]$Key
    )

    if (-not (Test-Path $FilePath)) {
        return ''
    }

    $escaped = [regex]::Escape($Key)
    $line = Get-Content -Path $FilePath | Where-Object { $_ -match "^${escaped}=" } | Select-Object -Last 1
    if (-not $line) {
        return ''
    }
    return ($line -replace "^${escaped}=", '')
}

function Set-EnvValueInFile {
    param(
        [string]$FilePath,
        [string]$Key,
        [string]$Value
    )

    $lines = @()
    if (Test-Path $FilePath) {
        $lines = Get-Content -Path $FilePath
    }

    $escaped = [regex]::Escape($Key)
    $updated = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match "^${escaped}=") {
            if (-not $updated) {
                $updated = $true
                "$Key=$Value"
            }
        }
        else {
            $line
        }
    }

    if (-not $updated) {
        $newLines += "$Key=$Value"
    }

    Set-Content -Path $FilePath -Value $newLines
}

function Apply-ProfileRuntimeOverrides {
    param(
        [string]$EnvFile,
        [string]$SelectedProfile
    )

    $overrideKeys = @(
        'ROUTER_API_BASE',
        'ROUTER_API_KEY',
        'ROUTER_EMBEDDING_MODEL',
        'RETRIEVAL_EMBEDDING_BACKEND',
        'RETRIEVAL_EMBEDDING_API_BASE',
        'RETRIEVAL_EMBEDDING_API_KEY',
        'RETRIEVAL_EMBEDDING_MODEL',
        'RETRIEVAL_RERANKER_API_BASE',
        'RETRIEVAL_RERANKER_API_KEY',
        'RETRIEVAL_RERANKER_MODEL',
        'WRITE_GUARD_LLM_ENABLED',
        'WRITE_GUARD_LLM_API_BASE',
        'WRITE_GUARD_LLM_API_KEY',
        'WRITE_GUARD_LLM_MODEL',
        'COMPACT_GIST_LLM_ENABLED',
        'COMPACT_GIST_LLM_API_BASE',
        'COMPACT_GIST_LLM_API_KEY',
        'COMPACT_GIST_LLM_MODEL',
        'MCP_API_KEY',
        'MCP_API_KEY_ALLOW_INSECURE_LOCAL'
    )

    foreach ($key in $overrideKeys) {
        $overrideValue = [System.Environment]::GetEnvironmentVariable($key)
        if (-not [string]::IsNullOrWhiteSpace($overrideValue)) {
            Set-EnvValueInFile -FilePath $EnvFile -Key $key -Value $overrideValue
            Write-Host "[override] $key applied to $EnvFile"
        }
    }

    if ($SelectedProfile -in @('c', 'd')) {
        Set-EnvValueInFile -FilePath $EnvFile -Key 'RETRIEVAL_EMBEDDING_BACKEND' -Value 'api'
        Write-Host "[override] RETRIEVAL_EMBEDDING_BACKEND=api forced for local profile $SelectedProfile runtime injection."
    }
}

function Test-TruthyValue {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $false
    }
    $normalized = $Value.Trim().ToLower()
    return @('1', 'true', 'yes', 'on', 'enabled') -contains $normalized
}

function Test-UnresolvedPlaceholder {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $true
    }

    return (
        $Value.Contains('replace-with-your-key') -or
        $Value.Contains('<your-router-host>') -or
        $Value.Contains('host.docker.internal:PORT') -or
        ($Value -match ':PORT($|/)')
    )
}

function Assert-ProfileExternalSettingsReady {
    param(
        [string]$EnvFile,
        [string]$SelectedProfile
    )

    if ($SelectedProfile -notin @('c', 'd')) {
        return
    }

    $embeddingBackend = (Get-EnvValueFromFile -FilePath $EnvFile -Key 'RETRIEVAL_EMBEDDING_BACKEND').ToLower()
    $rerankerEnabled = Get-EnvValueFromFile -FilePath $EnvFile -Key 'RETRIEVAL_RERANKER_ENABLED'
    $requiredKeys = New-Object System.Collections.Generic.List[string]

    switch ($embeddingBackend) {
        'router' {
            $requiredKeys.Add('ROUTER_API_BASE')
            $requiredKeys.Add('ROUTER_API_KEY')
        }
        'api' {
            $requiredKeys.Add('RETRIEVAL_EMBEDDING_API_BASE')
            $requiredKeys.Add('RETRIEVAL_EMBEDDING_API_KEY')
        }
        'openai' {
            $requiredKeys.Add('RETRIEVAL_EMBEDDING_API_BASE')
            $requiredKeys.Add('RETRIEVAL_EMBEDDING_API_KEY')
        }
        'hash' { }
        'none' { }
        default {
            if (-not [string]::IsNullOrWhiteSpace($embeddingBackend)) {
                $requiredKeys.Add('RETRIEVAL_EMBEDDING_API_BASE')
                $requiredKeys.Add('RETRIEVAL_EMBEDDING_API_KEY')
            }
        }
    }

    if (Test-TruthyValue -Value $rerankerEnabled) {
        $requiredKeys.Add('RETRIEVAL_RERANKER_API_BASE')
        $requiredKeys.Add('RETRIEVAL_RERANKER_API_KEY')
    }

    $hasIssue = $false
    foreach ($key in $requiredKeys) {
        $value = Get-EnvValueFromFile -FilePath $EnvFile -Key $key
        if ([string]::IsNullOrWhiteSpace($value)) {
            Write-Error "[profile-check] Missing required value for $key ($SelectedProfile)"
            $hasIssue = $true
            continue
        }
        if (Test-UnresolvedPlaceholder -Value $value) {
            Write-Error "[profile-check] Unresolved placeholder for $key ($SelectedProfile): $value"
            $hasIssue = $true
        }
    }

    if ($hasIssue) {
        throw "Profile $SelectedProfile has unresolved external settings in $EnvFile"
    }
}

function Invoke-Compose {
    param([string[]]$ComposeArgs)

    $composeOutput = @()
    if ($script:UseComposePlugin) {
        $composeOutput = & docker compose @ComposeArgs 2>&1
    }
    else {
        $composeOutput = & docker-compose @ComposeArgs 2>&1
    }

    if ($composeOutput.Count -gt 0) {
        $composeOutput | ForEach-Object { Write-Output $_ }
    }

    if ($LASTEXITCODE -ne 0) {
        $detail = ($composeOutput | Out-String).Trim()
        throw "docker compose command failed: $($ComposeArgs -join ' ')`n$detail"
    }
}

function Test-ComposeRetryableError {
    param([string]$Message)

    if ([string]::IsNullOrWhiteSpace($Message)) {
        return $false
    }

    $patterns = @(
        'No such container',
        'dependency failed to start',
        'toomanyrequests',
        'TLS handshake timeout',
        'connection reset by peer',
        'i/o timeout',
        'context canceled',
        'EOF'
    )

    foreach ($pattern in $patterns) {
        if ($Message -like "*$pattern*") {
            return $true
        }
    }

    return $false
}

function Invoke-ComposeWithRetry {
    param(
        [string[]]$ComposeArgs,
        [int]$MaxAttempts = 3
    )

    $attempt = 0
    while ($attempt -lt $MaxAttempts) {
        $attempt += 1
        try {
            Invoke-Compose -ComposeArgs $ComposeArgs
            return
        }
        catch {
            $detail = $_.Exception.Message
            $retryable = Test-ComposeRetryableError -Message $detail
            if ($attempt -ge $MaxAttempts -or -not $retryable) {
                throw
            }

            $sleepSeconds = 2 * $attempt
            Write-Warning "[compose-retry] transient compose up failure ($attempt/$MaxAttempts), retrying in ${sleepSeconds}s."
            Start-Sleep -Seconds $sleepSeconds
            try {
                Invoke-Compose -ComposeArgs @('-f', 'docker-compose.yml', 'down', '--remove-orphans')
            }
            catch {
                # Keep retry path best-effort; next attempt will surface a hard failure.
            }
        }
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$profileLower = $Profile.ToLower()

if (-not $PSBoundParameters.ContainsKey('FrontendPort')) {
    if ($env:MEMORY_PALACE_FRONTEND_PORT) {
        $FrontendPort = [int]$env:MEMORY_PALACE_FRONTEND_PORT
    }
    elseif ($env:NOCTURNE_FRONTEND_PORT) {
        $FrontendPort = [int]$env:NOCTURNE_FRONTEND_PORT
    }
    else {
        $FrontendPort = 3000
    }
}

if (-not $PSBoundParameters.ContainsKey('BackendPort')) {
    if ($env:MEMORY_PALACE_BACKEND_PORT) {
        $BackendPort = [int]$env:MEMORY_PALACE_BACKEND_PORT
    }
    elseif ($env:NOCTURNE_BACKEND_PORT) {
        $BackendPort = [int]$env:NOCTURNE_BACKEND_PORT
    }
    else {
        $BackendPort = 18000
    }
}

Assert-ValidPort -Port $FrontendPort -Name 'FrontendPort'
Assert-ValidPort -Port $BackendPort -Name 'BackendPort'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "docker is not installed or not in PATH"
    exit 1
}

$script:UseComposePlugin = $false
try {
    docker compose version | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $script:UseComposePlugin = $true
    }
}
catch {
    $script:UseComposePlugin = $false
}

if (-not $script:UseComposePlugin -and -not (Get-Command docker-compose -ErrorAction SilentlyContinue)) {
    Write-Error "Neither 'docker compose' nor 'docker-compose' is available"
    exit 1
}

$envFile = Join-Path $projectRoot '.env.docker'
& (Join-Path $scriptDir 'apply_profile.ps1') -Platform docker -Profile $profileLower -Target $envFile
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
if ($AllowRuntimeEnvInjection.IsPresent) {
    Apply-ProfileRuntimeOverrides -EnvFile $envFile -SelectedProfile $profileLower
}
else {
    Write-Host "[override] runtime env injection disabled by default; pass -AllowRuntimeEnvInjection to opt in."
}
Assert-ProfileExternalSettingsReady -EnvFile $envFile -SelectedProfile $profileLower

Push-Location $projectRoot
try {
    try {
        Invoke-Compose @('-f', 'docker-compose.yml', 'down', '--remove-orphans')
    }
    catch {
        throw "[compose-down] pre-cleanup failed; aborting to match fail-closed deployment behavior. detail=$($_.Exception.Message)"
    }

    if (-not $NoAutoPort) {
        $resolvedFrontendPort = Resolve-FreePort -StartPort $FrontendPort
        $resolvedBackendPort = Resolve-FreePort -StartPort $BackendPort

        if ($resolvedFrontendPort -ne $FrontendPort) {
            Write-Host "[port-adjust] frontend $FrontendPort is occupied, switched to $resolvedFrontendPort"
        }
        if ($resolvedBackendPort -ne $BackendPort) {
            Write-Host "[port-adjust] backend $BackendPort is occupied, switched to $resolvedBackendPort"
        }
        if ($resolvedFrontendPort -eq $resolvedBackendPort) {
            $nextBackendPort = $resolvedBackendPort + 1
            try {
                $resolvedBackendPort = Resolve-FreePort -StartPort $nextBackendPort
            }
            catch {
                throw "Failed to auto-resolve free backend port near $nextBackendPort. Try -NoAutoPort with explicit values. detail=$($_.Exception.Message)"
            }
            Write-Host "[port-adjust] backend reassigned to avoid collision with frontend: $resolvedBackendPort"
        }

        $FrontendPort = $resolvedFrontendPort
        $BackendPort = $resolvedBackendPort
    }

    $dataVolume = Resolve-DataVolume
    $env:MEMORY_PALACE_FRONTEND_PORT = "$FrontendPort"
    $env:MEMORY_PALACE_BACKEND_PORT = "$BackendPort"
    $env:MEMORY_PALACE_DATA_VOLUME = "$dataVolume"
    $env:NOCTURNE_FRONTEND_PORT = "$FrontendPort"
    $env:NOCTURNE_BACKEND_PORT = "$BackendPort"
    $env:NOCTURNE_DATA_VOLUME = "$dataVolume"

    $composeUpArgs = @('-f', 'docker-compose.yml', 'up', '-d', '--force-recreate', '--remove-orphans')
    if (-not $NoBuild) {
        $composeUpArgs = @('-f', 'docker-compose.yml', 'up', '-d', '--build', '--force-recreate', '--remove-orphans')
    }
    Invoke-ComposeWithRetry -ComposeArgs $composeUpArgs -MaxAttempts 3
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Memory Palace is starting with docker profile $profileLower."
Write-Host "Frontend: http://localhost:$FrontendPort"
Write-Host "Backend API: http://localhost:$BackendPort"
Write-Host "Health: http://localhost:$BackendPort/health"
