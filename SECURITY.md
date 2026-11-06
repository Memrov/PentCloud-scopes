# Security policy

## Supported code and data

Security maintenance applies to the current `main` branch and the latest published `catalog` snapshot. Historical catalog commits remain available for reproduction; corrections are published in a later snapshot rather than backported to old revisions. The `catalog` branch advances by normal fast-forward pushes. A pinned commit identifies one snapshot, but does not make its policies current or authorize testing.

This repository has no published software releases. Version support for the PentCloud application and tool runtimes is documented in their own repositories.

## Report privately

[Report an importer vulnerability privately](https://github.com/Memrov/PentCloud-scopes/security/advisories/new) using GitHub's private vulnerability reporting. Do not post credentials, private program details, sensitive target information or exploit results in public issues or pull requests.

Include the affected code or catalog commit, expected and observed behavior, impact, and minimal reproduction steps using synthetic data. Redact secrets, personal information and target inventories from logs and screenshots. Do not scan a third-party target to demonstrate an importer issue. Response and fix times depend on maintainer availability.

Public data corrections that do not expose a vulnerability can use the [data correction form](https://github.com/Memrov/PentCloud-scopes/issues/new?template=data_correction.yml). Include only public policy references and sanitized examples. Platform policy changes and target vulnerabilities belong with the authoritative program's reporting process.

## Consumer responsibilities

This repository collects public program metadata from one configured source. It does not test targets, contact target hosts, import private programs or use bounty-platform API keys. A catalog entry is not authorization to test. Always review the current official program policy and participation requirements.

Catalog consumers must treat policy text, asset strings and links as untrusted data. Preserve exclusions and restrictions, escape content when rendering, and verify a consistent snapshot before using it. Scope enforcement belongs at the application's actual tool and network boundaries.

The manifest records upstream and publication timestamps, not a live platform verification time. No maximum source-age gate or artifact attestation is currently implemented; see [maintenance follow-ups](MAINTENANCE.md#trust-follow-ups). Report apparent integrity or publication-boundary failures privately.
