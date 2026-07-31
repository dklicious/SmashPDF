param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [string]$CertificateBase64 = $env:WINDOWS_CERTIFICATE,
    [string]$CertificatePassword = $env:WINDOWS_CERTIFICATE_PASSWORD,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($CertificateBase64)) {
    throw "WINDOWS_CERTIFICATE is required for tagged releases."
}
if ([string]::IsNullOrWhiteSpace($CertificatePassword)) {
    throw "WINDOWS_CERTIFICATE_PASSWORD is required for tagged releases."
}

$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
$certificatePath = Join-Path ([System.IO.Path]::GetTempPath()) (
    "smashpdf-signing-{0}.pfx" -f [System.Guid]::NewGuid().ToString("N")
)
$certificate = $null
$importedCertificates = @()

try {
    [System.IO.File]::WriteAllBytes(
        $certificatePath,
        [System.Convert]::FromBase64String($CertificateBase64)
    )
    $securePassword = ConvertTo-SecureString `
        -String $CertificatePassword `
        -AsPlainText `
        -Force
    $importedCertificates = @(
        Import-PfxCertificate `
            -FilePath $certificatePath `
            -CertStoreLocation "Cert:\CurrentUser\My" `
            -Password $securePassword
    )
    $certificate = $importedCertificates |
        Where-Object { $_.HasPrivateKey } |
        Select-Object -First 1

    if (-not $certificate) {
        throw "The supplied signing certificate does not contain a private key."
    }

    $signTool = Get-ChildItem `
        -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" `
        -File |
        Sort-Object -Property FullName -Descending |
        Select-Object -First 1
    if (-not $signTool) {
        throw "SignTool.exe was not found on the Windows build runner."
    }

    & $signTool.FullName sign `
        /fd SHA256 `
        /sha1 $certificate.Thumbprint `
        /s My `
        /tr $TimestampUrl `
        /td SHA256 `
        $resolvedExecutable
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool failed with exit code $LASTEXITCODE."
    }

    & $signTool.FullName verify /pa /all /v $resolvedExecutable
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode verification failed with exit code $LASTEXITCODE."
    }
}
finally {
    foreach ($importedCertificate in $importedCertificates) {
        Remove-Item `
            -LiteralPath "Cert:\CurrentUser\My\$($importedCertificate.Thumbprint)" `
            -Force `
            -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $certificatePath `
        -Force `
        -ErrorAction SilentlyContinue
}
