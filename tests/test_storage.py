"""Admin storage methods on the JSON backend (runs everywhere, no cloud needed).

The same methods are covered for Firestore in tests/test_firestore.py (emulator only).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_list_put_delete_on_json_backend(tmp_path):
    from app.storage import JsonStorage
    store = JsonStorage(str(tmp_path / "data.json"))
    store.put_license("A", {"status": "active", "application": "X", "plan": "full"})
    store.put_license("B", {"status": "revoked", "application": "Y", "plan": "full"})
    store.save_install("A", "install-1", "2026-11-10T00:00:00Z")
    store.save_install("B", "install-2", "2026-11-10T00:00:00Z")

    assert [d["license_id"] for d in store.list_licenses(status="active")] == ["A"]
    assert [d["license_id"] for d in store.list_licenses(application="Y")] == ["B"]
    assert len(store.list_licenses()) == 2

    store.delete_license("A")
    assert store.get_license("A") is None
    assert store.count_installs("A") == 0
    assert store.count_installs("B") == 1  # other licenses' installs are untouched
    store.delete_license("missing")  # no error for an unknown id
