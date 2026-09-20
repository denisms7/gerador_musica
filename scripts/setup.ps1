<#
.SYNOPSIS
    Prepara o ambiente do MusicGen no Windows: venv do app + clone e sync do ACE-Step 1.5.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -AceStepHome C:\Projetos\ACE-Step-1.5
#>
param(
    [string]$AceStepHome = "C:\Projetos\ACE-Step-1.5"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "== 1/5 Verificando uv ==" -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Instalando uv..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "== 2/5 Ambiente do app ==" -ForegroundColor Cyan
Push-Location $ProjectRoot
# --python 3.11: evita o CPython do Microsoft Store (WindowsApps), que e sandboxed
# e causa problemas com venvs; o uv baixa e gerencia a versao se ela nao existir.
if (-not (Test-Path ".venv")) { uv venv .venv --python 3.11 }
# -e . usa pyproject.toml (fonte canonica) e instala o comando `musicgen`.
# Alternativa com pip puro: uv pip install -r requirements.txt
uv pip install --python .venv\Scripts\python.exe -e .
Pop-Location

Write-Host "== 3/5 ACE-Step 1.5 ==" -ForegroundColor Cyan
if (-not (Test-Path $AceStepHome)) {
    git clone https://github.com/ACE-Step/ACE-Step-1.5.git $AceStepHome
}
Push-Location $AceStepHome
uv sync
Pop-Location

Write-Host "== 4/5 Arquivo .env ==" -ForegroundColor Cyan
$envFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $ProjectRoot ".env.example") $envFile
    (Get-Content $envFile) -replace '^MUSICGEN_ACESTEP_HOME=.*', `
        "MUSICGEN_ACESTEP_HOME=$($AceStepHome -replace '\\','/')" | Set-Content $envFile
    Write-Host "Criado $envFile"
} else {
    Write-Host ".env ja existe; nao foi sobrescrito."
}

Write-Host "== 5/5 Diagnostico ==" -ForegroundColor Cyan
& "$ProjectRoot\.venv\Scripts\python.exe" "$ProjectRoot\scripts\diagnose.py"

Write-Host "`nPronto. Para usar (duas janelas):" -ForegroundColor Green
Write-Host "  1) Servidor de inferencia:  .\scripts\start-backend.ps1"
Write-Host "  2) Aplicacao:               .\scripts\run.ps1"
Write-Host ""
Write-Host "NAO rode 'uv run acestep-api' dentro de C:\Projetos\musica - esse comando" -ForegroundColor Yellow
Write-Host "so existe no repositorio do ACE-Step. start-backend.ps1 cuida da pasta." -ForegroundColor Yellow
