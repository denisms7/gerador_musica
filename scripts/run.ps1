<#
.SYNOPSIS
    Sobe a aplicacao Streamlit.
.DESCRIPTION
    Por padrao, se a porta ja estiver ocupada por uma instancia anterior do app,
    derruba essa instancia e sobe de novo. Isso e o comportamento desejado quase
    sempre: o Streamlit mantem modulos em sys.modules e objetos em
    st.cache_resource, entao depois de uma alteracao no codigo um "Rerun" nao
    basta - so um processo novo carrega o codigo novo.

    Use -NoRestart para recusar-se a matar o processo existente.
.EXAMPLE
    .\scripts\run.ps1
    .\scripts\run.ps1 -Port 8502 -NoRestart
#>
param(
    [int]$Port = 8501,
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

# Alcance deliberadamente estreito: so instancias deste app. O servidor de
# inferencia roda noutro processo e nunca deve ser tocado por este script.
$running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like '*streamlit*app.py*' })

if ($running.Count -gt 0) {
    if ($NoRestart) {
        Write-Host "Ja existe uma instancia do app rodando (PID $($running.ProcessId -join ', '))." -ForegroundColor Yellow
        Write-Host "Rode sem -NoRestart para reinicia-la, ou escolha outra porta com -Port." -ForegroundColor Yellow
        exit 1
    }
    foreach ($proc in $running) {
        Write-Host "Encerrando instancia anterior (PID $($proc.ProcessId))..." -ForegroundColor Yellow
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 1200
}

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Venv nao encontrado em $python" -ForegroundColor Red
    Write-Host "Rode: powershell -ExecutionPolicy Bypass -File scripts\setup.ps1" -ForegroundColor Yellow
    exit 1
}

Push-Location $ProjectRoot
try { & $python -m streamlit run app.py --server.port $Port } finally { Pop-Location }
