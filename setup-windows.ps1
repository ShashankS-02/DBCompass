# DBCompass setup for Windows (PowerShell 5.1 or 7).
#
# Run from the project folder in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1          install everything, then offer to start
#   powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1 start    start the app without reinstalling
#
# Needs Python 3.11+ and Node.js 20+. If they are missing and winget is available, the script offers
# to install them. Runs locally with SQLite and the dev sign-in bypass: no Docker, no Azure.
param([string]$Command = "")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Venv = Join-Path $Backend ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
# Override if the ports are taken: $env:DBCOMPASS_BACKEND_PORT = "8010"; $env:DBCOMPASS_FRONTEND_PORT = "5180"
$BackendPort = if ($env:DBCOMPASS_BACKEND_PORT) { [int]$env:DBCOMPASS_BACKEND_PORT } else { 8000 }
$FrontendPort = if ($env:DBCOMPASS_FRONTEND_PORT) { [int]$env:DBCOMPASS_FRONTEND_PORT } else { 5173 }

function Write-Step($Text) { Write-Host ""; Write-Host $Text -ForegroundColor Cyan }
function Write-Ok($Text) { Write-Host "  [OK] $Text" -ForegroundColor Green }
function Write-Warn($Text) { Write-Host "  [!]  $Text" -ForegroundColor Yellow }
function Stop-WithError($Text) { Write-Host ""; Write-Host "[X] $Text" -ForegroundColor Red; exit 1 }
function Confirm-Yes($Question) {
    $reply = Read-Host "  $Question [Y/n]"
    return ($reply -eq "" -or $reply -match "^[Yy]")
}

function Update-PathFromRegistry {
    # winget installs update the registry PATH, not this session's PATH.
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

# ---------- prerequisites ----------

function Test-PythonCommand([string[]]$CommandLine) {
    try {
        $exe = $CommandLine[0]
        $rest = @()
        if ($CommandLine.Length -gt 1) { $rest = $CommandLine[1..($CommandLine.Length - 1)] }
        & $exe @rest -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-Python {
    # The py launcher first; plain "python" can be the Microsoft Store stub, which the version check rejects.
    $candidates = @("py -3.13", "py -3.12", "py -3.11", "py -3", "python")
    foreach ($text in $candidates) {
        $candidate = [string[]]($text -split " ")
        if (Get-Command $candidate[0] -ErrorAction SilentlyContinue) {
            if (Test-PythonCommand $candidate) { return ,$candidate }
        }
    }
    return $null
}

function Test-Node {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { return $false }
    if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { return $false }
    $major = [int]((node --version).TrimStart("v").Split(".")[0])
    return ($major -ge 20)
}

function Install-WithWinget($PackageId, $Label, $Url) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        if (Confirm-Yes "$Label is missing. Install it with winget now?") {
            winget install --id $PackageId --exact --silent --accept-package-agreements --accept-source-agreements
            Update-PathFromRegistry
            return
        }
    }
    Stop-WithError "$Label is required. Install it from $Url and run this script again."
}

function Test-Prerequisites {
    Write-Step "1/5  Checking Python and Node.js"
    $script:Python = Find-Python
    if ($null -eq $script:Python) {
        Install-WithWinget "Python.Python.3.12" "Python 3.11 or newer" "https://www.python.org/downloads/windows/"
        $script:Python = Find-Python
        if ($null -eq $script:Python) { Stop-WithError "Python 3.11+ still not found. Open a new PowerShell window and run the script again." }
    }
    $pyExe = $script:Python[0]
    $pyArgs = @()
    if ($script:Python.Length -gt 1) { $pyArgs = $script:Python[1..($script:Python.Length - 1)] }
    Write-Ok (& $pyExe @pyArgs --version)
    if (-not (Test-Node)) {
        Install-WithWinget "OpenJS.NodeJS.LTS" "Node.js 20 or newer" "https://nodejs.org/en/download"
        if (-not (Test-Node)) { Stop-WithError "Node.js 20+ still not found. Open a new PowerShell window and run the script again." }
    }
    Write-Ok "Node.js $(node --version), npm $(npm.cmd --version)"
}

# ---------- configuration ----------

function New-EnvFiles {
    Write-Step "2/5  Creating local settings"
    $envFile = Join-Path $Root ".env"
    if (Test-Path $envFile) { Write-Ok ".env already exists (kept as is)" }
    else {
        Copy-Item (Join-Path $Root ".env.example") $envFile
        Write-Ok "Created .env (local SQLite database, dev sign-in bypass)"
    }
    $frontendEnv = Join-Path $Frontend ".env.local"
    if (Test-Path $frontendEnv) { Write-Ok "frontend\.env.local already exists (kept as is)" }
    else {
        Copy-Item (Join-Path $Frontend ".env.example") $frontendEnv
        Write-Ok "Created frontend\.env.local"
    }
}

# ---------- install ----------

function Install-Backend {
    Write-Step "3/5  Installing the backend (Python packages)"
    if (-not (Test-Path $VenvPython)) {
        $pyExe = $script:Python[0]
        $pyArgs = @()
        if ($script:Python.Length -gt 1) { $pyArgs = $script:Python[1..($script:Python.Length - 1)] }
        & $pyExe @pyArgs -m venv $Venv
        if ($LASTEXITCODE -ne 0) { Stop-WithError "Could not create backend\.venv." }
        Write-Ok "Created backend\.venv"
    }
    & $VenvPython -m pip install --quiet --upgrade pip
    & $VenvPython -m pip install --quiet -r (Join-Path $Backend "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Stop-WithError "pip install failed. Behind a corporate proxy? See 'Quick setup' in README.md." }
    Write-Ok "Python packages installed"
}

function Install-Frontend {
    Write-Step "4/5  Installing the frontend (npm packages)"
    Push-Location $Frontend
    try {
        # npm.cmd, not npm.ps1: PowerShell would swallow "--" arguments passed to npm.ps1.
        npm.cmd ci --no-audit --no-fund --loglevel=error
        if ($LASTEXITCODE -ne 0) { Stop-WithError "npm install failed. Behind a corporate proxy? See 'Quick setup' in README.md." }
    } finally { Pop-Location }
    Write-Ok "npm packages installed"
}

function Test-KnowledgeBase {
    Write-Step "5/5  Checking the knowledge base"
    Push-Location $Backend
    try {
        & $VenvPython -m app.knowledge.check *> $null
        if ($LASTEXITCODE -eq 0) { Write-Ok "Knowledge base check passed" }
        else { Write-Warn "Knowledge base check reported problems. Run: cd backend; .venv\Scripts\python -m app.knowledge.check" }
    } finally { Pop-Location }
}

# ---------- start ----------

function Test-PortBusy($Port) {
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)
    } catch {
        return $false
    }
}

function Start-App {
    $uvicorn = Join-Path $Venv "Scripts\uvicorn.exe"
    if (-not (Test-Path $uvicorn)) { Stop-WithError "Not installed yet. Run setup-windows.ps1 first." }
    if (-not (Test-Path (Join-Path $Frontend "node_modules"))) { Stop-WithError "Frontend not installed yet. Run setup-windows.ps1 first." }
    foreach ($port in @($BackendPort, $FrontendPort)) {
        if (Test-PortBusy $port) { Stop-WithError "Port $port is already in use (another DBCompass or 'docker compose up'?). Stop it, or set `$env:DBCOMPASS_BACKEND_PORT / `$env:DBCOMPASS_FRONTEND_PORT to free ports." }
    }

    Write-Step "Starting DBCompass"
    $log = Join-Path $Backend "backend.log"
    $errLog = Join-Path $Backend "backend.err.log"
    $backendProcess = Start-Process -FilePath $uvicorn -ArgumentList "app.main:app", "--port", "$BackendPort" `
        -WorkingDirectory $Backend -WindowStyle Hidden -PassThru -RedirectStandardOutput $log -RedirectStandardError $errLog
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:$BackendPort/api/health" -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        } catch {
            if ($backendProcess.HasExited) { Stop-WithError "The backend stopped while starting. See backend\backend.err.log." }
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $ready) { Write-Warn "The backend is slow to start; the page may need a refresh. Log: backend\backend.err.log" }
    Write-Ok "Backend running on http://localhost:$BackendPort (log: backend\backend.err.log)"
    Start-Job -ScriptBlock { param($url) Start-Sleep -Seconds 3; Start-Process $url } -ArgumentList "http://localhost:$FrontendPort" | Out-Null
    Write-Ok "Opening http://localhost:$FrontendPort in your browser. Press Ctrl+C here to stop."

    Push-Location $Frontend
    $env:VITE_API_PROXY_TARGET = "http://localhost:$BackendPort"
    try {
        npm.cmd run dev -- --port $FrontendPort --strictPort
    } finally {
        Pop-Location
        Write-Host "Stopping DBCompass..."
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}

# ---------- main ----------

if ($Command -eq "start") {
    Start-App
    exit 0
}

Write-Host "DBCompass setup for Windows" -ForegroundColor White
Test-Prerequisites
New-EnvFiles
Install-Backend
Install-Frontend
Test-KnowledgeBase

Write-Step "Setup complete"
Write-Host "  Start the app any time with:"
Write-Host "    powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1 start"
if (Confirm-Yes "Start DBCompass now?") {
    Start-App
}
