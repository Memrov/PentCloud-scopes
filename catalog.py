"""Lossless public scope normalization. Nothing here contacts program targets."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import quote, urlsplit

UPSTREAM = "arkadiyt/bounty-targets-data"
PLATFORMS = ("bugcrowd", "hackerone", "intigriti", "yeswehack")
HOSTS = {
    "bugcrowd": {"bugcrowd.com", "www.bugcrowd.com"},
    "hackerone": {"hackerone.com", "www.hackerone.com"},
    "intigriti": {"intigriti.com", "www.intigriti.com", "app.intigriti.com"},
    "yeswehack": {"yeswehack.com", "www.yeswehack.com"},
}


class CatalogError(ValueError):
    """Input is incomplete, ambiguous, or incompatible with this catalog."""


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 1_000_000:
        raise CatalogError("Invalid " + label)
    return value


def program_url(platform, value):
    value = text(value, "program URL")
    try:
        parts = urlsplit(value)
        valid = (parts.scheme == "https" and parts.hostname in HOSTS[platform]
                 and parts.port in (None, 443) and not parts.username
                 and not parts.password and not parts.query and not parts.fragment
                 and not any(c.isspace() or ord(c) < 32 for c in value))
    except ValueError:
        valid = False
    if not valid:
        raise CatalogError("Invalid official program URL for " + platform)
    return value


def normalize(platform, programs):
    if platform not in PLATFORMS:
        raise CatalogError("Unsupported platform")
    if not isinstance(programs, list) or not programs or len(programs) > 50_000:
        raise CatalogError("Expected a nonempty program array for " + platform)
    result, seen = [], set()
    for raw in programs:
        if not isinstance(raw, dict):
            raise CatalogError("Expected program object for " + platform)
        if raw.get("private") is True or raw.get("public") is False:
            raise CatalogError("Nonpublic program in public source")
        name = text(raw.get("name"), "program name")
        if platform == "hackerone":
            # Numeric IDs in this upstream can be zero for several programs.
            identity = text(raw.get("handle"), "HackerOne handle")
            status = {"field": "submission_state", "value": text(raw.get("submission_state"), "status")}
        elif platform == "bugcrowd":
            identity = program_url(platform, raw.get("url"))
            status = {"field": None, "value": None}
        elif platform == "intigriti":
            if raw.get("confidentiality_level") != "public":
                raise CatalogError("Intigriti confidentiality is not public")
            identity = text(raw.get("id"), "Intigriti ID")
            status = {"field": "status", "value": text(raw.get("status"), "status")}
        else:
            if raw.get("public") is not True or type(raw.get("disabled")) is not bool:
                raise CatalogError("YesWeHack public/status metadata missing")
            identity = text(raw.get("id"), "YesWeHack ID")
            status = {"field": "disabled", "value": raw["disabled"]}
        identifier = platform + ":" + identity
        if identifier in seen:
            raise CatalogError("Duplicate program identity for " + platform)
        seen.add(identifier)
        url = ("https://yeswehack.com/programs/" + quote(identity, safe="")
               if platform == "yeswehack" else raw.get("url"))
        url = program_url(platform, url)
        targets = raw.get("targets")
        if not isinstance(targets, dict) or set(targets) != {"in_scope", "out_of_scope"}:
            raise CatalogError("Missing or unknown scope groups for " + platform)
        normalized_targets = {}
        for group, assets in targets.items():
            if not isinstance(assets, list) or len(assets) > 100_000:
                raise CatalogError("Invalid scope array for " + platform)
            normalized_targets[group] = []
            for asset in assets:
                if not isinstance(asset, dict):
                    raise CatalogError("Expected asset object")
                value_key = {"hackerone": "asset_identifier", "intigriti": "endpoint"}.get(platform, "target")
                type_key = "asset_type" if platform == "hackerone" else "type"
                value = text(asset.get(value_key), "asset value")
                asset_type = asset.get(type_key)
                if type_key not in asset or (asset_type is not None and not isinstance(asset_type, str)):
                    raise CatalogError("Missing or invalid asset type")
                instructions = asset.get("instruction" if platform == "hackerone" else "description")
                if instructions is not None and not isinstance(instructions, str):
                    raise CatalogError("Invalid asset instructions")
                for key in ("eligible_for_bounty", "eligible_for_submission"):
                    if key in asset and type(asset[key]) is not bool:
                        raise CatalogError("Invalid eligibility flag")
                normalized_targets[group].append({
                    "type": asset_type or "unknown", "value": value, "instructions": instructions,
                    "eligible_for_bounty": asset.get("eligible_for_bounty"),
                    "eligible_for_submission": asset.get("eligible_for_submission"),
                    "raw": asset,
                })
        result.append({
            "schema_version": 1, "id": identifier, "platform": platform,
            "source_id": identity, "name": name, "url": url, "source_status": status,
            "targets": normalized_targets,
            "metadata": {key: value for key, value in raw.items() if key != "targets"},
            "source": {"repository": UPSTREAM, "path": "data/" + platform + "_data.json",
                       "record_sha256": digest(canonical(raw))},
        })
    return sorted(result, key=lambda item: item["id"])
