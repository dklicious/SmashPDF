# Security Policy

## Supported version

Security fixes are applied to the latest published version of SmashPDF.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use the
repository's **Security** tab to submit a private vulnerability report.

Include:

- the affected SmashPDF version;
- the PDF characteristics needed to reproduce the issue;
- the security impact;
- minimal reproduction steps; and
- any suggested mitigation.

Do not include confidential documents, passwords, private keys, or personal
information. Acknowledgement should be sent within seven days.

## Security model

SmashPDF runs locally and does not upload PDFs, passwords, or document contents.
Source files are never overwritten. Outputs are written through a temporary
file, validated, and then moved into place.

SmashPDF does not bypass an unknown opening password. Removing a PDF's digital
signature or certification controls invalidates cryptographic verification, so
the original signed document should always be retained.
