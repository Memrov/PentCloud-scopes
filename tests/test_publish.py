import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from catalog import CatalogError, canonical, digest
from sync import build_catalog, publish
from tests.fixtures import feeds
from tests.test_sync import REV, WHEN

try:
    from publish_branch import publish_git
except ImportError:
    publish_git = None


def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd, stderr=subprocess.DEVNULL).decode().strip()


class PublishTests(unittest.TestCase):
    def test_real_git_publication_noop_and_update_keep_main_unchanged(self):
        self.assertIsNotNone(publish_git, "Git publisher has not been implemented")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote, seed = root / "remote.git", root / "seed"
            git("init", "--bare", str(remote))
            git("init", "-b", "main", str(seed))
            (seed / "README.md").write_text("Source code stays on main.\n")
            git("add", ".", cwd=seed)
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "initial", cwd=seed)
            git("push", str(remote), "main", cwd=seed)
            original_main = git("rev-parse", "refs/heads/main", cwd=remote)
            snapshot, workspace = root / "snapshot", root / "work"
            data = feeds()
            publish(build_catalog(data, REV, WHEN, WHEN), snapshot)
            self.assertTrue(publish_git(snapshot, str(remote), workspace))
            first = git("rev-parse", "refs/heads/catalog", cwd=remote)
            self.assertFalse(publish_git(snapshot, str(remote), root / "noop"))
            self.assertEqual(git("rev-parse", "refs/heads/catalog", cwd=remote), first)
            data["hackerone"][0]["name"] = "Renamed program"
            publish(build_catalog(data, "2" * 40, WHEN, WHEN, previous=workspace), snapshot)
            self.assertTrue(publish_git(snapshot, str(remote), root / "update"))
            self.assertEqual(git("rev-parse", "refs/heads/catalog^", cwd=remote), first)
            self.assertEqual(git("rev-parse", "refs/heads/main", cwd=remote), original_main)
            names = git("ls-tree", "--name-only", "catalog", cwd=remote).splitlines()
            self.assertEqual(names, ["LICENSES", "changes.json", "index.json", "manifest.json", "programs", "schema"])

    def test_invalid_snapshot_cannot_create_a_remote_branch(self):
        self.assertIsNotNone(publish_git, "Git publisher has not been implemented")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            git("init", "--bare", str(remote))
            snapshot = root / "snapshot"
            publish(build_catalog(feeds(), REV, WHEN, WHEN), snapshot)
            (snapshot / "index.json").write_text("{}")
            with self.assertRaises(CatalogError):
                publish_git(snapshot, str(remote), root / "work")
            self.assertEqual(git("for-each-ref", cwd=remote), "")

    def test_stale_build_cannot_overwrite_a_newer_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            git("init", "--bare", str(remote))
            original, newer, stale = root / "original", root / "newer", root / "stale"
            data = feeds()
            publish(build_catalog(data, REV, WHEN, WHEN), original)
            publish_git(original, str(remote), root / "first")
            data["hackerone"][0]["name"] = "Newer source"
            publish(build_catalog(data, "2" * 40, WHEN, WHEN, previous=original), newer)
            publish_git(newer, str(remote), root / "second")
            current = git("rev-parse", "refs/heads/catalog", cwd=remote)
            data["hackerone"][0]["name"] = "Stale build based on original"
            publish(build_catalog(data, "3" * 40, WHEN, WHEN, previous=original), stale)
            with self.assertRaises(CatalogError):
                publish_git(stale, str(remote), root / "third")
            self.assertEqual(git("rev-parse", "refs/heads/catalog", cwd=remote), current)

    def test_inaccurate_changelog_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = root / "remote.git"
            git("init", "--bare", str(remote))
            original, newer = root / "original", root / "newer"
            data = feeds()
            publish(build_catalog(data, REV, WHEN, WHEN), original)
            publish_git(original, str(remote), root / "first")
            current = git("rev-parse", "refs/heads/catalog", cwd=remote)
            data["hackerone"][0]["name"] = "Changed but omitted from changelog"
            files = build_catalog(data, "2" * 40, WHEN, WHEN, previous=original)
            changes = json.loads(files["changes.json"])
            changes["updated"] = []
            files["changes.json"] = canonical(changes)
            manifest = json.loads(files["manifest.json"])
            manifest["files"]["changes.json"] = digest(files["changes.json"])
            files["manifest.json"] = canonical(manifest)
            publish(files, newer)
            with self.assertRaises(CatalogError):
                publish_git(newer, str(remote), root / "second")
            self.assertEqual(git("rev-parse", "refs/heads/catalog", cwd=remote), current)


if __name__ == "__main__":
    unittest.main()
