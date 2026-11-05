import copy
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest

from catalog import CatalogError, canonical, digest
from tests.fixtures import feeds

try:
    from sync import build_catalog, download, fetch_source, publish, verify
except ImportError:
    build_catalog = download = fetch_source = publish = verify = None

REV = "1" * 40
WHEN = "2026-01-01T12:00:00Z"


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(build_catalog, "Safe ingestion has not been implemented")
        self.feeds = feeds()

    def build(self, **kwargs):
        return build_catalog(self.feeds, REV, WHEN, WHEN, **kwargs)

    def test_build_records_provenance_without_claiming_provider_verification(self):
        files = self.build()
        manifest = json.loads(files["manifest.json"])
        self.assertEqual(manifest["source"]["commit"], REV)
        self.assertIsNone(manifest["provider_verified_at"])
        self.assertEqual(manifest["counts"]["hackerone"]["programs"], 1)
        index = json.loads(files["index.json"])
        self.assertEqual(len(index["programs"]), 4)
        for row in index["programs"]:
            self.assertIn(row["path"], files)
            self.assertEqual(json.loads(files[row["path"]])["id"], row["id"])

    def test_requires_all_four_complete_feeds(self):
        del self.feeds["yeswehack"]
        with self.assertRaises(CatalogError):
            self.build()

    def test_reordered_programs_have_identical_content_revision(self):
        second = copy.deepcopy(self.feeds["hackerone"][0])
        second.update(handle="other", url="https://hackerone.com/other")
        self.feeds["hackerone"].append(second)
        first = json.loads(self.build()["manifest.json"])
        self.feeds["hackerone"].reverse()
        self.assertEqual(json.loads(self.build()["manifest.json"])["catalog_sha256"], first["catalog_sha256"])

    def test_unsafe_display_text_never_becomes_a_filename(self):
        self.feeds["yeswehack"][0]["id"] = "../../$(touch bad)"
        files = self.build()
        self.assertFalse(any(".." in key or "$" in key for key in files))

    def test_noop_keeps_existing_publication_time_and_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "catalog"
            self.assertTrue(publish(self.build(), root))
            original = (root / "manifest.json").read_bytes()
            later = build_catalog(self.feeds, "2" * 40, WHEN, "2026-01-02T12:00:00Z")
            self.assertFalse(publish(later, root))
            self.assertEqual((root / "manifest.json").read_bytes(), original)

    def test_removed_program_disappears_and_has_explicit_removal_record(self):
        extra = copy.deepcopy(self.feeds["hackerone"][0])
        extra.update(handle="removed", url="https://hackerone.com/removed")
        self.feeds["hackerone"].append(extra)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "old"
            publish(self.build(), root)
            self.feeds["hackerone"].pop()
            files = self.build(previous=root)
            index = json.loads(files["index.json"])
            self.assertNotIn("hackerone:removed", [x["id"] for x in index["programs"]])
            changes = json.loads(files["changes.json"])
            self.assertEqual(changes["removed"][0]["id"], "hackerone:removed")
            self.assertEqual(changes["removed"][0]["reason"], "absent_from_upstream_snapshot")

    def test_large_removal_requires_review_of_that_exact_source_commit(self):
        original = self.feeds["hackerone"][0]
        for n in range(20):
            extra = copy.deepcopy(original)
            extra.update(handle="example" + str(n), url="https://hackerone.com/example" + str(n))
            self.feeds["hackerone"].append(extra)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "old"
            publish(self.build(), root)
            self.feeds["hackerone"] = self.feeds["hackerone"][:2]
            for approved in [None, "2" * 40]:
                with self.subTest(approved=approved), self.assertRaises(CatalogError):
                    self.build(previous=root, reviewed_source_commit=approved)
            self.assertIn("manifest.json", self.build(previous=root, reviewed_source_commit=REV))

    def test_failed_build_leaves_previous_output_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "catalog"
            publish(self.build(), root)
            before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.feeds["intigriti"] = []
            with self.assertRaises(CatalogError):
                publish(self.build(previous=root), root)
            self.assertEqual(before, {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()})

    def test_one_program_cannot_lose_exclusions_hidden_by_other_programs(self):
        first = self.feeds["hackerone"][0]
        first["targets"]["out_of_scope"] = [
            {"asset_identifier": f"excluded{n}.example.com", "asset_type": "URL"} for n in range(20)]
        for handle in ["other1", "other2"]:
            extra = copy.deepcopy(first)
            extra.update(handle=handle, url="https://hackerone.com/" + handle)
            self.feeds["hackerone"].append(extra)
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path(tmp) / "previous"
            publish(self.build(), previous)
            first["targets"]["out_of_scope"] = []
            with self.assertRaises(CatalogError):
                self.build(previous=previous)
            self.assertIn("manifest.json", self.build(previous=previous, reviewed_source_commit=REV))

    def test_additions_cannot_mask_removed_scope_entries(self):
        first = self.feeds["hackerone"][0]
        first["targets"]["in_scope"] = [
            {"asset_identifier": f"old{n}.example.com", "asset_type": "URL"} for n in range(20)]
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path(tmp) / "previous"
            publish(self.build(), previous)
            first["targets"]["in_scope"] = first["targets"]["in_scope"][:5] + [
                {"asset_identifier": f"new{n}.example.com", "asset_type": "URL"} for n in range(15)]
            with self.assertRaises(CatalogError):
                self.build(previous=previous)

    def test_even_a_single_exclusion_wipeout_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path(tmp) / "previous"
            publish(self.build(), previous)
            self.feeds["hackerone"][0]["targets"]["out_of_scope"] = []
            with self.assertRaises(CatalogError):
                self.build(previous=previous)

    def test_manifest_requires_all_four_valid_feed_checksums(self):
        for checksums in [None, {}, {"hackerone": "bad"}, {p: "not-a-hash" for p in self.feeds}]:
            files = self.build()
            manifest = json.loads(files["manifest.json"])
            if checksums is None:
                del manifest["source"]["feed_sha256"]
            else:
                manifest["source"]["feed_sha256"] = checksums
            files["manifest.json"] = canonical(manifest)
            with self.subTest(checksums=checksums), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(CatalogError):
                    publish(files, Path(tmp) / "snapshot")

    def test_changelog_must_be_structured_and_reference_consistent_rows(self):
        for mutate in [lambda x, row: x.pop("schema_version"),
                       lambda x, row: x.update(added="not an array"),
                       lambda x, row: x.update(previous_catalog_sha256="bad"),
                       lambda x, row: x["added"].append(copy.deepcopy(row)),
                       lambda x, row: x.update(removed=[{**row, "reason": "unknown"}])]:
            files = self.build()
            changes = json.loads(files["changes.json"])
            mutate(changes, changes["added"][0])
            files["changes.json"] = canonical(changes)
            manifest = json.loads(files["manifest.json"])
            manifest["files"]["changes.json"] = digest(files["changes.json"])
            files["manifest.json"] = canonical(manifest)
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(CatalogError):
                    publish(files, Path(tmp) / "snapshot")

    def test_verifier_rejects_modified_or_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "catalog"
            publish(self.build(), root)
            verify(root)
            (root / "index.json").write_text("{}")
            with self.assertRaises(CatalogError):
                verify(root)
            (root / "index.json").write_bytes(self.build()["index.json"])
            (root / "unexpected.txt").write_text("extra")
            with self.assertRaises(CatalogError):
                verify(root)

    def test_verifier_rejects_traversal_and_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "catalog"
            files = self.build()
            manifest = json.loads(files["manifest.json"])
            manifest["files"]["../escape"] = "0" * 64
            files["manifest.json"] = json.dumps(manifest).encode()
            with self.assertRaises(CatalogError):
                publish(files, root)
            publish(self.build(), root)
            (root / "index.json").unlink()
            (root / "index.json").symlink_to(Path(tmp) / "elsewhere")
            with self.assertRaises(CatalogError):
                verify(root)

    def test_source_is_pinned_once_and_only_public_data_files_are_requested(self):
        calls = []
        def fetch(url, limit):
            calls.append(url)
            if url.endswith("/commits/main"):
                return json.dumps({"sha": REV, "commit": {"committer": {"date": WHEN}}}).encode()
            platform = url.rsplit("/", 1)[1].removesuffix("_data.json")
            return json.dumps(self.feeds[platform]).encode()
        loaded, revision, timestamp = fetch_source(fetch=fetch)
        self.assertEqual(revision, REV)
        self.assertEqual(timestamp, WHEN)
        self.assertEqual(len(loaded), 4)
        self.assertEqual(len(calls), 5)
        self.assertTrue(all("/" + REV + "/data/" in url for url in calls[1:]))

    def test_invalid_json_or_source_revision_is_rejected(self):
        for data in [b"{", b'{"sha":"main"}', b'{"sha":"../escape"}']:
            with self.subTest(data=data), self.assertRaises(CatalogError):
                fetch_source(fetch=lambda url, limit: data)


class QuietHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        status = 500 if self.path == "/error" else 302 if self.path == "/redirect" else 200
        self.send_response(status)
        if status == 302:
            self.send_header("Location", "/ok")
        self.end_headers()
        self.wfile.write(b"abcdef")

    def log_message(self, *args):
        pass


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_download_checks_size_http_status_and_redirects(self):
        self.assertIsNotNone(download, "Bounded download has not been implemented")
        base = "http://127.0.0.1:" + str(self.server.server_port)
        self.assertEqual(download(base + "/ok", 6, attempts=1), b"abcdef")
        for path, limit in [("/ok", 5), ("/error", 20), ("/redirect", 20)]:
            with self.subTest(path=path), self.assertRaises(CatalogError):
                download(base + path, limit, attempts=1)


if __name__ == "__main__":
    unittest.main()
