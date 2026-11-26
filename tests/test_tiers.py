import json

import pytest

import tiers


def test_shipped_tiers_are_valid():
    data = tiers.load()
    assert set(data["tiers"]) == {"free", "basic", "full", "ultra"}
    assert data["tiers"]["free"] == []


def test_legacy_tier_2_is_full():
    assert tiers.resolve_tier("tier-2") == tiers.resolve_tier("full")
    assert tiers.resolve_tier("tier-1") == tiers.resolve_tier("basic")


def test_unknown_tier_refused():
    with pytest.raises(ValueError):
        tiers.resolve_tier("gold")


def test_feature_outside_catalog_refused(tmp_path):
    data = tiers.load()
    data["tiers"]["basic"].append("not-a-feature")
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        tiers.load(str(path))


def test_issue_license_tier_features():
    import issue_license

    names = issue_license.tier_features("basic", "sso")
    assert "sso" in names and "advanced-sync" in names
    assert names == sorted(set(names))
