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
file, validated, and then published with atomic no-replace semantics unless the
caller explicitly enables overwrite.

SmashPDF does not bypass an unknown opening password. Removing a PDF's digital
signature or certification controls invalidates cryptographic verification, so
the original signed document should always be retained.

Lock mode uses AES-256 encryption, a user-selected opening password, and a
cryptographically random owner password that is not stored. The output is
reopened to verify its encryption integrity, password, page count, and denied
edit/copy/print permissions before publication. PDF permission flags depend on
reader compliance and are not irreversible DRM when the opening password is
known.

## Release integrity

Tagged releases require:

- a timestamped SHA-256 Authenticode signature;
- a published SHA-256 checksum;
- a CycloneDX SBOM;
- GitHub build-provenance and SBOM attestations; and
- dependencies installed from hash-locked requirement files.

Release tags are checked against the canonical application version before the
executable is built.
