"""Shared-fixture tests for the Python verifier (run from the repo root: pytest)."""
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "verifiers" / "python"))
from licensing import check_online_reply, verify_license  # noqa: E402

CASES = json.loads((ROOT / "verifiers" / "cases.json").read_text(encoding="utf-8"))
NOW = datetime.strptime(CASES["now"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def test_shared_license_cases():
    for case in CASES["cases"]:
        result = verify_license(
            case["license"], CASES["public_key_pem"], case["mode"],
            case.get("features_needed", []), now=NOW,
        )
        assert result.valid_for_paid_features == case["expect"], case["name"]


def test_online_replies():
    data = json.loads((ROOT / "verifiers" / "online-replies.json").read_text(encoding="utf-8"))
    pub = (ROOT / "verifiers" / "online-public.pem").read_text(encoding="utf-8")
    expected = {"active": True, "limit_reached": False}
    for name, item in data.items():
        reply = json.loads(item["reply"])
        # Check each reply an hour after it was issued, so the test doesn't expire.
        checked = datetime.strptime(reply["payload"]["checked_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        result = check_online_reply(item["reply"], pub, item["license_id"], now=checked)
        assert result.active == expected.get(reply["payload"]["status"], result.active), name


def test_online_reply_rejects_wrong_license():
    data = json.loads((ROOT / "verifiers" / "online-replies.json").read_text(encoding="utf-8"))
    pub = (ROOT / "verifiers" / "online-public.pem").read_text(encoding="utf-8")
    item = next(iter(data.values()))
    assert not check_online_reply(item["reply"], pub, "SOME-OTHER-ID").active


def test_clock_rollback_is_rejected():
    data = json.loads((ROOT / "verifiers" / "online-replies.json").read_text(encoding="utf-8"))
    pub = (ROOT / "verifiers" / "online-public.pem").read_text(encoding="utf-8")
    item = next(iter(data.values()))
    checked = datetime.strptime(json.loads(item["reply"])["payload"]["checked_at"],
                                "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    from datetime import timedelta
    later = checked + timedelta(days=1)
    # The app has seen a later time than now, so the clock moved backwards.
    result = check_online_reply(item["reply"], pub, item["license_id"], now=checked, last_seen=later)
    assert not result.active and "clock" in result.reason


def test_legacy_full_plan_is_alias_of_subscription():
    # 'full' was merged into 'subscription'. Old licenses must give the same result under either name.
    for case in CASES["cases"]:
        if case["mode"] != "full":
            continue
        args = (case["license"], CASES["public_key_pem"])
        kwargs = dict(features_needed=case.get("features_needed", []), now=NOW)
        old = verify_license(*args, "full", **kwargs)
        new = verify_license(*args, "subscription", **kwargs)
        assert old.valid_for_paid_features == new.valid_for_paid_features, case["name"]
        assert old.valid_for_paid_features == case["expect"], case["name"]


def test_issuer_cases():
    # A reply must come from the license's issuer_url when both name one (SPEC.md section 5).
    for case in CASES["issuer_cases"]:
        result = check_online_reply(case["reply"], CASES["public_key_pem"], case["license_id"],
                                    now=NOW, issuer_url=case["license_issuer_url"])
        assert result.active == case["expect_active"], case["name"]


def test_evaluate_ignores_reply_from_another_issuer():
    from licensing import evaluate
    lic = next(c for c in CASES["cases"] if c["name"] == "subscription_with_issuer_url")["license"]
    by_name = {c["name"]: c["reply"] for c in CASES["issuer_cases"]}
    pem = CASES["public_key_pem"]
    assert evaluate(lic, pem, "subscription", "LIC-1", reply_text=by_name["same_issuer"], now=NOW).valid_for_paid_features
    assert not evaluate(lic, pem, "subscription", "LIC-1", reply_text=by_name["same_issuer_revoked"],
                        now=NOW).valid_for_paid_features
    # A revoke signed for another server is not trusted for this license, so the local license decides.
    assert evaluate(lic, pem, "subscription", "LIC-1", reply_text=by_name["different_issuer"], now=NOW).valid_for_paid_features
