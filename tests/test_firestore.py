"""Firestore adapter test. Runs only against the Firestore emulator.

Start the emulator, then run pytest:
  gcloud emulators firestore start --host-port=localhost:8081
  export FIRESTORE_EMULATOR_HOST=localhost:8081
  pytest tests/test_firestore.py
"""
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"),
                                reason="Firestore emulator not running")


def test_install_round_trip_and_count():
    from app.storage import FirestoreStorage
    store = FirestoreStorage(project="demo-licensing")
    store.db.collection("licenses").document("EMU-1").set({"status": "active", "max_installs": 2})
    store.save_install("EMU-1", "install-aaaaaa", "2026-11-10T00:00:00Z", token_hash="h1")
    store.save_install("EMU-1", "install-aaaaaa", "2026-11-10T01:00:00Z")
    install = store.get_install("EMU-1", "install-aaaaaa")
    assert install["token_hash"] == "h1"  # an update keeps the token hash
    assert install["last_seen"] == "2026-11-10T01:00:00Z"
    assert store.count_installs("EMU-1") == 1
    store.set_license_status("EMU-1", "revoked")
    assert store.get_license("EMU-1")["status"] == "revoked"


def test_admin_methods_round_trip():
    from app.storage import FirestoreStorage
    store = FirestoreStorage(project="demo-licensing")
    store.put_license("EMU-2", {"status": "active", "application": "EmuApp", "plan": "full"})
    store.save_install("EMU-2", "install-bbbbbb", "2026-11-10T00:00:00Z")
    assert [d["license_id"] for d in store.list_licenses(application="EmuApp")] == ["EMU-2"]
    store.delete_license("EMU-2")
    assert store.get_license("EMU-2") is None
    assert store.count_installs("EMU-2") == 0
