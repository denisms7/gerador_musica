<#
.SYNOPSIS
    Exporta os certificados raiz confiaveis do Windows para um bundle PEM.
.DESCRIPTION
    Antivirus com varredura HTTPS e proxies corporativos reassinam o trafego TLS
    com um CA proprio. O Windows confia nele, mas o Python usa o bundle do
    `certifi`, que nao o conhece - dai o erro
    "CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain".

    Este script exporta a loja de raizes do Windows (que JA contem o CA do
    interceptador) para um PEM, e o start-backend.ps1 passa a usa-lo via
    SSL_CERT_FILE / REQUESTS_CA_BUNDLE.

    Isso mantem a verificacao de certificado ligada - ao contrario de desabilitar
    a verificacao, que deixa a conexao aberta a qualquer interceptacao.
.EXAMPLE
    .\scripts\export-ca-bundle.ps1
#>
param(
    [string]$OutFile
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutFile) { $OutFile = Join-Path $ProjectRoot "certs\windows-ca-bundle.pem" }

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutFile) | Out-Null

$builder = [System.Text.StringBuilder]::new()
$count = 0
$seen = @{}

foreach ($store in @("Cert:\LocalMachine\Root", "Cert:\CurrentUser\Root",
                     "Cert:\LocalMachine\CA", "Cert:\CurrentUser\CA")) {
    if (-not (Test-Path $store)) { continue }
    foreach ($cert in Get-ChildItem $store) {
        if ($seen.ContainsKey($cert.Thumbprint)) { continue }
        $seen[$cert.Thumbprint] = $true
        try {
            $b64 = [Convert]::ToBase64String($cert.RawData, 'InsertLineBreaks')
        } catch { continue }
        [void]$builder.AppendLine("# Subject: $($cert.Subject)")
        [void]$builder.AppendLine("-----BEGIN CERTIFICATE-----")
        [void]$builder.AppendLine($b64)
        [void]$builder.AppendLine("-----END CERTIFICATE-----")
        [void]$builder.AppendLine("")
        $count++
    }
}

# Anexa o bundle do certifi para nao perder as CAs publicas que o Windows nao tem
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    try {
        $certifiPath = & $venvPython -c "import certifi; print(certifi.where())" 2>$null
        if ($certifiPath -and (Test-Path $certifiPath)) {
            [void]$builder.AppendLine("# --- certifi ---")
            [void]$builder.AppendLine((Get-Content $certifiPath -Raw))
        }
    } catch { }
}

Set-Content -Path $OutFile -Value $builder.ToString() -Encoding ascii
Write-Host "Bundle gerado: $OutFile" -ForegroundColor Green
Write-Host "$count certificados da loja do Windows incluidos."
Write-Host ""
Write-Host "start-backend.ps1 usara este arquivo automaticamente." -ForegroundColor Cyan
