"""Tier definitions for QuellDAP, read from tiers.json (edited with admin/tier-editor.html).

A tier is a named list of feature names. issue_license.py writes the explicit features into the
license file, so a license keeps the features it was issued with.
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tiers.json")
TIER_ORDER = ("free", "basic", "full", "ultra")


def load(path: str = PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    validate(data)
    return data


def validate(data: dict) -> None:
    catalog = set(data["catalog"])
    tiers = data["tiers"]
    if set(tiers) != set(TIER_ORDER):
        raise ValueError(f"tiers must be exactly {', '.join(TIER_ORDER)}")
    for name, features in tiers.items():
        unknown = set(features) - catalog
        if unknown:
            raise ValueError(f"tier {name} has features not in the catalog: {sorted(unknown)}")
        if len(set(features)) != len(features):
            raise ValueError(f"tier {name} lists a feature twice")
    for old, new in data.get("legacy", {}).items():
        if new not in tiers:
            raise ValueError(f"legacy token {old} maps to unknown tier {new}")


def resolve_tier(name: str, path: str = PATH) -> list:
    data = load(path)
    key = data.get("legacy", {}).get(name, name)
    if key not in data["tiers"]:
        raise ValueError(f"unknown tier {name!r}; use one of {', '.join(TIER_ORDER)}")
    return list(data["tiers"][key])
