param(
    [ValidateSet('macos', 'windows', 'docker')]
    [string]$Platform = 'windows',

    [ValidateSet('a', 'b', 'c', 'd', 'A', 'B', 'C', 'D')]
    [string]$Profile = 'b',

    [string]$Target = ''
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$profileLower = $Profile.ToLower()

if ([string]::IsNullOrWhiteSpace($Target)) {
    $Target = Join-Path $projectRoot '.env'
}

$baseEnv = Join-Path $projectRoot '.env.example'
$overrideEnv = Join-Path $projectRoot ("deploy/profiles/{0}/profile-{1}.env" -f $Platform, $profileLower)

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

function Dedupe-DatabaseUrl {
    param([string]$FilePath)

    if (-not (Test-Path $FilePath)) {
        return
    }

    $lastLine = Get-Content -Path $FilePath | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -Last 1
    if (-not $lastLine) {
        return
    }

    $value = $lastLine -replace '^DATABASE_URL=', ''
    Set-EnvValueInFile -FilePath $FilePath -Key 'DATABASE_URL' -Value $value
}

if (-not (Test-Path $baseEnv)) {
    Write-Error "Missing base env template: $baseEnv"
    exit 1
}

if (-not (Test-Path $overrideEnv)) {
    Write-Error "Missing profile template: $overrideEnv"
    exit 1
}

Copy-Item -Path $baseEnv -Destination $Target -Force
Add-Content -Path $Target -Value ""
Add-Content -Path $Target -Value "# -----------------------------------------------------------------------------"
Add-Content -Path $Target -Value "# Appended profile overrides ($Platform/profile-$profileLower)"
Add-Content -Path $Target -Value "# -----------------------------------------------------------------------------"
Get-Content -Path $overrideEnv | Add-Content -Path $Target

if ($Platform -eq 'macos') {
    $placeholder = 'DATABASE_URL=sqlite+aiosqlite:////Users/<your-user>/memory_palace/agent_memory.db'
    if (Select-String -Path $Target -Pattern ([regex]::Escape($placeholder)) -Quiet) {
        $dbPath = (Join-Path $projectRoot 'demo.db') -replace '\\', '/'
        $dbUrl = 'DATABASE_URL=sqlite+aiosqlite:////' + $dbPath.TrimStart('/')
        Set-EnvValueInFile -FilePath $Target -Key 'DATABASE_URL' -Value $dbUrl.Substring('DATABASE_URL='.Length)
        Write-Host "[auto-fill] DATABASE_URL set to $dbPath"
    }
}

if ($Platform -eq 'windows') {
    $placeholder = 'DATABASE_URL=sqlite+aiosqlite:///C:/memory_palace/agent_memory.db'
    if (Select-String -Path $Target -Pattern ([regex]::Escape($placeholder)) -Quiet) {
        $dbPath = (Join-Path $projectRoot 'demo.db') -replace '\\', '/'
        if ($dbPath -match '^/([a-zA-Z])/(.*)$') {
            $drive = $Matches[1].ToUpperInvariant()
            $dbPath = "${drive}:/$($Matches[2])"
        }
        elseif ($dbPath -match '^/mnt/([a-zA-Z])/(.*)$') {
            $drive = $Matches[1].ToUpperInvariant()
            $dbPath = "${drive}:/$($Matches[2])"
        }
        elseif ($dbPath -notmatch '^[A-Za-z]:/') {
            $dbPath = 'C:/memory_palace/demo.db'
        }
        $dbUrl = 'DATABASE_URL=sqlite+aiosqlite:///' + $dbPath
        Set-EnvValueInFile -FilePath $Target -Key 'DATABASE_URL' -Value $dbUrl.Substring('DATABASE_URL='.Length)
        Write-Host "[auto-fill] DATABASE_URL set to $dbPath"
    }
}

Dedupe-DatabaseUrl -FilePath $Target

Write-Host "Generated $Target from $overrideEnv"
