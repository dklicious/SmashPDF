$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = if (Get-Command py -ErrorAction SilentlyContinue) {
    "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    "python"
} else {
    throw "Python 3 was not found."
}

if (-not (Test-Path -LiteralPath ".venv-build")) {
    if ($python -eq "py") {
        & py -3 -m venv ".venv-build"
    } else {
        & python -m venv ".venv-build"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the build environment."
    }
}

$venvPython = Join-Path $PSScriptRoot ".venv-build\Scripts\python.exe"
& $venvPython -m pip install --require-hashes -r requirements-build.lock
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install hash-locked build dependencies."
}

& $venvPython -m scripts.generate_version_info build\version_info.txt
if ($LASTEXITCODE -ne 0) {
    throw "Failed to generate Windows version metadata."
}

& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "SmashPDF" `
    --icon "assets\smashpdf.ico" `
    --version-file "build\version_info.txt" `
    --add-data "assets\smashpdf_logo_64.png;assets" `
    --add-data "assets\smashpdf.ico;assets" `
    --collect-all tkinterdnd2 `
    smashpdf.py
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed to build SmashPDF.exe."
}

$version = & $venvPython -c "from _version import __version__; print(__version__)"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to read the canonical application version."
}
$versionInfo = (Get-Item -LiteralPath "dist\SmashPDF.exe").VersionInfo
if ($versionInfo.FileVersion -ne $version) {
    throw "Built file version $($versionInfo.FileVersion) does not match $version."
}

Write-Host "Built: $PSScriptRoot\dist\SmashPDF.exe"
