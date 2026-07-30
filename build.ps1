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
}

$venvPython = Join-Path $PSScriptRoot ".venv-build\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt pyinstaller==6.21.0
& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name "SmashPDF" `
    --icon "assets\smashpdf.ico" `
    --add-data "assets\smashpdf_logo_64.png;assets" `
    --add-data "assets\smashpdf.ico;assets" `
    --collect-all tkinterdnd2 `
    smashpdf.py

Write-Host "Built: $PSScriptRoot\dist\SmashPDF.exe"
