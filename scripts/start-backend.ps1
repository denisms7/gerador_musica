<#
.SYNOPSIS
    Sobe o servidor de inferencia ACE-Step na pasta correta.
.DESCRIPTION
    `uv run acestep-api` so funciona DENTRO do repositorio do ACE-Step. Rodado em
    C:\Projetos\musica ele falha com "program not found", porque ali o projeto e o
    musicgen. Este script le MUSICGEN_ACESTEP_HOME do .env, valida a pasta e roda
    o comando no lugar certo.
.EXAMPLE
    .\scripts\start-backend.ps1
    .\scripts\start-backend.ps1 -AceStepHome C:\Projetos\ACE-Step-1.5
#>
param(
    [string]$AceStepHome,
    [string]$DitModel,
    [string]$LmModel,
    [string]$CaBundle,
    [switch]$NoXet
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"

function Read-EnvValue([string]$Key) {
    if (-not (Test-Path $EnvFile)) { return $null }
    $line = Select-String -Path $EnvFile -Pattern "^\s*$Key\s*=\s*(.+)$" |
            Select-Object -Last 1
    if ($null -eq $line) { return $null }
    return $line.Matches[0].Groups[1].Value.Trim().Trim('"')
}

if (-not $AceStepHome) { $AceStepHome = Read-EnvValue "MUSICGEN_ACESTEP_HOME" }
if (-not $DitModel)    { $DitModel    = Read-EnvValue "MUSICGEN_DIT_MODEL" }
if (-not $LmModel)     { $LmModel     = Read-EnvValue "MUSICGEN_LM_MODEL" }

if (-not $AceStepHome) {
    Write-Host "MUSICGEN_ACESTEP_HOME nao definido." -ForegroundColor Red
    if (-not (Test-Path $EnvFile)) {
        Write-Host "O arquivo .env nem existe ainda. Rode a instalacao primeiro:"
        Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1" -ForegroundColor Yellow
    } else {
        Write-Host "Preencha MUSICGEN_ACESTEP_HOME no .env, ou passe -AceStepHome."
    }
    exit 1
}

$AceStepHome = $AceStepHome -replace '/', '\'
if (-not (Test-Path $AceStepHome)) {
    Write-Host "Pasta do ACE-Step nao encontrada: $AceStepHome" -ForegroundColor Red
    Write-Host "Rode scripts\setup.ps1 para clonar o backend." -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path (Join-Path $AceStepHome "pyproject.toml"))) {
    Write-Host "$AceStepHome nao parece o repositorio do ACE-Step." -ForegroundColor Red
    exit 1
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "'uv' nao esta no PATH. Instale: https://astral.sh/uv" -ForegroundColor Red
    exit 1
}

if ($DitModel) { $env:ACESTEP_CONFIG_PATH   = $DitModel }
if ($LmModel)  { $env:ACESTEP_LM_MODEL_PATH = $LmModel }

# VIRTUAL_ENV do venv do app faz o uv emitir warning e pode confundir a resolucao
# do ambiente do ACE-Step. Limpar e o comportamento correto aqui.
$env:VIRTUAL_ENV = $null

# TLS: antivirus com varredura HTTPS e proxies reassinam o trafego com um CA
# proprio que o Windows confia mas o certifi do Python nao, o que quebra o
# download dos pesos com CERTIFICATE_VERIFY_FAILED. Apontar para um bundle que
# inclua esse CA resolve mantendo a verificacao ligada.
if (-not $CaBundle) {
    $default = Join-Path $ProjectRoot "certs\windows-ca-bundle.pem"
    if (Test-Path $default) { $CaBundle = $default }
}
if ($CaBundle) {
    if (-not (Test-Path $CaBundle)) {
        Write-Host "CA bundle nao encontrado: $CaBundle" -ForegroundColor Red
        exit 1
    }
    $env:SSL_CERT_FILE       = $CaBundle
    $env:REQUESTS_CA_BUNDLE  = $CaBundle
    $env:CURL_CA_BUNDLE      = $CaBundle
}

# O CDN Xet (us.aws.cdn.hf.co) e o que mais sofre com inspecao TLS; o download
# HTTP comum do Hub e mais lento porem mais tolerante.
if ($NoXet) { $env:HF_HUB_DISABLE_XET = "1" }
if (-not $env:HF_HUB_DOWNLOAD_TIMEOUT) { $env:HF_HUB_DOWNLOAD_TIMEOUT = "60" }

function Show-Value($v) { if ([string]::IsNullOrWhiteSpace($v)) { "(default do ACE-Step)" } else { $v } }

Write-Host "Backend : $AceStepHome"      -ForegroundColor Cyan
Write-Host "DiT     : $(Show-Value $DitModel)"
Write-Host "LM      : $(Show-Value $LmModel)"
Write-Host "CA      : $(Show-Value $CaBundle)"
Write-Host "Xet     : $(if ($NoXet) { 'desativado' } else { 'ativo' })"
Write-Host ""
Write-Host "No primeiro start os pesos sao baixados (varios GB) ANTES de a porta abrir." -ForegroundColor Yellow
Write-Host "Deixe esta janela aberta; a UI so conecta quando o servidor responder." -ForegroundColor Yellow
Write-Host ""

Push-Location $AceStepHome
try { uv run acestep-api } finally { Pop-Location }
