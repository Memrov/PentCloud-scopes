# PentCloud Scopes

[![CI](https://github.com/Memrov/PentCloud-scopes/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Memrov/PentCloud-scopes/actions/workflows/ci.yml?query=branch%3Amain)
[![CodeQL](https://github.com/Memrov/PentCloud-scopes/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/Memrov/PentCloud-scopes/actions/workflows/codeql.yml?query=branch%3Amain)
[![Catalog sync](https://github.com/Memrov/PentCloud-scopes/actions/workflows/sync.yml/badge.svg?branch=main)](https://github.com/Memrov/PentCloud-scopes/actions/workflows/sync.yml?query=branch%3Amain)
[![License: MIT](https://img.shields.io/github/license/Memrov/PentCloud-scopes)](LICENSE)
[![Report a vulnerability privately](https://img.shields.io/badge/security-report%20privately-blue)](https://github.com/Memrov/PentCloud-scopes/security/advisories/new)

Badges link to workflow results, the license and the private reporting channel. Read the [security policy](SECURITY.md) for support and reporting guidance.

A public bug bounty program catalog for finding programs and reviewing their published targets. Scope stays attached to its program, including exclusions, asset types, instructions and source metadata.

The catalog imports public JSON from [arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data) for **HackerOne, Bugcrowd, Intigriti and YesWeHack**. That project maintains the platform collectors. This repository maintains a stable format, validation and publication. It downloads data without running upstream code or using platform credentials.

**Discovery data is not authorization to test.** Check the current official program policy, participation requirements and automation rules before testing. Inclusion does not guarantee that a program is open, that you are eligible, that every activity is permitted, or that a bounty will be paid. This catalog does not start assessments or enforce network scope.

This repository operates independently of [PentCloud](https://github.com/Memrov/PentCloud). It is not connected to the application or its deployment pipeline.

## Ecosystem trust map

| Repository | What to verify |
| --- | --- |
| [PentCloud](https://github.com/Memrov/PentCloud) | Application behavior, authorization and deployment controls; its [security policy](https://github.com/Memrov/PentCloud/blob/main/SECURITY.md). |
| [PentCloud tools](https://github.com/Memrov/PentCloud-tools) | Versioned tool runtimes, upstream binary checksums and licenses; its [security policy](https://github.com/Memrov/PentCloud-tools/blob/main/SECURITY.md). |
| PentCloud Scopes | Public discovery data, source revision, validation and snapshot checksums; this repository's [security policy](SECURITY.md). |

The repositories have separate release and maintenance boundaries. A passing check here does not validate another repository or authorize testing a listed target.

## Browse the data

Generated files live on the [`catalog` branch](https://github.com/Memrov/PentCloud-scopes/tree/catalog):

- [`manifest.json`](https://github.com/Memrov/PentCloud-scopes/blob/catalog/manifest.json): source revision, publication time, counts and file checksums.
- [`index.json`](https://github.com/Memrov/PentCloud-scopes/blob/catalog/index.json): compact program summaries and record paths.
- `programs/<platform>/<stable-key>.json`: complete individual records.
- [`changes.json`](https://github.com/Memrov/PentCloud-scopes/blob/catalog/changes.json): additions, updates and records absent from the preceding published snapshot.

For a consistent download, resolve the catalog branch to a commit and fetch every file from that commit. Verify each file against the manifest. Reading moving branch URLs independently can mix revisions.

The main branch holds the importer, schema, tests and documentation. Automated data updates never change main or release application code.

## How updates work

An hourly GitHub Actions job, scheduled at minute 17, reads all four feeds from one immutable upstream commit. It validates inputs, builds a complete snapshot and verifies every published record before pushing the catalog branch. It creates no commit when the catalog content is unchanged.

Failed, empty, malformed or incomplete feeds do not replace the previous catalog. Large program removals or scope reductions stop publication for review. Removed programs are omitted from the new index and recorded in `changes.json`; absence means removed from this source snapshot, not necessarily closed by the platform.

Schedules may be delayed, and public repository schedules can be disabled after 60 days of inactivity. The [Actions history](https://github.com/Memrov/PentCloud-scopes/actions/workflows/sync.yml) shows completed checks and failures. A green sync badge reports the last run's result; it does not prove that the catalog is fresh, that another run will happen, or that a live platform policy was checked. Check the run time and manifest timestamps separately.

## Provenance and limitations

Every program retains its source record hash, original metadata and raw asset fields. The manifest pins the upstream commit for the whole snapshot. Unknown asset types remain data; they are not converted into runnable URLs. Paths, `www`, wildcards and free-text exclusions are preserved.

`source_status` preserves the available source field and value. Missing status remains unknown; a YesWeHack `disabled: false` value does not prove testing permission. Bounty eligibility is separate from submission eligibility.

`published_at` and `source.fetched_at` describe the published snapshot. `source.committed_at` describes the upstream commit. These are **not** the time the platform verified its policy. `provider_verified_at` is always `null`. An unchanged catalog retains its original publication time; consult Actions for the last successful import check.

Upstream data may lag the platform, omit policy text or contain errors. This repository cannot guarantee freshness or completeness. Private programs, invitations and user API connections are not collected. Upstream attribution is retained in [LICENSES/upstream-MIT.txt](LICENSES/upstream-MIT.txt).

GitHub's [dependency graph and Export SBOM control](https://github.com/Memrov/PentCloud-scopes/network/dependencies) describe recognized source and workflow dependencies. The importer uses Python's standard library. That SBOM does not inventory the upstream catalog, program targets or scanner binaries from other repositories. Snapshot checksums detect byte changes relative to a manifest; they are not build attestations or proof that a program permits testing. See [maintenance follow-ups](MAINTENANCE.md#trust-follow-ups) for freshness and provenance work that is not implemented yet.

## Develop or run manually

Python 3.12+ and Git are sufficient. There are no Python packages to install. GitHub Actions uses Python 3.13; its publication job also uses the runner's GitHub CLI.

```sh
python3 -m unittest discover -v
python3 sync.py sync --output build/catalog
python3 sync.py verify build/catalog
```

The manual command makes a local snapshot only. To compare against an existing validated snapshot, pass `--previous /path/to/previous-catalog` and use a fresh output directory. An unchanged comparison creates no output and reports `changed: false`.

Program records follow [schema/program.schema.json](schema/program.schema.json). See [MAINTENANCE.md](MAINTENANCE.md) for failure handling, reviewed upstream revisions and publication permissions.

See [CONTRIBUTING.md](CONTRIBUTING.md) for importer fixes and public data corrections, and the [code of conduct](CODE_OF_CONDUCT.md) for participation guidance.

## License

The importer is MIT licensed. Upstream dataset attribution and its MIT notice are included. Program policies and testing permissions remain governed by their authoritative sources; a software license does not authorize security testing.
