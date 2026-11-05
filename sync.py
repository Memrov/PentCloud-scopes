"""Build and verify public catalog snapshots from one immutable upstream commit."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from catalog import CatalogError, PLATFORMS, UPSTREAM, canonical, digest, normalize, program_url, text

ROOT = Path(__file__).resolve().parent
SHA = re.compile(r"[0-9a-f]{40}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
PROGRAM_PATH = re.compile(r"programs/(bugcrowd|hackerone|intigriti|yeswehack)/[0-9a-f]{64}\.json\Z")
STATIC_PATHS = {"index.json", "changes.json", "schema/program.schema.json", "LICENSES/upstream-MIT.txt"}


def decode(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CatalogError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(CatalogError("Nonfinite JSON number")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CatalogError("Invalid source JSON") from exc


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(url, limit, attempts=3):
    headers = {"User-Agent": "PentCloud-scopes/1", "Accept": "application/json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and urlsplit(url).hostname == "api.github.com":
        headers["Authorization"] = "Bearer " + token
    opener = build_opener(NoRedirect())
    for attempt in range(attempts):
        try:
            with opener.open(Request(url, headers=headers), timeout=30) as response:
                if response.status != 200:
                    raise CatalogError("Unexpected upstream HTTP status")
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise CatalogError("Upstream body exceeds size limit")
                return body
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            retryable = not isinstance(exc, HTTPError) or exc.code == 429 or exc.code >= 500
            if not retryable or attempt == attempts - 1:
                # Never include response bodies, headers, or credential-bearing URLs.
                raise CatalogError("Public upstream download failed") from None
            time.sleep(2 ** attempt)
    raise CatalogError("Public upstream download failed")


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
    except (AttributeError, TypeError, ValueError) as exc:
        raise CatalogError("Expected timestamp with timezone") from exc
    return value


def fetch_source(source_commit=None, fetch=download):
    if source_commit is not None and not SHA.fullmatch(source_commit):
        raise CatalogError("Source revision must be a full Git commit SHA")
    ref = source_commit or "main"
    info = decode(fetch("https://api.github.com/repos/" + UPSTREAM + "/commits/" + ref, 2_000_000))
    try:
        revision = info["sha"]
        committed_at = timestamp(info["commit"]["committer"]["date"])
        if not isinstance(revision, str) or not SHA.fullmatch(revision) or (source_commit and revision != source_commit):
            raise ValueError()
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogError("Invalid upstream commit metadata") from exc
    feeds = {}
    for platform in PLATFORMS:
        url = "https://raw.githubusercontent.com/" + UPSTREAM + "/" + revision + "/data/" + platform + "_data.json"
        feeds[platform] = decode(fetch(url, 32 * 1024 * 1024))
    return feeds, revision, committed_at


def summary(record, path):
    return {key: record[key] for key in ("id", "platform", "name", "url", "source_status")} | {
        "path": path, "record_sha256": record["source"]["record_sha256"],
        "scope_counts": {group: len(assets) for group, assets in record["targets"].items()},
    }


def content_digest(files):
    return digest(canonical({path: digest(body) for path, body in files.items()
                             if path not in {"manifest.json", "changes.json"}}))


def changes_for(old, current, previous_hash):
    return {
        "schema_version": 1, "previous_catalog_sha256": previous_hash,
        "added": [current[key] for key in sorted(set(current) - set(old))],
        "updated": [current[key] for key in sorted(set(current) & set(old)) if current[key] != old[key]],
        "removed": [{**old[key], "reason": "absent_from_upstream_snapshot"}
                    for key in sorted(set(old) - set(current))],
    }


def guard_scope_losses(old, new_targets, previous, previous_counts, revision):
    losses = {platform: {"in_scope": 0, "out_of_scope": 0} for platform in PLATFORMS}
    for identifier, row in old.items():
        before = decode((Path(previous) / row["path"]).read_bytes())["targets"]
        after = new_targets.get(identifier, {"in_scope": [], "out_of_scope": []})
        for group, assets in before.items():
            # Compare original entries conservatively, including their restrictions.
            # Additions never offset removals; duplicate entries retain multiplicity.
            old_entries = Counter(digest(canonical(asset["raw"])) for asset in assets)
            new_entries = Counter(digest(canonical(asset["raw"])) for asset in after[group])
            lost = sum((old_entries - new_entries).values())
            losses[row["platform"]][group] += lost
            if identifier in new_targets and (
                (group == "out_of_scope" and assets and lost == len(assets))
                or (lost >= 10 and lost > len(assets) * 0.5)
            ):
                raise CatalogError("Program restriction loss requires review of source commit " + revision)
    for platform, groups in losses.items():
        for group, lost in groups.items():
            if lost >= 10 and lost > previous_counts[platform][group] * 0.5:
                raise CatalogError("Large scope reduction requires review of source commit " + revision)


def build_catalog(feeds, revision, committed_at, observed_at, previous=None, reviewed_source_commit=None):
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        raise CatalogError("Source revision must be a full Git commit SHA")
    timestamp(committed_at)
    timestamp(observed_at)
    if set(feeds) != set(PLATFORMS):
        raise CatalogError("All four public feeds must be present")
    files, rows, counts, new_targets = {}, [], {}, {}
    for platform in PLATFORMS:
        records = normalize(platform, feeds[platform])
        counts[platform] = {"programs": len(records), "in_scope": 0, "out_of_scope": 0}
        for record in records:
            path = "programs/" + platform + "/" + digest(record["id"].encode()) + ".json"
            files[path] = canonical(record)
            rows.append(summary(record, path))
            new_targets[record["id"]] = record["targets"]
            for group, assets in record["targets"].items():
                counts[platform][group] += len(assets)
        if counts[platform]["in_scope"] == 0:
            raise CatalogError("Public feed contains no in-scope assets: " + platform)
    rows.sort(key=lambda row: row["id"])
    current = {row["id"]: row for row in rows}
    old, old_manifest = {}, None
    if previous is not None and (Path(previous) / "manifest.json").exists():
        old_manifest = verify(Path(previous))
        old = {row["id"]: row for row in decode((Path(previous) / "index.json").read_bytes())["programs"]}
        if reviewed_source_commit != revision:
            for platform in PLATFORMS:
                before = old_manifest["counts"][platform]
                removed = sum(row["platform"] == platform and identifier not in current for identifier, row in old.items())
                if removed >= 5 and removed / before["programs"] > 0.2:
                    raise CatalogError("Large program removal requires review of source commit " + revision)
            guard_scope_losses(old, new_targets, previous, old_manifest["counts"], revision)
    files["index.json"] = canonical({"schema_version": 1, "programs": rows})
    files["changes.json"] = canonical(changes_for(old, current, old_manifest["catalog_sha256"] if old_manifest else None))
    for path in ("schema/program.schema.json", "LICENSES/upstream-MIT.txt"):
        files[path] = (ROOT / path).read_bytes()
    files["manifest.json"] = canonical({
        "schema_version": 1, "catalog_sha256": content_digest(files),
        "published_at": observed_at, "provider_verified_at": None,
        "source": {"repository": UPSTREAM, "commit": revision, "committed_at": committed_at,
                   "fetched_at": observed_at,
                   "feed_sha256": {p: digest(canonical(feeds[p])) for p in PLATFORMS}},
        "counts": counts,
        "files": {path: digest(body) for path, body in sorted(files.items())},
    })
    return files


def validate_changes(changes, rows):
    if (not isinstance(changes, dict)
            or set(changes) != {"schema_version", "previous_catalog_sha256", "added", "updated", "removed"}
            or type(changes["schema_version"]) is not int or changes["schema_version"] != 1):
        raise CatalogError("Invalid changelog structure")
    previous = changes["previous_catalog_sha256"]
    if previous is not None and (not isinstance(previous, str) or not HASH.fullmatch(previous)):
        raise CatalogError("Invalid predecessor digest")
    current = {row["id"]: row for row in rows}
    seen = set()
    keys = {"id", "platform", "name", "url", "source_status", "path", "record_sha256", "scope_counts"}
    for group in ("added", "updated", "removed"):
        if not isinstance(changes[group], list):
            raise CatalogError("Invalid changelog rows")
        for row in changes[group]:
            if not isinstance(row, dict) or set(row) != keys | ({"reason"} if group == "removed" else set()):
                raise CatalogError("Invalid changelog row")
            if row["id"] in seen:
                raise CatalogError("Duplicate changelog identity")
            seen.add(row["id"])
            if group != "removed":
                if current.get(row["id"]) != row:
                    raise CatalogError("Changelog does not reference the current index")
                continue
            platform = row["platform"]
            if (platform not in PLATFORMS or row["id"] in current
                    or not isinstance(row["id"], str) or not row["id"].startswith(platform + ":")
                    or row["reason"] != "absent_from_upstream_snapshot"
                    or not isinstance(row["record_sha256"], str) or not HASH.fullmatch(row["record_sha256"])):
                raise CatalogError("Invalid removed program")
            expected_path = "programs/" + platform + "/" + digest(row["id"].encode()) + ".json"
            if row["path"] != expected_path:
                raise CatalogError("Invalid removed program path")
            text(row["name"], "removed program name")
            program_url(platform, row["url"])
            status, counts = row["source_status"], row["scope_counts"]
            if (not isinstance(status, dict) or set(status) != {"field", "value"}
                    or (status["field"] is not None and not isinstance(status["field"], str))
                    or (status["value"] is not None and type(status["value"]) not in (str, bool))
                    or not isinstance(counts, dict) or set(counts) != {"in_scope", "out_of_scope"}
                    or any(type(value) is not int or value < 0 for value in counts.values())):
                raise CatalogError("Invalid removed program metadata")


def verify(root):
    root = Path(root)
    if root.is_symlink():
        raise CatalogError("Catalog root is a symlink")
    try:
        manifest = decode((root / "manifest.json").read_bytes())
        if manifest["schema_version"] != 1 or manifest["source"]["repository"] != UPSTREAM:
            raise CatalogError("Unsupported catalog format/source")
        if not SHA.fullmatch(manifest["source"]["commit"]) or manifest["provider_verified_at"] is not None:
            raise CatalogError("Invalid source provenance")
        feeds = manifest["source"]["feed_sha256"]
        if (not isinstance(feeds, dict) or set(feeds) != set(PLATFORMS)
                or any(not isinstance(value, str) or not HASH.fullmatch(value) for value in feeds.values())):
            raise CatalogError("Invalid source feed checksums")
        for value in (manifest["published_at"], manifest["source"]["committed_at"], manifest["source"]["fetched_at"]):
            timestamp(value)
        paths = manifest["files"]
        if not isinstance(paths, dict) or not STATIC_PATHS.issubset(paths):
            raise CatalogError("Incomplete catalog file list")
        bodies = {}
        for path, expected in paths.items():
            if path not in STATIC_PATHS and not PROGRAM_PATH.fullmatch(path):
                raise CatalogError("Unexpected catalog path")
            if not isinstance(expected, str) or not HASH.fullmatch(expected):
                raise CatalogError("Invalid file digest")
            file = root / path
            if any(root.joinpath(*Path(path).parts[:n]).is_symlink()
                   for n in range(1, len(Path(path).parts) + 1)):
                raise CatalogError("Symlink in catalog")
            body = file.read_bytes()
            if len(body) > 32 * 1024 * 1024 or digest(body) != expected:
                raise CatalogError("Catalog checksum mismatch")
            bodies[path] = body
        actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
                  if ".git" not in p.relative_to(root).parts and (p.is_file() or p.is_symlink())}
        if actual != set(paths) | {"manifest.json"} or content_digest(bodies) != manifest["catalog_sha256"]:
            raise CatalogError("Catalog contents do not match manifest")
        index = decode(bodies["index.json"])
        if index["schema_version"] != 1 or not isinstance(index["programs"], list):
            raise CatalogError("Invalid index")
        seen, record_paths = set(), set()
        counts = {p: {"programs": 0, "in_scope": 0, "out_of_scope": 0} for p in PLATFORMS}
        for row in index["programs"]:
            path = row["path"]
            if not PROGRAM_PATH.fullmatch(path) or path in record_paths:
                raise CatalogError("Invalid index record path")
            record = decode(bodies[path])
            raw = {**record["metadata"], "targets": {
                group: [asset["raw"] for asset in assets] for group, assets in record["targets"].items()}}
            rebuilt = normalize(record["platform"], [raw])[0]
            expected_path = "programs/" + record["platform"] + "/" + digest(record["id"].encode()) + ".json"
            if rebuilt != record or summary(record, path) != row or path != expected_path or record["id"] in seen:
                raise CatalogError("Inconsistent program record")
            seen.add(record["id"])
            record_paths.add(path)
            counts[record["platform"]]["programs"] += 1
            for group, assets in record["targets"].items():
                counts[record["platform"]][group] += len(assets)
        if record_paths != {path for path in paths if PROGRAM_PATH.fullmatch(path)} or counts != manifest["counts"]:
            raise CatalogError("Inconsistent catalog counts")
        if any(value["programs"] == 0 or value["in_scope"] == 0 for value in counts.values()):
            raise CatalogError("Empty platform in catalog")
        validate_changes(decode(bodies["changes.json"]), index["programs"])
        return manifest
    except (KeyError, TypeError, OSError, ValueError) as exc:
        if isinstance(exc, CatalogError):
            raise
        raise CatalogError("Invalid or incomplete catalog") from exc


def publish(files, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".catalog-", dir=output.parent) as tmp:
        staged = Path(tmp) / "snapshot"
        staged.mkdir()
        for path, body in files.items():
            if path not in STATIC_PATHS | {"manifest.json"} and not PROGRAM_PATH.fullmatch(path):
                raise CatalogError("Unexpected output path")
            target = staged / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        new = verify(staged)
        if output.exists() or output.is_symlink():
            old = verify(output)
            if old["catalog_sha256"] == new["catalog_sha256"]:
                return False
            backup = Path(tmp) / "previous"
            output.rename(backup)
            try:
                staged.rename(output)
            except OSError:
                backup.rename(output)
                raise
        else:
            staged.rename(output)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("verify")
    check.add_argument("directory", type=Path)
    collect = commands.add_parser("sync")
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--previous", type=Path)
    collect.add_argument("--source-commit")
    collect.add_argument("--reviewed-source-commit")
    collect.add_argument("--input-dir", type=Path, help="Offline reproduction from saved public feeds")
    collect.add_argument("--source-committed-at")
    args = parser.parse_args()
    try:
        if args.command == "verify":
            manifest = verify(args.directory)
            print("Verified catalog " + manifest["catalog_sha256"])
            return
        if args.input_dir:
            feeds = {p: decode((args.input_dir / (p + "_data.json")).read_bytes()) for p in PLATFORMS}
            revision, committed_at = args.source_commit, args.source_committed_at
        else:
            feeds, revision, committed_at = fetch_source(args.source_commit)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        files = build_catalog(feeds, revision, committed_at, now, args.previous, args.reviewed_source_commit)
        new = decode(files["manifest.json"])
        old = verify(args.previous) if args.previous and (args.previous / "manifest.json").exists() else None
        changed = not old or old["catalog_sha256"] != new["catalog_sha256"]
        if changed:
            publish(files, args.output)
        print(json.dumps({"changed": changed, "source_commit": revision,
                          "catalog_sha256": new["catalog_sha256"], "counts": new["counts"]}, sort_keys=True))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                output.write("changed=" + str(changed).lower() + "\n")
    except (CatalogError, OSError) as exc:
        print("Catalog sync stopped: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
