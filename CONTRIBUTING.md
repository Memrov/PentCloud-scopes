# Contributing

This repository maintains the public catalog importer, schema and validation. Read the [security policy](SECURITY.md) before reporting a possible vulnerability, and follow the [code of conduct](CODE_OF_CONDUCT.md).

## Report a bug or data correction

Use the [bug form](https://github.com/Memrov/PentCloud-scopes/issues/new?template=bug_report.yml) for importer or publication defects and the [data correction form](https://github.com/Memrov/PentCloud-scopes/issues/new?template=data_correction.yml) for public catalog discrepancies. Include the relevant code or catalog commit. Use synthetic examples and public program-policy links; exclude credentials, private program details, sensitive target data and scan results.

Check the upstream [bounty-targets-data repository](https://github.com/arkadiyt/bounty-targets-data) and authoritative program policy when diagnosing a source discrepancy. Do not edit generated catalog files by hand or treat catalog membership as testing permission. Report vulnerabilities in a listed target through that program's own process.

## Make a change

1. Branch from `main`. Keep changes focused; explain any schema or source-adapter change and its effect on existing consumers.
2. Use Python 3.12+ and Git. No third-party Python packages or platform credentials are needed.
3. Add synthetic regression fixtures for behavior changes. Preserve exclusions, raw metadata, source provenance and failure handling; never contact target hosts in tests.
4. Run the checks below and describe the results in your pull request.

```sh
python3 -B -m unittest discover -v
git diff --check
```

Changes to GitHub Actions should retain full commit-SHA pins, read permissions by default and the isolated publication job. Pull requests must pass repository checks; dependency review rejects newly introduced high or critical vulnerabilities. The catalog sync job publishes generated data separately after validation. See [MAINTENANCE.md](MAINTENANCE.md) for reviewed source revisions and publication boundaries.
