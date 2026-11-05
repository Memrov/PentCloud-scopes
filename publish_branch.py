"""Publish validated JSON to catalog; never write the source-code branch."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from catalog import CatalogError
from sync import changes_for, decode, verify


def git(directory, *args, allow_missing=False):
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args],
                            cwd=directory, capture_output=True, check=False)
    if result.returncode and not (allow_missing and result.returncode == 2):
        raise CatalogError("Git " + args[0] + " failed (exit " + str(result.returncode) + ")")
    return result


def checkout_catalog(remote, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    git(directory, "init", "-q", "-b", "catalog")
    git(directory, "remote", "add", "origin", remote)
    # GitHub's automatically supplied token remains in the process environment.
    # No token value is written to configuration, URLs, files, or stdout.
    if os.environ.get("GH_TOKEN"):
        git(directory, "config", "credential.helper", "!gh auth git-credential")
    head = git(directory, "ls-remote", "--exit-code", "--heads", "origin", "refs/heads/catalog", allow_missing=True)
    if head.returncode == 2:
        return False
    git(directory, "fetch", "--quiet", "--depth=1", "origin", "refs/heads/catalog")
    git(directory, "checkout", "--quiet", "-B", "catalog", "FETCH_HEAD")
    verify(directory)
    return True


def publish_git(snapshot, remote, workspace):
    snapshot, workspace = Path(snapshot), Path(workspace)
    manifest = verify(snapshot)
    exists = checkout_catalog(remote, workspace)
    old = verify(workspace) if exists else None
    if old and old["catalog_sha256"] == manifest["catalog_sha256"]:
        return False
    previous_hash = decode((snapshot / "changes.json").read_bytes())["previous_catalog_sha256"]
    if previous_hash != (old["catalog_sha256"] if old else None):
        raise CatalogError("Catalog changed after this build; rebuild against the current snapshot")
    old_rows = decode((workspace / "index.json").read_bytes())["programs"] if old else []
    current_rows = decode((snapshot / "index.json").read_bytes())["programs"]
    expected_changes = changes_for({row["id"]: row for row in old_rows},
                                   {row["id"]: row for row in current_rows}, previous_hash)
    if decode((snapshot / "changes.json").read_bytes()) != expected_changes:
        raise CatalogError("Changelog does not describe this catalog transition")
    if exists:
        for entry in workspace.iterdir():
            if entry.name == ".git":
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    # Copy only verified manifest paths, never upstream code or .git metadata.
    for path in [*manifest["files"], "manifest.json"]:
        destination = workspace / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((snapshot / path).read_bytes())
    verify(workspace)
    git(workspace, "add", "--all", "--", "manifest.json", "index.json", "changes.json", "programs", "schema", "LICENSES")
    git(workspace, "-c", "user.name=github-actions[bot]",
        "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "--quiet", "-m", "catalog: publish " + manifest["catalog_sha256"][:12])
    # A concurrent update rejects this normal fast-forward push. Never force it.
    git(workspace, "push", "--quiet", "origin", "HEAD:refs/heads/catalog")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("previous", "publish"))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    try:
        if not args.repository or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
            raise CatalogError("Expected GitHub owner/repository")
        remote = "https://github.com/" + args.repository + ".git"
        if args.command == "previous":
            exists = checkout_catalog(remote, args.directory)
            print("Previous catalog loaded" if exists else "First publication: no previous catalog")
        else:
            if args.snapshot is None:
                raise CatalogError("--snapshot is required")
            changed = publish_git(args.snapshot, remote, args.directory)
            print("Published catalog" if changed else "Catalog unchanged; no commit created")
    except (CatalogError, OSError) as exc:
        print("Catalog publication stopped: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
