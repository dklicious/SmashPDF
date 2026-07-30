# SmashPDF

A local-first Windows tool that creates unrestricted and optionally compressed
copies of PDFs without changing the source files. Documents and passwords stay
on your computer.

## Download and run

Download `SmashPDF.exe` from the
[latest release](https://github.com/dklicious/SmashPDF/releases/latest), then
double-click it. No installation, Python runtime, account, or internet
connection is required.

Choose a processing option, then drag one or more PDFs into the drop box. You
can also click the box to browse. Each result is saved beside its source.

Processing options:

- **Unlock only** keeps the original image quality.
- Tick **Compress PDF after unlocking (keeps original quality)** to enable it.
- **Standard compression** usually makes suitable PDFs 5-30% smaller.
- **Maximum compression** usually makes suitable PDFs 10-40% smaller.

Compression does not resize or recompress images, rasterise pages, remove text,
or alter page geometry. Actual reduction depends on the PDF, and the app shows
the exact saving after processing.

Example:

`Contract.pdf` becomes `Contract_unlocked.pdf`,
`Contract_unlocked_compressed.pdf`, or
`Contract_unlocked_major_compressed.pdf`.

If that name already exists, the tool creates `Contract_unlocked (2).pdf`.

## What it handles

- PDFs that open normally but have printing, copying, or editing restrictions.
- PDFs that require an opening password, when you provide that password.
- Digital-signature and certification locks.
- Multiple PDFs in one batch.
- Existing non-signature form fields.

Visible digital-signature appearances are retained as stamp annotations.
Cryptographic signature verification cannot remain valid after a PDF is
unlocked, so keep the original signed PDF as the authoritative copy.

## Standalone executable

`SmashPDF.exe` is self-contained. It does not require Python, Codex, an
internet connection, or installation.

## Build and test from source

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m bandit -q -r smashpdf.py
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
.\build.ps1
```

## Command line

```powershell
python smashpdf.py "C:\path\document.pdf"
python smashpdf.py "C:\path\protected.pdf" --password "opening-password"
python smashpdf.py "C:\path\document.pdf" --output "C:\path\copy.pdf"
python smashpdf.py "C:\path\document.pdf" --compression standard
python smashpdf.py "C:\path\document.pdf" --compression major
```

Use `python smashpdf.py --help` for all options.

## Safety

- Processing is local; files and passwords are not uploaded.
- The source file is never overwritten.
- Output is written atomically and validated before delivery.
- A page-count check runs after every conversion.
- This tool does not bypass an unknown opening password.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and the security
model.

## About

SmashPDF is made by **dklicious**. Thank you for your support.

## Licence

[MIT](LICENSE)
