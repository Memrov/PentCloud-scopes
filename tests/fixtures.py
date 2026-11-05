"""Synthetic public-program examples; no credentials or live targets."""


def feeds():
    return {
        "hackerone": [{
            "id": 0, "handle": "example", "name": "Example H1",
            "url": "https://hackerone.com/example", "submission_state": "open",
            "offers_bounties": False,
            "targets": {
                "in_scope": [{"asset_identifier": "https://www.example.com/api/v1/",
                              "asset_type": "URL", "instruction": "GET only; 1 request/second.",
                              "eligible_for_bounty": False, "eligible_for_submission": True}],
                "out_of_scope": [{"asset_identifier": "admin.example.com", "asset_type": "URL",
                                  "instruction": "Do not test.", "eligible_for_bounty": False,
                                  "eligible_for_submission": False}],
            },
        }],
        "bugcrowd": [{
            "name": "Example BC", "url": "https://bugcrowd.com/engagements/example",
            "safe_harbor": "full", "targets": {
                "in_scope": [{"type": "website", "target": "*.example.org",
                              "uri": "", "name": "*.example.org", "ipAddress": None}],
                "out_of_scope": [{"type": "website", "target": "excluded.example.org"}],
            },
        }],
        "intigriti": [{
            "id": "11111111-1111-4111-8111-111111111111", "name": "Example Intigriti",
            "url": "https://www.intigriti.com/programs/example/example/detail",
            "status": "open", "confidentiality_level": "public", "targets": {
                "in_scope": [{"type": "url", "endpoint": "https://example.net/only/",
                              "description": "No automated scanning.", "impact": "No Bounty"}],
                "out_of_scope": [{"type": "wildcard", "endpoint": "*.private.example.net",
                                  "description": "Excluded", "impact": "Out of scope"}],
            },
        }],
        "yeswehack": [{
            "id": "example-ywh", "name": "Example YWH", "public": True, "disabled": False,
            "targets": {
                "in_scope": [{"type": "web-application", "target": "https://example.test/"}],
                "out_of_scope": [{"type": "other", "target": "All third-party services"}],
            },
        }],
    }
