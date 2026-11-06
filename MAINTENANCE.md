# Maintaining the public catalog

The upstream repository is fixed in code. No authenticated platform endpoints or user credentials are used. Changes to source locations, adapters or the schema require a reviewed main-branch change with passing CI.

## Routine updates

Run **Sync public catalog** from Actions on main, or let its hourly schedule run. The read-only build job tests the importer and compares all four feeds with the previous catalog. Only a changed, verified snapshot reaches a separate publication job with repository content write permission. Publication uses a normal fast-forward Git push; a conflicting update stops it. No force pushes are used.

GitHub supplies a short-lived repository token automatically. No repository secrets, Cloudflare credentials, platform API keys or personal access tokens need to be configured. The catalog branch contains JSON, the record schema and the upstream license notice only. It contains no workflows or executable files. Main should require pull requests and successful CI; prevent branch deletion and force pushes.

## A sync fails

Inspect the failed Actions step. Do not delete the previous data to make a job pass. Typical causes are an upstream outage, malformed JSON, an unknown scope group, missing required metadata, a nonpublic record, a checksum mismatch or an unexpectedly large removal/reduction. An upstream schema change may need an adapter update; fix and test that change before publishing again.

The previous snapshot remains available, but its availability must not be interpreted as current permission to test. Consumers should show source/publication ages and check the current official policy before running any assessment.

## Review a large change

Publication stops when at least five programs and more than 20% of a platform's programs disappear, or when at least ten assets and more than half of a scope group disappear within a program or platform. Losing all previous exclusions from a retained program also requires review, even for a single exclusion. Additions do not offset removals. Comparison uses original asset entries, including restrictions, so substantial policy edits can also require review. The entire four-platform snapshot is held back. Review the upstream diff and official source before approving it.

To accept a legitimate large change, dispatch **Sync public catalog** on main with `reviewed_source_commit` set to that exact 40-character upstream commit SHA. This pins the import to the reviewed revision and bypasses only the large-reduction gate. Input validation, public-data checks, checksums and output verification still apply. The approval does not carry forward to later commits.

## Consume and inspect a snapshot

`manifest.json` lists SHA-256 checksums for every published file except itself. `catalog_sha256` hashes the canonical JSON mapping of file paths to checksums, excluding `manifest.json` and `changes.json`; it identifies the catalog content independently of publication time and the preceding snapshot. Canonical JSON uses sorted keys, two-space indentation, UTF-8 and one trailing newline.

Stable program IDs use HackerOne handles, Intigriti IDs, YesWeHack slugs and Bugcrowd official program URLs. Record filenames are SHA-256 hashes of those full platform-qualified IDs. Display-name changes do not change identity. A genuine upstream handle/URL change appears as removal plus addition.

Each program's `metadata` and its assets' `raw` objects reconstruct the upstream record; `source.record_sha256` hashes that canonical reconstructed record. The manifest's feed hashes similarly describe canonical parsed upstream arrays, not the original download's whitespace. Free-text policies, HTML, URLs and asset strings are untrusted data: escape them when rendering and never execute them or compile them directly into a network allowlist.

To reproduce a published revision, supply its full upstream commit:

```sh
python3 sync.py sync --source-commit UPSTREAM_COMMIT_SHA --output build/reproduced
```

A failed refresh cannot prove a program was removed. A successful new snapshot can record absence, but cannot prove why it disappeared. Historical snapshots remain in the catalog branch history. Rollbacks for debugging must retain explicit source provenance and do not restore testing authorization.

## Trust follow-ups

These improvements require separate implementation and review; they are not guarantees of the current catalog:

- Define a maximum upstream source age and future-clock tolerance for publication, with tests for stale, future-dated and unchanged imports. Keep historical reproduction separate from publication eligibility.
- Expose the last successful import check separately from the last changed snapshot, so an unchanged catalog does not acquire a misleading publication time. A workflow badge alone cannot detect a stopped schedule.
- Record the importer commit and workflow run in provenance, then attest a verified manifest or snapshot archive and document consumer verification. Existing checksums do not authenticate the builder or verify platform policies.
- Measure importer branch coverage before choosing a regression threshold or publishing a coverage badge.

There are no published software releases or release automation today. If releases are introduced, create a draft, attach all assets and publish only after verification so the workflow supports [immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases). Release protection is separate from the advancing `catalog` branch.

## References

- [Public upstream dataset and collector attribution](https://github.com/arkadiyt/bounty-targets-data)
- [GitHub Actions schedules and limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
- [GitHub Actions billing](https://docs.github.com/en/actions/concepts/billing-and-usage)
