import copy
import unittest

try:
    from catalog import CatalogError, normalize
except ImportError:
    CatalogError = ValueError
    normalize = None

from tests.fixtures import feeds


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(normalize, "The catalog normalizer has not been implemented")
        self.feeds = feeds()

    def test_preserves_path_www_and_non_bounty_scope(self):
        record = normalize("hackerone", self.feeds["hackerone"])[0]
        asset = record["targets"]["in_scope"][0]
        self.assertEqual(asset["value"], "https://www.example.com/api/v1/")
        self.assertEqual(asset["type"], "URL")
        self.assertFalse(asset["eligible_for_bounty"])
        self.assertTrue(asset["eligible_for_submission"])
        self.assertEqual(asset["instructions"], "GET only; 1 request/second.")
        self.assertEqual(record["targets"]["out_of_scope"][0]["value"], "admin.example.com")

    def test_keeps_unflattened_wildcards_and_contextual_exclusions(self):
        bc = normalize("bugcrowd", self.feeds["bugcrowd"])[0]
        ywh = normalize("yeswehack", self.feeds["yeswehack"])[0]
        self.assertEqual(bc["targets"]["in_scope"][0]["value"], "*.example.org")
        self.assertEqual(ywh["targets"]["out_of_scope"][0]["value"], "All third-party services")
        self.assertEqual(ywh["url"], "https://yeswehack.com/programs/example-ywh")

    def test_preserves_unknown_types_metadata_and_raw_asset(self):
        raw = self.feeds["intigriti"][0]
        raw["extra_policy"] = {"approval_required": True}
        raw["targets"]["in_scope"][0]["type"] = None
        result = normalize("intigriti", [raw])[0]
        self.assertEqual(result["metadata"]["extra_policy"], {"approval_required": True})
        self.assertEqual(result["targets"]["in_scope"][0]["type"], "unknown")
        self.assertIsNone(result["targets"]["in_scope"][0]["raw"]["type"])
        self.assertEqual(result["targets"]["in_scope"][0]["instructions"], "No automated scanning.")
        self.assertEqual(raw["targets"]["in_scope"][0]["impact"], "No Bounty")

    def test_rename_does_not_change_identity_and_zero_h1_ids_do_not_collide(self):
        first = self.feeds["hackerone"][0]
        second = copy.deepcopy(first)
        second.update(handle="another", name="Another", url="https://hackerone.com/another")
        result = normalize("hackerone", [first, second])
        self.assertEqual(len({x["id"] for x in result}), 2)
        old_id = normalize("hackerone", [first])[0]["id"]
        first["name"] = "Renamed"
        self.assertEqual(normalize("hackerone", [first])[0]["id"], old_id)

    def test_suspended_program_is_not_promoted_to_active(self):
        raw = self.feeds["intigriti"][0]
        raw["status"] = "suspended"
        result = normalize("intigriti", [raw])[0]
        self.assertEqual(result["source_status"], {"field": "status", "value": "suspended"})
        self.assertNotIn("can_run", result)

    def test_private_data_is_rejected(self):
        for platform, field, value in [("intigriti", "confidentiality_level", "inviteonly"),
                                       ("yeswehack", "public", False),
                                       ("hackerone", "private", True)]:
            with self.subTest(platform=platform):
                raw = self.feeds[platform][0]
                raw[field] = value
                with self.assertRaises(CatalogError):
                    normalize(platform, [raw])

    def test_duplicate_program_identity_is_rejected(self):
        with self.assertRaises(CatalogError):
            normalize("bugcrowd", self.feeds["bugcrowd"] * 2)

    def test_empty_or_malformed_feed_is_rejected(self):
        for bad in [[], {}, None, ["bad"]]:
            with self.subTest(value=bad), self.assertRaises(CatalogError):
                normalize("hackerone", bad)

    def test_missing_or_ambiguous_scope_is_rejected(self):
        for mutation in [lambda x: x.pop("targets"),
                         lambda x: x["targets"].pop("out_of_scope"),
                         lambda x: x["targets"].update(conditional=[]),
                         lambda x: x["targets"]["in_scope"][0].pop("asset_identifier")]:
            raw = copy.deepcopy(self.feeds["hackerone"][0])
            mutation(raw)
            with self.assertRaises(CatalogError):
                normalize("hackerone", [raw])

    def test_untrusted_name_is_data_and_does_not_change_identity(self):
        raw = self.feeds["hackerone"][0]
        old_id = normalize("hackerone", [raw])[0]["id"]
        raw["name"] = '../../$(touch injected)\n<script>bad</script>'
        result = normalize("hackerone", [raw])[0]
        self.assertEqual(result["id"], old_id)
        self.assertEqual(result["name"], raw["name"])

    def test_program_url_cannot_point_at_another_host(self):
        raw = self.feeds["bugcrowd"][0]
        for url in ["https://evil.example/engagements/a", "https://bugcrowd.com@evil.example/a",
                    "javascript:alert(1)", "https://bugcrowd.com:8443/engagements/a"]:
            raw["url"] = url
            with self.subTest(url=url), self.assertRaises(CatalogError):
                normalize("bugcrowd", [raw])


if __name__ == "__main__":
    unittest.main()
